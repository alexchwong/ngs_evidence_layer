import io
import json
import unittest
from unittest.mock import patch

from workflows.proforma_v1 import model_client
from workflows.proforma_v1.model_binding import Binding


def _binding(reasoning):
    return Binding(
        pipeline="lmstudio",
        role="diagnosis",
        kind="openai-compatible",
        model="qwen3-coder-next",
        temperature=0.0,
        max_tokens=16384,
        base_url="http://localhost:1234/v1",
        reasoning=reasoning,
    )


class _Response:
    def __init__(self, body):
        self._body = body if isinstance(body, bytes) else body.encode("utf-8")

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _StreamResponse:
    def __init__(self, lines):
        self.lines = [line.encode("utf-8") for line in lines]

    def __iter__(self):
        return iter(self.lines)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class _Activity:
    def __init__(self):
        self.outputs = []
        self.reasonings = []
        self.events = []
        self.reasoning_exposed = False

    def output(self, text):
        self.outputs.append(text)

    def reasoning(self, text):
        self.reasoning_exposed = True
        self.reasonings.append(text)

    def emit(self, event, **fields):
        self.events.append((event, fields))


class LMStudioReasoningNoneTests(unittest.TestCase):
    def test_none_selects_native_chat_and_reasoning_off(self):
        binding = _binding("none")
        messages = [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "task"},
        ]
        self.assertEqual(model_client._lmstudio_transport(binding), "lmstudio-native")
        self.assertEqual(model_client._endpoint(binding), "http://localhost:1234/api/v1/chat")
        payload = model_client._payload(binding, messages, stream=False)
        self.assertEqual(payload["reasoning"], "off")
        self.assertEqual(payload["system_prompt"], "system")
        self.assertEqual(payload["input"], "task")
        self.assertEqual(payload["max_output_tokens"], 16384)
        self.assertNotIn("messages", payload)

    def test_default_and_effort_levels_remain_on_responses(self):
        for reasoning in ("default", "low", "medium", "high"):
            with self.subTest(reasoning=reasoning):
                binding = _binding(reasoning)
                self.assertEqual(model_client._lmstudio_transport(binding), "responses")
                self.assertEqual(model_client._endpoint(binding), "http://localhost:1234/v1/responses")
                payload = model_client._payload(binding, [{"role": "user", "content": "task"}], stream=False)
                if reasoning == "default":
                    self.assertNotIn("reasoning", payload)
                else:
                    self.assertEqual(payload["reasoning"], {"effort": reasoning})

    def test_native_retry_history_is_preserved_as_text_input(self):
        payload = model_client._payload(
            _binding("none"),
            [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "original"},
                {"role": "assistant", "content": "bad output"},
                {"role": "user", "content": "repair feedback"},
            ],
            stream=False,
        )
        self.assertIn("[USER]\noriginal", payload["input"])
        self.assertIn("[ASSISTANT]\nbad output", payload["input"])
        self.assertIn("[USER]\nrepair feedback", payload["input"])
        self.assertEqual(payload["reasoning"], "off")

    def test_native_nonstreaming_response_is_parsed(self):
        document = {
            "model_instance_id": "qwen3-coder-next",
            "output": [{"type": "message", "content": "answer"}],
            "stats": {"input_tokens": 10, "total_output_tokens": 4, "reasoning_output_tokens": 0},
            "response_id": "resp_123",
        }
        with patch("urllib.request.urlopen", return_value=_Response(json.dumps(document))):
            completion = model_client._complete_nonstreaming(
                _binding("none"), [{"role": "user", "content": "task"}]
            )
        self.assertEqual(completion.content, "answer")
        self.assertEqual(completion.generation_id, "resp_123")
        self.assertEqual(completion.usage["prompt_tokens"], 10)
        self.assertEqual(completion.usage["completion_tokens"], 4)
        self.assertEqual(completion.usage["reasoning_tokens"], 0)

    def test_native_streaming_response_is_parsed(self):
        result = {
            "model_instance_id": "qwen3-coder-next",
            "output": [{"type": "message", "content": "answer"}],
            "stats": {"input_tokens": 7, "total_output_tokens": 2, "reasoning_output_tokens": 0},
            "response_id": "resp_stream",
        }
        lines = [
            'event: chat.start\n',
            'data: {"type":"chat.start","model_instance_id":"qwen3-coder-next"}\n',
            'event: message.delta\n',
            'data: {"type":"message.delta","content":"ans"}\n',
            'event: message.delta\n',
            'data: {"type":"message.delta","content":"wer"}\n',
            'event: chat.end\n',
            'data: ' + json.dumps({"type": "chat.end", "result": result}) + '\n',
        ]
        activity = _Activity()
        with patch("urllib.request.urlopen", return_value=_StreamResponse(lines)):
            completion = model_client._complete_lmstudio_native_streaming(
                _binding("none"), [{"role": "user", "content": "task"}], activity
            )
        self.assertEqual(completion.content, "answer")
        self.assertEqual(completion.generation_id, "resp_stream")
        self.assertEqual("".join(activity.outputs), "answer")
        self.assertFalse(activity.reasoning_exposed)


if __name__ == "__main__":
    unittest.main()
