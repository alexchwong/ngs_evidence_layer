"""Regression tests for the browser-interface UX enhancement layer."""
from __future__ import annotations

import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

from ui import enhancements
from ui import server


ROOT = Path(__file__).resolve().parents[1]


class AliasAndSecretTests(unittest.TestCase):
    def test_aliases_used_in_openrouter_profiles_are_valid(self):
        self.assertEqual(server.validate_alias_name("gptoss20b"), "gptoss20b")
        self.assertEqual(server.validate_alias_name("qwen_next"), "qwen_next")
        self.assertEqual(server.validate_alias_name("qwen-next"), "qwen-next")

    def test_alias_with_space_has_specific_error(self):
        with self.assertRaisesRegex(ValueError, "Model alias.*no spaces"):
            server.validate_alias_name("qwen next")

    def test_profile_filename_error_is_not_described_as_model_name(self):
        with self.assertRaises(server.UIError) as caught:
            server.pipeline_path("openai/gpt-oss-20b")
        self.assertIn("Profile file name", caught.exception.message)
        self.assertIn("not an OpenRouter model ID", caught.exception.message)

    def test_secret_mask_never_returns_full_secret(self):
        secret = "sk-or-v1-abcdefghijklmnopqrstuvwxyz"
        masked = server.mask_secret(secret)
        self.assertTrue(masked.startswith(secret[:8]))
        self.assertTrue(masked.endswith(secret[-4:]))
        self.assertNotEqual(masked, secret)
        self.assertNotIn(secret, masked)


class RetryPolicyTests(unittest.TestCase):
    def test_run_failure_retries_up_to_three_attempts_total(self):
        self.assertTrue(server.should_retry(phase="run", returncode=1, attempt=1))
        self.assertTrue(server.should_retry(phase="run", returncode=1, attempt=2))
        self.assertFalse(server.should_retry(phase="run", returncode=1, attempt=3))

    def test_setup_failures_are_not_retried(self):
        self.assertFalse(server.should_retry(phase="setup", returncode=1, attempt=1))

    def test_deterministic_config_failure_is_not_retried(self):
        self.assertFalse(
            server.should_retry(
                phase="run", returncode=1, attempt=1,
                output="nel failed: configuration check failed: missing profile",
            )
        )

    def test_manual_stop_suppresses_retry(self):
        self.assertFalse(
            server.should_retry(
                phase="run", returncode=-15, attempt=1, stop_requested=True
            )
        )


class RetryRegistryIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.console = Path(tempfile.mkdtemp())
        self.original_console = server.CONSOLE_DIR
        server.CONSOLE_DIR = self.console

    def tearDown(self):
        server.CONSOLE_DIR = self.original_console
        shutil.rmtree(self.console, ignore_errors=True)

    def _wait_inactive(self, registry, run_id, timeout=4.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            child = registry.get(run_id)
            if child is not None and not child.active:
                return child
            time.sleep(0.05)
        self.fail(f"run {run_id} did not become inactive")

    def test_registry_retries_failed_run_three_attempts_total(self):
        registry = server.Registry()
        argv = [sys.executable, "-u", "-c", "raise SystemExit(7)"]
        registry.start(argv, run_id="retry-test", phase="run", exclusive=False)
        child = self._wait_inactive(registry, "retry-test")
        self.assertEqual(child.attempt, 3)
        self.assertEqual(child.returncode, 7)
        log = server.console_path("retry-test").read_text(encoding="utf-8")
        self.assertIn("attempt 1/3", log)
        self.assertIn("attempt 2/3", log)
        self.assertIn("attempt 3/3", log)

    def test_manual_stop_cancels_automatic_retry(self):
        registry = server.Registry()
        argv = [sys.executable, "-u", "-c", "import time; time.sleep(10)"]
        registry.start(argv, run_id="stop-test", phase="run", exclusive=False)
        result = registry.stop("stop-test")
        self.assertTrue(result["stopped"])
        child = self._wait_inactive(registry, "stop-test")
        self.assertEqual(child.attempt, 1)
        self.assertTrue(child.stop_requested)


class BundledCaseTests(unittest.TestCase):
    def test_preview_uses_clinical_input_only(self):
        doc = enhancements._case_preview(server, "nel-demo", "1")
        self.assertTrue(doc["text"].strip())
        self.assertNotIn("Marking criteria", doc["text"])
        self.assertNotIn("NEL task", doc["text"])


class StaticUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.html = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")

    def test_rhs_is_fixed_thirty_seventy_split(self):
        self.assertIn("grid-template-rows:30% 70%", self.html)

    def test_console_and_dissent_are_first_class_middle_views(self):
        self.assertIn('id="consoleTab"', self.html)
        self.assertIn('id="dissentTab"', self.html)

    def test_delete_uses_dialog_not_typed_prompt(self):
        self.assertIn('id="deleteDialog"', self.html)
        self.assertNotIn("window.prompt", self.html)

    def test_theme_toggle_and_workbench_title_exist(self):
        self.assertIn("NGS Evidence Layer", self.html)
        self.assertIn('id="themeToggle"', self.html)

    def test_bundled_case_preview_is_read_only(self):
        self.assertIn('id="casePreview" class="case-preview" readonly', self.html)


if __name__ == "__main__":
    unittest.main()
