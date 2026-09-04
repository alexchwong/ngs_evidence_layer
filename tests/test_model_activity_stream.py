import io
import json
import os
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from workflows.proforma_v1 import model_client
from workflows.proforma_v1.model_binding import Binding


class _Response:
    def __init__(self, *, lines=None, body=b""):
        self.lines = list(lines or [])
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def __iter__(self):
        return iter(self.lines)

    def read(self):
        return self.body


def _binding(*, reasoning="default", base_url="https://openrouter.ai/api/v1") -> Binding:
    return Binding(
        pipeline="openrouter-test",
        role="diagnosis",
        kind="openai-compatible",
        model="example/model",
        base_url=base_url,
        api_key="test-key",
        timeout_s=30,
        reasoning=reasoning,
    )


class ModelActivityStreamingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.activity = Path(self.tmp.name) / "activity.jsonl"
        self.env = mock.patch.dict(
            os.environ,
            {
                "NEL_MODEL_STREAM": "1",
                "NEL_MODEL_ACTIVITY_FILE": str(self.activity),
            },
            clear=False,
        )
        self.env.start()

    def tearDown(self):
        self.env.stop()
        self.tmp.cleanup()

    def _events(self):
        return [json.loads(line) for line in self.activity.read_text(encoding="utf-8").splitlines()]


    def test_openrouter_reasoning_effort_is_sent_per_binding(self):
        payload = model_client._payload(
            _binding(reasoning="high"),
            [{"role": "user", "content": "x"}],
            stream=True,
        )
        self.assertEqual(payload["reasoning"], {"effort": "high"})

    def test_default_reasoning_omits_provider_parameter(self):
        payload = model_client._payload(
            _binding(reasoning="default"),
            [{"role": "user", "content": "x"}],
            stream=True,
        )
        self.assertNotIn("reasoning", payload)

    def test_lmstudio_responses_receives_supported_reasoning_effort(self):
        binding = _binding(reasoning="high", base_url="http://localhost:1234/v1")
        payload = model_client._payload(
            binding,
            [{"role": "user", "content": "x"}],
            stream=True,
        )
        self.assertEqual(model_client._endpoint(binding), "http://localhost:1234/v1/responses")
        self.assertEqual(payload["reasoning"], {"effort": "high"})
        self.assertIn("input", payload)
        self.assertEqual(payload["max_output_tokens"], binding.max_tokens)
        self.assertNotIn("messages", payload)
        self.assertNotIn("max_tokens", payload)

    def test_lmstudio_rejects_unsupported_reasoning_level(self):
        with self.assertRaisesRegex(RuntimeError, "unsupported by NEL"):
            model_client._payload(
                _binding(reasoning="xhigh", base_url="http://localhost:1234/v1"),
                [{"role": "user", "content": "x"}],
                stream=True,
            )

    def test_lmstudio_responses_stream_keeps_reasoning_out_of_completion(self):
        lines = [
            b'data: {"type":"response.created","response":{"id":"resp-1"}}\n',
            b'data: {"type":"response.reasoning_summary_text.delta","delta":"think "}\n',
            b'data: {"type":"response.output_text.delta","delta":"answer"}\n',
            b'data: {"type":"response.completed","response":{"id":"resp-1","status":"completed","usage":{"input_tokens":3,"output_tokens":2,"total_tokens":5}}}\n',
        ]
        with mock.patch.object(model_client.urllib.request, "urlopen", return_value=_Response(lines=lines)):
            result = model_client.complete_messages(
                _binding(reasoning="high", base_url="http://localhost:1234/v1"),
                [{"role": "user", "content": "x"}],
            )
        self.assertEqual(result.content, "answer")
        self.assertEqual(result.reasoning, "think ")
        self.assertEqual(result.generation_id, "resp-1")
        self.assertEqual(result.usage["total_tokens"], 5)
        events = self._events()
        self.assertEqual("".join(row.get("text", "") for row in events if row["event"] == "reasoning"), "think ")
        self.assertEqual("".join(row.get("text", "") for row in events if row["event"] == "output"), "answer")
        self.assertEqual([row for row in events if row["event"] == "finish"][-1]["transport"], "responses")

    def test_stream_keeps_reasoning_out_of_completion(self):
        lines = [
            b'data: {"id":"gen-1","choices":[{"delta":{"reasoning":"think "},"finish_reason":null}]}\n',
            b'data: {"id":"gen-1","choices":[{"delta":{"content":"answer"},"finish_reason":null}]}\n',
            b'data: {"id":"gen-1","choices":[{"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":3,"completion_tokens":2,"total_tokens":5}}\n',
            b'data: [DONE]\n',
        ]
        with mock.patch.object(model_client.urllib.request, "urlopen", return_value=_Response(lines=lines)):
            result = model_client.complete_messages(_binding(reasoning="high"), [{"role": "user", "content": "x"}])
        self.assertEqual(result.content, "answer")
        self.assertEqual(result.reasoning, "think ")
        self.assertEqual(result.generation_id, "gen-1")
        self.assertEqual(result.usage["total_tokens"], 5)
        events = self._events()
        self.assertEqual([row for row in events if row["event"] == "start"][-1]["reasoning"], "high")
        self.assertEqual("".join(row.get("text", "") for row in events if row["event"] == "reasoning"), "think ")
        self.assertEqual("".join(row.get("text", "") for row in events if row["event"] == "output"), "answer")
        finish = [row for row in events if row["event"] == "finish"][-1]
        self.assertTrue(finish["reasoning_exposed"])
        self.assertTrue(finish["streamed"])

    def test_stream_without_reasoning_is_explicit(self):
        lines = [
            b'data: {"choices":[{"delta":{"content":"answer"},"finish_reason":null}]}\n',
            b'data: {"choices":[{"delta":{},"finish_reason":"stop"}]}\n',
            b'data: [DONE]\n',
        ]
        with mock.patch.object(model_client.urllib.request, "urlopen", return_value=_Response(lines=lines)):
            result = model_client.complete_messages(_binding(), [{"role": "user", "content": "x"}])
        self.assertEqual(result.content, "answer")
        finish = [row for row in self._events() if row["event"] == "finish"][-1]
        self.assertFalse(finish["reasoning_exposed"])

    def test_rejected_stream_falls_back_to_completed_response(self):
        error = urllib.error.HTTPError(
            model_client._endpoint(_binding()),
            400,
            "bad request",
            hdrs=None,
            fp=io.BytesIO(b"stream unsupported"),
        )
        body = json.dumps(
            {
                "id": "gen-2",
                "choices": [{"message": {"reasoning": "fallback thought", "content": "fallback answer"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4},
            }
        ).encode("utf-8")
        with mock.patch.object(
            model_client.urllib.request,
            "urlopen",
            side_effect=[error, _Response(body=body)],
        ):
            result = model_client.complete_messages(_binding(), [{"role": "user", "content": "x"}])
        self.assertEqual(result.content, "fallback answer")
        events = self._events()
        self.assertTrue(any(row["event"] == "fallback" for row in events))
        self.assertEqual("".join(row.get("text", "") for row in events if row["event"] == "reasoning"), "fallback thought")
        finish = [row for row in events if row["event"] == "finish"][-1]
        self.assertFalse(finish["streamed"])


    def test_non_ui_call_keeps_existing_nonstreaming_transport(self):
        os.environ["NEL_MODEL_STREAM"] = "0"
        body = json.dumps(
            {
                "id": "gen-nonstream",
                "choices": [{"message": {"content": "plain answer"}, "finish_reason": "stop"}],
            }
        ).encode("utf-8")
        seen = {}

        def fake_urlopen(request, timeout):
            seen.update(json.loads(request.data.decode("utf-8")))
            return _Response(body=body)

        with mock.patch.object(model_client.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = model_client.complete_messages(_binding(), [{"role": "user", "content": "x"}])
        self.assertEqual(result.content, "plain answer")
        self.assertFalse(seen["stream"])
        self.assertFalse(self.activity.exists())

    def test_reasoning_details_take_precedence_over_compatibility_aliases(self):
        self.assertEqual(
            model_client._reasoning_fragment(
                {
                    "reasoning": "router",
                    "reasoning_content": "router",
                    "thinking": "router",
                    "reasoning_details": [
                        {"type": "reasoning.text", "text": "router"},
                        {"type": "reasoning.encrypted", "data": "opaque"},
                    ],
                }
            ),
            "router",
        )

    def test_openrouter_stream_does_not_duplicate_mirrored_reasoning_fields(self):
        lines = [
            b'data: {"id":"gen-dup","choices":[{"delta":{"reasoning":"The ","reasoning_details":[{"type":"reasoning.text","text":"The ","id":"r1","index":0}]},"finish_reason":null}]}\n',
            b'data: {"id":"gen-dup","choices":[{"delta":{"reasoning":"model ","reasoning_details":[{"type":"reasoning.text","text":"model ","id":"r1","index":0}]},"finish_reason":null}]}\n',
            b'data: {"id":"gen-dup","choices":[{"delta":{"content":"answer"},"finish_reason":null}]}\n',
            b'data: {"id":"gen-dup","choices":[{"delta":{},"finish_reason":"stop"}]}\n',
            b'data: [DONE]\n',
        ]
        with mock.patch.object(model_client.urllib.request, "urlopen", return_value=_Response(lines=lines)):
            result = model_client.complete_messages(
                _binding(reasoning="high"), [{"role": "user", "content": "x"}]
            )
        self.assertEqual(result.content, "answer")
        reasoning = "".join(
            row.get("text", "") for row in self._events() if row["event"] == "reasoning"
        )
        self.assertEqual(reasoning, "The model ")
        self.assertEqual(result.reasoning, "The model ")

    def test_reasoning_alias_fallbacks_remain_supported(self):
        self.assertEqual(model_client._reasoning_fragment({"reasoning": "a"}), "a")
        self.assertEqual(model_client._reasoning_fragment({"reasoning_content": "b"}), "b")
        self.assertEqual(model_client._reasoning_fragment({"thinking": "c"}), "c")

    def test_reasoning_details_prefer_text_over_summary_in_same_chunk(self):
        self.assertEqual(
            model_client._reasoning_fragment(
                {
                    "reasoning_details": [
                        {"type": "reasoning.summary", "summary": "summary"},
                        {"type": "reasoning.text", "text": "raw"},
                    ]
                }
            ),
            "raw",
        )

    def test_activity_directory_uses_validated_run_reference_hash(self):
        os.environ.pop("NEL_MODEL_ACTIVITY_FILE", None)
        os.environ["NEL_MODEL_ACTIVITY_DIR"] = self.tmp.name
        with mock.patch.object(model_client.sys, "argv", ["nel.py", "run", "--run-id", "batch-1:case-2"]):
            path = model_client._activity_path()
        self.assertIsNotNone(path)
        self.assertEqual(path.parent, Path(self.tmp.name).resolve())
        self.assertEqual(path.suffix, ".jsonl")
        self.assertNotIn(":", path.name)

    def test_lmstudio_nonstreaming_responses_is_parsed(self):
        os.environ["NEL_MODEL_STREAM"] = "0"
        body = json.dumps({
            "id": "resp-sync",
            "status": "completed",
            "output": [
                {"type": "reasoning", "summary": [{"type": "summary_text", "text": "summary"}]},
                {"type": "message", "content": [{"type": "output_text", "text": "final"}]},
            ],
            "usage": {"input_tokens": 2, "output_tokens": 1, "total_tokens": 3},
        }).encode("utf-8")
        seen = {}
        def fake_urlopen(request, timeout):
            seen["url"] = request.full_url
            seen["payload"] = json.loads(request.data.decode("utf-8"))
            return _Response(body=body)
        with mock.patch.object(model_client.urllib.request, "urlopen", side_effect=fake_urlopen):
            result = model_client.complete_messages(
                _binding(reasoning="medium", base_url="http://localhost:1234/v1"),
                [{"role": "user", "content": "x"}],
            )
        self.assertEqual(result.content, "final")
        self.assertEqual(result.reasoning, "summary")
        self.assertEqual(result.reasoning_details[0]["type"], "reasoning")
        self.assertEqual(seen["url"], "http://localhost:1234/v1/responses")
        self.assertEqual(seen["payload"]["reasoning"], {"effort": "medium"})

    def test_old_lmstudio_does_not_silently_drop_requested_reasoning(self):
        os.environ["NEL_MODEL_STREAM"] = "0"
        error = urllib.error.HTTPError(
            "http://localhost:1234/v1/responses", 404, "not found", hdrs=None, fp=io.BytesIO(b"missing")
        )
        with mock.patch.object(model_client.urllib.request, "urlopen", side_effect=error):
            with self.assertRaisesRegex(RuntimeError, r"0\.3\.29\+"):
                model_client.complete_messages(
                    _binding(reasoning="high", base_url="http://localhost:1234/v1"),
                    [{"role": "user", "content": "x"}],
                )


if __name__ == "__main__":
    unittest.main()
