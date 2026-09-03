import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML = (ROOT / "ui" / "index.html").read_text(encoding="utf-8")


class UIEnhancementTests(unittest.TestCase):
    def test_eight_named_themes_are_exposed(self):
        expected = {
            "clinical-light",
            "clinical-dark",
            "solarized-light",
            "solarized-dark",
            "nord",
            "gruvbox",
            "aubergine",
            "high-contrast",
        }
        options = set(re.findall(r'<option value="([^"]+)">', HTML))
        self.assertTrue(expected.issubset(options))
        self.assertIn("localStorage", HTML)

    def test_files_are_a_tree_with_an_inspectable_preview(self):
        self.assertIn('class="file-explorer"', HTML)
        self.assertIn("buildFileTree", HTML)
        self.assertIn("renderTreeNode", HTML)
        self.assertIn("/api/file?run=", HTML)
        self.assertIn("file-preview", HTML)

    def test_usage_view_uses_existing_usage_api_and_model_ledger(self):
        self.assertIn('id="usageTab"', HTML)
        self.assertIn("/api/usage?run=", HTML)
        self.assertIn("logs/model-usage.json", HTML)
        self.assertIn("Model time", HTML)

    def test_progress_prefers_workflow_progress_artifact(self):
        self.assertIn("logs/workflow-progress.json", HTML)
        self.assertIn("function renderProgress", HTML)
        # Existing bootstrap stages remain only as a compatibility fallback for old runs.
        self.assertIn("state.boot?.stages", HTML)


if __name__ == "__main__":
    unittest.main()
