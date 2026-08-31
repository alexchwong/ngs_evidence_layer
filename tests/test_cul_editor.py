#!/usr/bin/env python3
"""Tests for the standalone Corpus User Layer editor artefact."""
from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "cul.py"
spec = importlib.util.spec_from_file_location("cul_cli", SCRIPT)
cul = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cul)


class CULEditorTests(unittest.TestCase):
    def test_literal_edit_flag_builds_separate_editor_without_touching_browser(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp_root = Path(tmp)
            editor = tmp_root / "config" / "cul" / "corpus-user-layer.html"
            browser = tmp_root / "output" / "reports" / "card-browser.html"
            browser.parent.mkdir(parents=True)
            browser.write_text("READ ONLY SENTINEL", encoding="utf-8")

            with mock.patch.object(cul, "EDITOR_HTML", editor), mock.patch.object(
                cul, "READ_ONLY_BROWSER_HTML", browser
            ):
                rc = cul.main(["--edit", "--no-open", "--no-watch"])

            self.assertEqual(rc, 0)
            self.assertTrue(editor.is_file())
            self.assertEqual(browser.read_text(encoding="utf-8"), "READ ONLY SENTINEL")

            html = editor.read_text(encoding="utf-8")
            self.assertIn('document.title = "Corpus User Layer"', html)
            self.assertIn("Review changes", html)
            self.assertIn("Download profile", html)
            self.assertIn("Copy citation", html)
            self.assertIn("buildEditorPane", html)
            self.assertIn("Retrieval rules", html)
            self.assertIn('{ key:"category", title:"Category"', html)
            self.assertIn('{ key:"paper",    title:"Paper"', html)
            self.assertIn(
                "body.edit-mode .shell{grid-template-columns:250px minmax(0,1fr) minmax(18rem,22rem)}",
                html,
            )
            self.assertIn('"editor":true', html)

    def test_edit_subcommand_remains_an_alias(self):
        parser = cul.build_parser()
        args = parser.parse_args(["edit", "--no-open", "--no-watch"])
        self.assertIs(args.func, cul.cmd_edit)


if __name__ == "__main__":
    unittest.main()
