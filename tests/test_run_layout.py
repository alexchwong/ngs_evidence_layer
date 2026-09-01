from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from scripts import run_layout


class CaseParserTests(unittest.TestCase):
    def test_strict_case_markdown_parses_in_order(self):
        cases = run_layout.parse_case_markdown(
            "# Case 1\n\nAlpha\n\n# Case AML follow-up\n\nBeta\n"
        )
        self.assertEqual([c.title for c in cases], ["1", "AML follow-up"])
        self.assertEqual([c.case_id for c in cases], ["001-1", "002-aml-follow-up"])
        self.assertTrue(cases[0].text.startswith("# Case 1\n"))

    def test_no_heading_is_hard_failure(self):
        with self.assertRaisesRegex(run_layout.LayoutError, "no '# Case <title>' headings"):
            run_layout.parse_case_markdown("A plain single case")

    def test_content_before_first_heading_is_hard_failure(self):
        with self.assertRaisesRegex(run_layout.LayoutError, "content appears before"):
            run_layout.parse_case_markdown("preface\n# Case 1\nCase")

    def test_empty_case_is_hard_failure(self):
        with self.assertRaisesRegex(run_layout.LayoutError, "has no case text"):
            run_layout.parse_case_markdown("# Case 1\n\n# Case 2\ntext")

    def test_duplicate_case_title_is_hard_failure(self):
        with self.assertRaisesRegex(run_layout.LayoutError, "duplicate case title"):
            run_layout.parse_case_markdown("# Case Alpha\na\n# Case alpha\nb")

    def test_case_heading_requires_title(self):
        with self.assertRaisesRegex(run_layout.LayoutError, "non-empty title"):
            run_layout.parse_case_markdown("# Case\ntext")

    def test_case_ids_are_comma_delimited(self):
        self.assertEqual(run_layout.parse_case_ids("1, 2,5"), ["1", "2", "5"])
        with self.assertRaisesRegex(run_layout.LayoutError, "empty entries"):
            run_layout.parse_case_ids("1,,5")
        with self.assertRaisesRegex(run_layout.LayoutError, "duplicate"):
            run_layout.parse_case_ids("1,1")


class LayoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def _write_single(self, run_id: str):
        path = self.root / run_id
        path.mkdir()
        run_layout.write_run_manifest(
            path,
            run_id=run_id,
            workflow="proforma-v1",
            mode="ngs-report",
            pipeline="lmstudio",
            created_at="2026-09-01T00:00:00+00:00",
        )
        return path

    def test_single_run_requires_run_manifest(self):
        path = self._write_single("single-1")
        loc = run_layout.resolve_run(self.root, "single-1")
        self.assertEqual(loc.path, path)
        self.assertFalse(loc.is_batch_child)

    def test_unmanifested_legacy_folder_is_rejected(self):
        (self.root / "old-run").mkdir()
        with self.assertRaisesRegex(run_layout.LayoutError, "unsupported legacy run layout"):
            run_layout.resolve_run(self.root, "old-run")

    def test_batch_child_membership_is_manifest_driven(self):
        batch_id, case_id = "batch-1", "001-case-1"
        batch = self.root / batch_id
        child = batch / case_id
        child.mkdir(parents=True)
        run_layout.write_run_manifest(
            child,
            run_id=f"{batch_id}:{case_id}",
            workflow="proforma-v1",
            mode="ngs-report",
            pipeline="openrouter",
            created_at="2026-09-01T00:00:00+00:00",
            batch_id=batch_id,
            case_id=case_id,
            case_title="Case 1",
        )
        run_layout.write_batch_manifest(batch, {
            "schema_version": 1,
            "kind": "batch",
            "batch_id": batch_id,
            "workflow": "proforma-v1",
            "mode": "ngs-report",
            "pipeline": "openrouter",
            "created_at": "2026-09-01T00:00:00+00:00",
            "children": [{"case_id": case_id, "title": "Case 1", "run_id": f"{batch_id}:{case_id}"}],
        })
        loc = run_layout.resolve_run(self.root, f"{batch_id}:{case_id}")
        self.assertTrue(loc.is_batch_child)
        self.assertEqual(loc.path, child)

    def test_undeclared_child_is_rejected_even_if_folder_exists(self):
        batch_id = "batch-1"
        batch = self.root / batch_id
        batch.mkdir()
        run_layout.write_batch_manifest(batch, {
            "schema_version": 1, "kind": "batch", "batch_id": batch_id,
            "workflow": "proforma-v1", "mode": "ngs-report", "pipeline": "openrouter",
            "created_at": "2026-09-01T00:00:00+00:00", "children": [],
        })
        (batch / "001-orphan").mkdir()
        with self.assertRaisesRegex(run_layout.LayoutError, "does not contain"):
            run_layout.resolve_run(self.root, f"{batch_id}:001-orphan")


if __name__ == "__main__":
    unittest.main()
