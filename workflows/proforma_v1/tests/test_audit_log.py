from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from workflows.proforma_v1.engine import audit_log
from workflows.proforma_v1.engine.workflow_compiler import compile_workflow

HERE = Path(__file__).resolve().parents[1]


class AuditLogPacketTests(unittest.TestCase):
    def test_packet_folds_challenge_into_owner_decision_and_deduplicates_evidence(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            registry = {
                "v01": {"gene": "SF3B1", "description": "p.K700E", "variant_id": "V1"},
                "v02": {"gene": "TP53", "description": "p.R248Q", "variant_id": "V2"},
            }
            card = {
                "card_id": "CARD-1",
                "category": "prognosis",
                "genes": ["SF3B1"],
                "diseases": ["MDS"],
                "evidence_tier": "guideline",
                "interpretation": "SF3B1-mutated MDS has favorable prognostic significance in the stated context.",
            }
            domains = {
                "prognosis": {
                    "framework_favorable": [{
                        "variants": ["v01"],
                        "reason": "v01 is favorable in this prognostic framework.",
                        "evidence_card_tags": ["[card:aaaaaaaaaaaa]"],
                    }],
                    "no_prognostic_evidence": [{
                        "variants": ["v02"],
                        "reason": "No separate prognostic effect was identified for v02.",
                        "evidence_card_tags": [],
                    }],
                }
            }
            supported = [{
                "schema_id": "PX-FRAMEWORK_FAVORABLE-01",
                "domain": "prognosis",
                "reason": "v01 is favorable in this prognostic framework.",
                "variants": ["v01"],
                "evidence": [{
                    "card_id": "CARD-1",
                    "card_tag": "[card:aaaaaaaaaaaa]",
                    "audit_comments": [],
                }],
            }]
            context = {
                "__work__": work,
                "registry": registry,
                "diagnosis": {},
                "domains": domains,
                "supported": supported,
                "all_cards": [card],
                "manifest": {},
            }
            issue = {
                "id": "D001",
                "issue_key": "evidence-warning:PX-FRAMEWORK_FAVORABLE-01:[card:aaaaaaaaaaaa]",
                "reviewed_text": "Reason: v01 is favorable in this prognostic framework. Card: [card:aaaaaaaaaaaa]",
                "status": "resolved",
                "history": [
                    {
                        "stage": "evidence audit comparison",
                        "event": "raised",
                        "reason": [
                            "Resolver: include; auditor: exclude.",
                            "The evidence required context qualification.",
                        ],
                    },
                    {
                        "stage": "evidence adjudication",
                        "event": "addressed",
                        "action": ["Adjudicator decided to include the disputed card."],
                        "outcome": ["The evidence was retained after review."],
                    },
                ],
            }
            with patch.object(audit_log.workflow_dissent, "doc", return_value={"issues": [issue]}), \
                 patch("workflows.proforma_v1.card_identity.tag_by_id", return_value={"CARD-1": "aaaaaaaaaaaa"}):
                packet = audit_log.audit_log_packet(None, context, {})

            decisions = [row for row in packet if row.get("decision_id")]
            self.assertEqual(len(decisions), 2)
            self.assertFalse(any(str(row.get("decision_id", "")).startswith("dissent:") for row in packet))

            favorable = next(row for row in decisions if "SF3B1 p.K700E" in row["reason"])
            negative = next(row for row in decisions if "TP53 p.R248Q" in row["reason"])
            self.assertEqual(favorable["final_disposition"], "reported")
            self.assertEqual(negative["final_disposition"], "considered_not_reported")

            self.assertEqual(len(favorable["evidence"]), 1)
            evidence = favorable["evidence"][0]
            self.assertEqual(evidence["interpretation"], card["interpretation"])
            self.assertEqual(evidence["final_status"], "accepted")
            self.assertTrue(evidence.get("review"))

            # Model-facing packet intentionally omits runtime/card provenance noise.
            rendered = repr(packet)
            for forbidden in ("card_tag", "publication_key", "evidence_tier", "_path", "_variant_ids"):
                self.assertNotIn(forbidden, rendered)

    def test_unmatched_review_context_does_not_become_a_coverage_unit(self):
        packet = [
            {"decision_id": "owner:prognosis:a", "domain": "prognosis", "reason": "A"},
            {"kind": "review_context", "domain": "cross-domain", "statement": "Unmatched review"},
        ]
        summary = {
            "summaries": [{
                "source_decision_ids": ["owner:prognosis:a"],
                "domain": "prognosis",
                "topic": "Grouped prognosis",
                "summary": "Model-authored summary.",
            }]
        }
        result = audit_log.audit_log_validate_summary(None, {
            "workflow_audit_log_packet": packet,
            "workflow_audit_log_summary": summary,
        }, {})
        self.assertEqual(result["status"], "pass")
        self.assertEqual(result["source_decisions"], 1)

    def test_summary_validation_checks_only_structural_owner_decision_coverage(self):
        packet = [
            {"decision_id": "owner:prognosis:a"},
            {"decision_id": "owner:prognosis:b"},
        ]
        summary = {
            "summaries": [{
                "source_decision_ids": ["owner:prognosis:a", "owner:prognosis:b"],
                "domain": "prognosis",
                "topic": "Grouped prognosis",
                "summary": "Any packet-faithful model prose is structurally acceptable.",
            }]
        }
        result = audit_log.audit_log_validate_summary(None, {
            "workflow_audit_log_packet": packet,
            "workflow_audit_log_summary": summary,
        }, {})
        self.assertEqual(result["status"], "pass")

        duplicate = {"summaries": [
            dict(summary["summaries"][0], source_decision_ids=["owner:prognosis:a"]),
            {
                "source_decision_ids": ["owner:prognosis:a", "owner:prognosis:b"],
                "domain": "prognosis", "topic": "Second group", "summary": "More prose.",
            },
        ]}
        result = audit_log.audit_log_validate_summary(None, {
            "workflow_audit_log_packet": packet,
            "workflow_audit_log_summary": duplicate,
        }, {})
        self.assertEqual(result["status"], "fail")

    def test_render_replaces_default_user_facing_dissent_artifact(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            (work / "dissent.md").write_text("legacy", encoding="utf-8")
            packet = [{"decision_id": "owner:treatment:a"}]
            summary = {"summaries": [{
                "source_decision_ids": ["owner:treatment:a"],
                "domain": "treatment",
                "topic": "Treatment assessment",
                "summary": "No reportable treatment implication was retained.",
            }]}
            result = audit_log.audit_log_render(None, {
                "__work__": work,
                "workflow_audit_log_packet": packet,
                "workflow_audit_log_summary": summary,
            }, {})
            self.assertEqual(result["status"], "summarized")
            self.assertTrue((work / "audit-log.md").is_file())
            self.assertFalse((work / "dissent.md").exists())


class AuditLogDefaultWorkflowTests(unittest.TestCase):
    def test_default_workflow_uses_audit_log_tail(self):
        workflow = compile_workflow(HERE / "workflow" / "default.yaml")
        ids = {step.id for step in workflow.steps}
        self.assertTrue({
            "audit_log.packet",
            "audit_log.summarize",
            "audit_log.summary.validate",
            "audit_log.render",
        }.issubset(ids))
        self.assertFalse(any(step_id.startswith("dissent.") for step_id in ids))


if __name__ == "__main__":
    unittest.main()
