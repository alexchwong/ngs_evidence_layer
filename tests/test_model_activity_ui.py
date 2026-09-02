import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from ui import workflow_server


class ModelActivityUITests(unittest.TestCase):
    def test_ui_child_environment_enables_transient_streaming(self):
        env = workflow_server._ui_child_env()
        self.assertEqual(env["NEL_MODEL_STREAM"], "1")
        self.assertEqual(env["NEL_MODEL_ACTIVITY_DIR"], str(workflow_server.MODEL_ACTIVITY_DIR))

    def test_activity_tail_returns_only_new_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            activity_dir = Path(tmp)
            with mock.patch.object(workflow_server, "MODEL_ACTIVITY_DIR", activity_dir), \
                 mock.patch.object(workflow_server.batch, "_top_kind", return_value="run"), \
                 mock.patch.object(workflow_server.batch, "_run_location", return_value=SimpleNamespace()):
                path = workflow_server._model_activity_path("run-1")
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("first\n", encoding="utf-8")
                first = workflow_server.model_activity("run-1", 0)
                self.assertEqual(first["text"], "first\n")
                with path.open("a", encoding="utf-8") as handle:
                    handle.write("second\n")
                second = workflow_server.model_activity("run-1", first["offset"])
                self.assertEqual(second["text"], "second\n")


    def test_activity_files_are_cleared_as_transient_session_state(self):
        with tempfile.TemporaryDirectory() as tmp:
            activity_dir = Path(tmp)
            (activity_dir / "one.jsonl").write_text("x\n", encoding="utf-8")
            (activity_dir / "keep.txt").write_text("x\n", encoding="utf-8")
            with mock.patch.object(workflow_server, "MODEL_ACTIVITY_DIR", activity_dir):
                workflow_server._clear_model_activity()
            self.assertFalse((activity_dir / "one.jsonl").exists())
            self.assertTrue((activity_dir / "keep.txt").exists())

    def test_batch_parent_has_no_model_activity_stream(self):
        with mock.patch.object(workflow_server.batch, "_top_kind", return_value="batch"):
            self.assertEqual(
                workflow_server.model_activity("batch-1", 0),
                {"offset": 0, "text": "", "size": 0},
            )

    def test_page_injects_model_activity_asset(self):
        self.assertEqual(
            workflow_server._MODEL_ACTIVITY_SCRIPT,
            '<script src="/assets/model-activity.js"></script>',
        )

    def test_page_injects_role_reasoning_asset(self):
        self.assertEqual(
            workflow_server._ROLE_REASONING_SCRIPT,
            '<script src="/assets/role-reasoning.js"></script>',
        )

    def test_role_reasoning_is_copied_into_composed_profile(self):
        doc = {"model_roles": {"diagnosis": {"model": "main", "max_tokens": 100}}}
        workflow_server._apply_role_reasoning(
            doc,
            {"roles": {"diagnosis": {"reasoning": "high"}}},
        )
        self.assertEqual(doc["model_roles"]["diagnosis"]["reasoning"], "high")

    def test_invalid_role_reasoning_is_rejected(self):
        doc = {"model_roles": {"diagnosis": {"model": "main", "max_tokens": 100}}}
        with self.assertRaises(workflow_server.base.UIError):
            workflow_server._apply_role_reasoning(
                doc,
                {"roles": {"diagnosis": {"reasoning": "ultra"}}},
            )

    def test_lmstudio_allows_documented_reasoning_levels(self):
        doc = {"model_roles": {"diagnosis": {"reasoning": "high"}}}
        workflow_server._validate_provider_reasoning(doc, "lmstudio")

    def test_lmstudio_rejects_openrouter_only_reasoning_levels(self):
        doc = {"model_roles": {"diagnosis": {"reasoning": "xhigh"}}}
        with self.assertRaisesRegex(workflow_server.base.UIError, "not supported for LM Studio"):
            workflow_server._validate_provider_reasoning(doc, "lmstudio")

    def test_other_provider_requires_default_reasoning(self):
        doc = {"model_roles": {"diagnosis": {"reasoning": "low"}}}
        with self.assertRaisesRegex(workflow_server.base.UIError, "must be Default"):
            workflow_server._validate_provider_reasoning(doc, "other")


if __name__ == "__main__":
    unittest.main()
