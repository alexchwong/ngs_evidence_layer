import tempfile
import unittest
from pathlib import Path

import yaml

from tests.test_report_citations import CARD_TAGS, EVIDENCE
from workflows.diagnosis_first_v1 import report_yaml


class DiagnosisFirstYamlTests(unittest.TestCase):
    def _write(self, path, value):
        path.write_text(yaml.safe_dump(value, sort_keys=False), encoding="utf-8")

    def _draft(self):
        return {
            "schema_version": 1,
            "rules": [
                {
                    "id": "R0.1",
                    "omit": False,
                    "statements": [
                        {"text": "NPM1 mutation was detected.", "citation": "(no citation required)"}
                    ],
                },
                {
                    "id": "R1.1",
                    "omit": False,
                    "statements": [
                        {
                            "text": "The diagnosis is AML with mutated NPM1.",
                            "citation": "[card:a1b2c3][card:d4e5f6]",
                        },
                        {
                            "text": "A second retained fact is supported independently.",
                            "citation": "[card:b1c2d3]",
                        },
                    ],
                },
            ],
        }

    def _summary_template(self):
        document = {"schema_version": 1}
        for section in report_yaml.SUMMARY_SECTIONS:
            document[section] = {"statements": [{"text": "", "citation": ""}]}
        return document


    def test_summary_accepts_zero_statements_in_every_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._write(tmp / "draft.yaml", self._draft())
            summary = {
                "schema_version": 1,
                **{section: {"statements": []} for section in report_yaml.SUMMARY_SECTIONS},
            }
            self._write(tmp / "summary.yaml", summary)
            parsed = report_yaml.validate_summary(tmp / "summary.yaml", tmp / "draft.yaml")
            self.assertTrue(all(parsed[section] == [] for section in report_yaml.SUMMARY_SECTIONS))

    def test_summary_rejects_partial_source_citation_set(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._write(tmp / "draft.yaml", self._draft())
            summary = self._summary_template()
            summary["detected_variants"]["statements"] = [
                {"text": "NPM1 mutation was detected.", "citation": "(no citation required)"}
            ]
            summary["diagnosis"]["statements"] = [
                {"text": "The diagnosis is AML with mutated NPM1.", "citation": "[card:a1b2c3]"}
            ]
            self._write(tmp / "summary.yaml", summary)
            with self.assertRaisesRegex(ValueError, "not an exact union"):
                report_yaml.validate_summary(tmp / "summary.yaml", tmp / "draft.yaml")

    def test_summary_accepts_union_of_complete_source_citation_sets(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._write(tmp / "draft.yaml", self._draft())
            summary = self._summary_template()
            summary["detected_variants"]["statements"] = [
                {"text": "NPM1 mutation was detected.", "citation": "(no citation required)"}
            ]
            summary["diagnosis"]["statements"] = [
                {
                    "text": "The diagnosis and second retained fact are summarised together.",
                    "citation": "[card:a1b2c3][card:d4e5f6][card:b1c2d3]",
                }
            ]
            self._write(tmp / "summary.yaml", summary)
            parsed = report_yaml.validate_summary(tmp / "summary.yaml", tmp / "draft.yaml")
            self.assertEqual(len(parsed["diagnosis"]), 1)

    def test_render_summary_allows_multiple_sentences_per_structured_statement(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._write(tmp / "draft.yaml", self._draft())
            summary = self._summary_template()
            summary["diagnosis"]["statements"] = [
                {
                    "text": (
                        "ELN 2022 risk classification applies. "
                        "NPM1-mutated AML is favorable risk in this setting. "
                        "FLT3-TKD does not add an ELN 2022 adverse-risk assignment."
                    ),
                    "citation": "[card:a1b2c3][card:d4e5f6]",
                }
            ]
            self._write(tmp / "summary.yaml", summary)
            (tmp / "evidence.md").write_text(EVIDENCE, encoding="utf-8")
            (tmp / "card-tags.json").write_text(CARD_TAGS, encoding="utf-8")
            output = tmp / "report-final.md"

            report_yaml.render_summary(
                tmp / "summary.yaml",
                tmp / "draft.yaml",
                tmp / "evidence.md",
                tmp / "card-tags.json",
                output,
            )

            rendered = output.read_text(encoding="utf-8")
            self.assertIn("ELN 2022 risk classification applies. NPM1-mutated AML is favorable risk", rendered)
            self.assertIn("FLT3-TKD does not add an ELN 2022 adverse-risk assignment [1].", rendered)

    def test_render_summary_writes_final_markdown_and_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            self._write(tmp / "draft.yaml", self._draft())
            summary = self._summary_template()
            summary["detected_variants"]["statements"] = [
                {"text": "NPM1 mutation was detected.", "citation": "(no citation required)"}
            ]
            summary["diagnosis"]["statements"] = [
                {
                    "text": "The diagnosis is AML with mutated NPM1.",
                    "citation": "[card:a1b2c3][card:d4e5f6]",
                }
            ]
            self._write(tmp / "summary.yaml", summary)
            (tmp / "evidence.md").write_text(EVIDENCE, encoding="utf-8")
            (tmp / "card-tags.json").write_text(CARD_TAGS, encoding="utf-8")
            output = tmp / "report-final.md"
            report_yaml.render_summary(
                tmp / "summary.yaml",
                tmp / "draft.yaml",
                tmp / "evidence.md",
                tmp / "card-tags.json",
                output,
            )
            rendered = output.read_text(encoding="utf-8")
            self.assertIn("NPM1 mutation was detected.", rendered)
            self.assertIn("The diagnosis is AML with mutated NPM1 [1].", rendered)
            self.assertIn("## References", rendered)
            self.assertEqual(rendered.count("Alpha A. First paper."), 1)


if __name__ == "__main__":
    unittest.main()
