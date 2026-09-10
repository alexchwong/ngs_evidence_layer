from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflows.proforma_v1.engine import prompt_renderer, transforms


ROOT = Path(__file__).resolve().parents[1]


class DefaultDissentSummaryTests(unittest.TestCase):
    def _ledger(self):
        return {
            "schema_version": 2,
            "issues": [
                {
                    "id": "D001",
                    "issue_key": "internal:evidence:one",
                    "reviewed_text": "TP53 mutation is independently adverse in this case.",
                    "status": "resolved",
                    "history": [
                        {
                            "stage": "evidence audit",
                            "event": "raised",
                            "reason": ["The cited evidence supports adverse risk only for biallelic TP53."],
                            "resolution_recommendation": ["Reconsider the statement."],
                        },
                        {
                            "stage": "evidence adjudication",
                            "event": "addressed",
                            "action": ["Do not retain the monoallelic adverse-risk statement."],
                            "outcome": ["The unsupported adverse-risk statement was removed."],
                        },
                    ],
                },
                {
                    "id": "D002",
                    "issue_key": "internal:evidence:two",
                    "reviewed_text": "TP53 mutation is independently adverse in this case.",
                    "status": "resolved",
                    "history": [
                        {
                            "stage": "retry audit",
                            "event": "raised",
                            "reason": ["The same monoallelic-versus-biallelic concern remained."],
                        }
                    ],
                },
            ],
        }

    def test_canonical_ledger_packet_is_actually_rendered_into_model_prompt(self):
        from workflows.proforma_v1.engine import dissent as workflow_dissent

        with tempfile.TemporaryDirectory() as td, patch.object(workflow_dissent, "doc", return_value=self._ledger()):
            packet = transforms.workflow_dissent_packet(None, {"__work__": td}, {})

        prompt = prompt_renderer.render(
            ROOT / "prompts" / "dissent_summary.md",
            root=ROOT,
            inputs={"dissent_items": packet, "audit_feedback": None},
        )

        self.assertEqual([row["id"] for row in packet], ["D001", "D002"])
        self.assertNotIn("issue_key", packet[0])
        self.assertIn("D001", prompt)
        self.assertIn("D002", prompt)
        self.assertIn("TP53 mutation is independently adverse in this case.", prompt)
        self.assertIn("supports adverse risk only for biallelic TP53", prompt)
        self.assertIn("unsupported adverse-risk statement was removed", prompt)
        self.assertNotIn("{{ input.dissent_items }}", prompt)


    def test_validator_returns_precise_retry_feedback_for_missing_ids(self):
        packet = [
            {"id": "D001", "statement": "One.", "status": "open", "history": []},
            {"id": "D002", "statement": "Two.", "status": "open", "history": []},
            {"id": "D003", "statement": "Three.", "status": "open", "history": []},
        ]
        summary = {
            "summaries": [
                {
                    "source_issue_ids": ["D001"],
                    "statement": "One.",
                    "concern_critique": "Concern.",
                    "decision_and_basis": "Unresolved.",
                },
                {
                    "source_issue_ids": ["D002"],
                    "statement": "Two.",
                    "concern_critique": "Concern.",
                    "decision_and_basis": "Unresolved.",
                },
            ]
        }
        result = transforms.workflow_validate_dissent_summary(
            None,
            {
                "workflow_dissent_packet": packet,
                "workflow_dissent_summary": summary,
            },
            {},
        )
        self.assertEqual(result["status"], "fail")
        self.assertIn("missing D003", result["feedback"])
        self.assertIn("every supplied source issue ID exactly once", result["feedback"])

        prompt = prompt_renderer.render(
            ROOT / "prompts" / "dissent_summary.md",
            root=ROOT,
            inputs={"dissent_items": packet, "audit_feedback": result["feedback"]},
        )
        self.assertIn("missing D003", prompt)
        self.assertIn("Deterministic retry feedback", prompt)

    def test_valid_complete_summary_replaces_root_dissent_markdown(self):
        packet = [
            {"id": "D001", "statement": "Shared statement.", "status": "resolved", "history": []},
            {"id": "D002", "statement": "Shared statement.", "status": "resolved", "history": []},
        ]
        summary = {
            "summaries": [
                {
                    "source_issue_ids": ["D001", "D002"],
                    "statement": "Shared statement.",
                    "concern_critique": "Two related concerns were raised.",
                    "decision_and_basis": "The final recorded action resolved both concerns.",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "dissent.md"
            target.write_text("deterministic fallback\n", encoding="utf-8")
            result = transforms.workflow_render_dissent_summary(
                None,
                {
                    "__work__": td,
                    "workflow_dissent_packet": packet,
                    "workflow_dissent_summary": summary,
                },
                {},
            )
            rendered = target.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "summarized")
        self.assertEqual(rendered.count("**Statement:**"), 1)
        self.assertIn("**Concern / Critique:** Two related concerns were raised.", rendered)
        self.assertIn("**Decision and Basis:** The final recorded action resolved both concerns.", rendered)
        self.assertNotIn("D001", rendered)
        self.assertNotIn("D002", rendered)

    def test_incomplete_or_invalid_summary_keeps_deterministic_fallback(self):
        packet = [
            {"id": "D001", "statement": "Statement one.", "status": "resolved", "history": []},
            {"id": "D002", "statement": "Statement two.", "status": "open", "history": []},
        ]
        incomplete = {
            "summaries": [
                {
                    "source_issue_ids": ["D001"],
                    "statement": "Statement one.",
                    "concern_critique": "Concern.",
                    "decision_and_basis": "Decision.",
                }
            ]
        }
        with tempfile.TemporaryDirectory() as td:
            target = Path(td) / "dissent.md"
            target.write_text("deterministic fallback\n", encoding="utf-8")
            result = transforms.workflow_render_dissent_summary(
                None,
                {
                    "__work__": td,
                    "workflow_dissent_packet": packet,
                    "workflow_dissent_summary": incomplete,
                },
                {},
            )
            rendered = target.read_text(encoding="utf-8")

        self.assertEqual(result["status"], "deterministic_fallback")
        self.assertIn("missing D002", result["reason"])
        self.assertEqual(rendered, "deterministic fallback\n")

    def test_duplicate_or_unknown_source_issue_ids_are_rejected(self):
        packet = [{"id": "D001", "statement": "Statement.", "status": "open", "history": []}]
        duplicate = {
            "summaries": [
                {
                    "source_issue_ids": ["D001"],
                    "statement": "Statement.",
                    "concern_critique": "Concern one.",
                    "decision_and_basis": "Decision one.",
                },
                {
                    "source_issue_ids": ["D001"],
                    "statement": "Statement.",
                    "concern_critique": "Concern two.",
                    "decision_and_basis": "Decision two.",
                },
            ]
        }
        rows, error = transforms._workflow_dissent_summary_rows(packet, duplicate)
        self.assertEqual(rows, [])
        self.assertIn("more than one summary row", error)

        unknown = {
            "summaries": [
                {
                    "source_issue_ids": ["D999"],
                    "statement": "Statement.",
                    "concern_critique": "Concern.",
                    "decision_and_basis": "Decision.",
                }
            ]
        }
        rows, error = transforms._workflow_dissent_summary_rows(packet, unknown)
        self.assertEqual(rows, [])
        self.assertIn("unknown D999", error)


if __name__ == "__main__":
    unittest.main()
