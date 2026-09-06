from __future__ import annotations

import json
import unittest
from pathlib import Path

import yaml

from scripts.core.syntax_repair.adapters import (
    WrongStructuredArtifactError,
    adapter_for,
    classify_wrong_artifacts,
    observe_deterministic_repairs,
)
from workflows.proforma_v1 import reasoning_runtime as rr

try:
    from scripts.core.syntax_repair import repair_structured_output
except ImportError:  # pragma: no cover - only partial-overlay test environments
    repair_structured_output = None


HERE = Path(__file__).resolve().parents[1]
PROMPTS = HERE / "prompts" / "reasoning"

ACTIVE_REASONING_PROMPTS = {
    "diagnosis_who.md": "authority:",
    "diagnosis_icc.md": "authority:",
    "diagnosis_second.md": "authority:",
    "diagnostic_evidence_rescue.md": "assignments:",
    "diagnostic_evidence_audit.md": "audits:",
    "diagnostic_evidence_adjudicate.md": "adjudications:",
    "diagnostic_reasoning_audit.md": "derived_states:",
    "prognosis.md": "domain:",
    "treatment.md": "domain:",
    "biomarker.md": "domain:",
    "germline.md": "domain:",
    "ptbg_evidence_rescue.md": "assignments:",
    "ptbg_evidence_audit.md": "audits:",
    "ptbg_evidence_adjudicate.md": "adjudications:",
    "ptbg_reasoning_audit.md": "derived_states:",
    "dissent_summary.md": "summary:",
}


WHO_MARKDOWN = """# WHO5 Diagnostic Proposal

## W-PROPOSAL-001
schema_disease: MDS with biallelic TP53 inactivation
status: established
root_id: W-CRITERION-004

---

## Atomic Reasoning Graph

### W-CRITERION-004: TP53 biallelic inactivation not met
- Only one TP53 mutation (V1)
- No 17p deletion (C7), no cnLOH (C8)

---

## Final Determination
- Proposed diagnosis: MDS with low blasts and multilineage dysplasia
- root_id: null
"""


class ReasoningSyntaxBoundaryTests(unittest.TestCase):
    def test_whole_markdown_owner_output_is_not_a_syntax_repair_problem(self):
        calls = []

        def repair(prompt, attempt):
            calls.append((prompt, attempt))
            return WHO_MARKDOWN

        if repair_structured_output is None:
            with classify_wrong_artifacts(), self.assertRaises(WrongStructuredArtifactError):
                adapter_for("yaml").deterministic_cleanup(WHO_MARKDOWN)
        else:
            with classify_wrong_artifacts(), self.assertRaises(WrongStructuredArtifactError):
                repair_structured_output(
                    WHO_MARKDOWN,
                    format_name="yaml",
                    model_repair=repair,
                    model_attempts=3,
                )
            self.assertEqual(calls, [], "wrong-artifact output must consume zero syntax-model attempts")

    def test_multiple_yaml_document_sections_are_not_sent_for_local_syntax_repair(self):
        with classify_wrong_artifacts(), self.assertRaises(WrongStructuredArtifactError):
            adapter_for("yaml").deterministic_cleanup("a: 1\n---\nb: 2\n")

    def test_single_yaml_comment_does_not_trigger_markdown_classifier(self):
        cleaned, repairs = adapter_for("yaml").deterministic_cleanup("# comment\na: 1\n")
        self.assertEqual(yaml.safe_load(cleaned), {"a": 1})
        self.assertEqual(repairs, [])

    def test_wrong_artifact_classifier_is_opt_in_and_does_not_change_default_cleanup(self):
        # Without the reasoning guard the shared adapter retains its pre-fix
        # default behavior; default.yaml therefore does not acquire reasoning
        # output classification semantics.
        cleaned, _repairs = adapter_for("yaml").deterministic_cleanup(WHO_MARKDOWN)
        with self.assertRaises(Exception):
            adapter_for("yaml").parse(cleaned)

    def test_fenced_yaml_is_repaired_deterministically_without_changing_values(self):
        raw = "Here is the YAML:\n```yaml\nreason: keep-this-exact-value\ncount: 12\n```\nThanks\n"
        cleaned, repairs = adapter_for("yaml").deterministic_cleanup(raw)
        self.assertEqual(yaml.safe_load(cleaned), {"reason": "keep-this-exact-value", "count": 12})
        self.assertIn("extracted the fenced code block from surrounding prose", repairs)

    def test_colon_space_plain_scalar_is_repaired_deterministically(self):
        cleaned, repairs = adapter_for("yaml").deterministic_cleanup("reason: Case fact C2: 30%\n")
        self.assertEqual(yaml.safe_load(cleaned), {"reason": "Case fact C2: 30%"})
        self.assertIn("quoted YAML plain scalar containing colon-space", repairs)

    def test_provider_can_observe_and_log_deterministic_cleanup_inside_model_runner(self):
        observed = []
        with observe_deterministic_repairs(lambda rows: observed.extend(rows)):
            adapter_for("yaml").deterministic_cleanup("reason: Case fact C2: 30%\n")
        self.assertIn("quoted YAML plain scalar containing colon-space", observed)

    def test_safe_schema_representation_repairs_only_existing_values(self):
        schema = {
            "type": "object",
            "required": ["enabled", "items"],
            "properties": {
                "enabled": {"type": "boolean"},
                "items": {"type": "array", "items": {"type": "string"}},
            },
            "additionalProperties": False,
        }
        normalized = rr.normalize_reasoning_artifact(
            'enabled: "true"\nitems: existing-value\n', fmt="yaml", schema=schema
        )
        self.assertEqual(normalized.document, {"enabled": True, "items": ["existing-value"]})
        self.assertEqual(len(normalized.repairs), 2)

    def test_parseable_bare_list_for_mapping_contract_is_wrong_artifact_type(self):
        schema = {"type": "object", "required": ["assignments"], "properties": {"assignments": {"type": "array"}}}
        normalized = rr.normalize_reasoning_artifact("- rule_id: W-R1\n  card_tag: '[card:aaaaaaaaaaaa]'\n", fmt="yaml", schema=schema)
        self.assertIn("__reasoning_wrong_artifact__", normalized.document)

    def test_wrong_artifact_feedback_is_one_actionable_contract_failure(self):
        schema = {"type": "object", "required": ["authority"], "properties": {"authority": {"type": "string"}}}
        result = rr.audit_atomic_artifact(WHO_MARKDOWN, fmt="yaml", schema=schema)
        self.assertFalse(result.ok)
        self.assertEqual([issue.code for issue in result.issues], ["wrong_artifact_type"])
        self.assertIn("exactly one YAML mapping", result.feedback())
        self.assertNotIn("schema_required", result.feedback())

    def test_all_active_reasoning_prompts_declare_yaml_only_mapping_and_required_envelope(self):
        for name, envelope in ACTIVE_REASONING_PROMPTS.items():
            with self.subTest(prompt=name):
                text = (PROMPTS / name).read_text(encoding="utf-8")
                self.assertIn("## Output serialization contract", text)
                self.assertIn("Return exactly one YAML mapping", text)
                self.assertIn("no Markdown headings", text)
                self.assertIn("no tables", text)
                self.assertIn("no `---` document separators", text)
                self.assertIn("```yaml", text)
                self.assertIn(envelope, text)

    def test_dissent_summary_prompt_no_longer_invites_free_prose_output(self):
        text = (PROMPTS / "dissent_summary.md").read_text(encoding="utf-8")
        contract = text.split("Summarise the supplied immutable decision ledger", 1)[0]
        self.assertIn("summary:", contract)
        self.assertIn("highlights:", contract)
        self.assertIn("Return exactly one YAML mapping", contract)

    def test_other_structured_model_prompts_already_declare_their_output_format(self):
        checks = {
            "structure_case.md": ("Return JSON only", '"provisional_disease"'),
            "report_write.md": ("Return YAML only", "blocks:"),
            "report_preservation.md": ("Return YAML only", "audits:"),
        }
        for name, required in checks.items():
            path = HERE / "prompts" / name
            if not path.is_file():
                continue  # partial changed-files overlay; full repository contains these assets
            text = path.read_text(encoding="utf-8")
            for token in required:
                self.assertIn(token, text, name)

    def test_self_resume_defers_reasoning_artifacts_to_reasoning_aware_hydration(self):
        source = (HERE / "self.py").read_text(encoding="utf-8")
        self.assertIn(
            "if (candidate.execution or {}).get('self_handler') in {'reasoning_model','reasoning_optional_model'}:",
            source,
        )
        marker = source.index("for candidate in workflow.steps:")
        reasoning_skip = source.index("reasoning_optional_model", marker)
        direct_yaml = source.index("staged.yaml.safe_load(raw)", marker)
        self.assertLess(reasoning_skip, direct_yaml)

    def test_self_shared_structure_and_report_handoffs_use_safe_deterministic_cleanup(self):
        source = (HERE / "self.py").read_text(encoding="utf-8")
        self.assertIn("def _self_safe_serialization_cleanup", source)
        self.assertIn("_self_safe_serialization_cleanup('structure',ctx); sr.accept_structured_case", source)
        self.assertIn("_self_safe_serialization_cleanup('report.write',ctx)", source)
        self.assertIn("adapter_for(fmt).deterministic_cleanup(raw)", source)

    def test_self_genuine_parse_error_gets_syntax_only_rehandoff_not_semantic_redo(self):
        source = (HERE / "executors" / "self_executor.py").read_text(encoding="utf-8")
        self.assertIn('normalized.get("__reasoning_parse_error__")', source)
        self.assertIn("Syntax-only repair required", source)
        self.assertIn("Change YAML/JSON serialization only", source)

    def test_default_workflow_is_not_part_of_reasoning_syntax_fix(self):
        default = HERE / "workflow" / "default.yaml"
        if not default.is_file():
            self.skipTest("partial changed-files overlay does not contain unchanged default.yaml")
        reasoning = HERE / "workflow" / "reasoning.yaml"
        self.assertTrue(reasoning.is_file())
        # The fix is implemented in generic serialization infrastructure and
        # reasoning-specific prompts/executors; no workflow graph edit is needed.
        self.assertNotEqual(default.read_bytes(), reasoning.read_bytes())


if __name__ == "__main__":
    unittest.main()
