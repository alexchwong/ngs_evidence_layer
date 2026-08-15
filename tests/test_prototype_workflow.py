import json
import tempfile
import unittest
from pathlib import Path

from scripts import prototype_workflow, report_audit


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "agreed_reporting_rules.md"
SKILL = ROOT / "SKILL.md"
ANALYSE_REPORT = ROOT / "prompts" / "workflow" / "analyse_report.md"


def draft_for(rules_text, *, tag="a1b2c3"):
    lines = []
    for spec in report_audit.agreed_rule_specs(rules_text):
        rule_id = spec["rule_id"]
        if rule_id == "R0.1":
            lines.append(f"{rule_id} REPORT: Detected variants. (no citation required)")
        else:
            lines.append(f"{rule_id} OMIT: No reportable implication. [card:{tag}]")
    return "\n".join(lines) + "\n"


class PrototypeWorkflowTests(unittest.TestCase):
    def test_rule_slices_are_canonical_subsets(self):
        source = RULES.read_text(encoding="utf-8")
        dx = prototype_workflow.slice_rules_text(source, {0, 1})
        remainder = prototype_workflow.slice_rules_text(source, {2, 3, 4, 5})
        self.assertTrue(all(s["rule_id"].startswith(("R0.", "R1.")) for s in report_audit.agreed_rule_specs(dx)))
        self.assertTrue(all(s["rule_id"].startswith(("R2.", "R3.", "R4.", "R5.")) for s in report_audit.agreed_rule_specs(remainder)))


    def test_generated_rule_views_have_purpose_built_intros(self):
        source = RULES.read_text(encoding="utf-8")
        dx = prototype_workflow.slice_rules_text(source, {0, 1})
        remainder = prototype_workflow.slice_rules_text(source, {2, 3, 4, 5})
        full = prototype_workflow.slice_rules_text(source, set(range(0, 6)))

        self.assertTrue(dx.startswith("# Diagnosis-pass reporting rules\n"))
        self.assertTrue(remainder.startswith("# Downstream reporting rules\n"))
        self.assertTrue(full.startswith("# Full reporting-rule re-analysis\n"))
        for view in (dx, remainder, full):
            self.assertNotIn("# Agreed reporting rules for interpretative myeloid NGS summaries", view)
            self.assertNotIn("# Style requirements", view)
            self.assertIn("## REPORT versus OMIT classification", view)
            self.assertIn("## Citation contract", view)
            self.assertIn("Rule-draft citation contract", view)

    def test_patient_level_style_is_copied_verbatim_from_legacy_skill_6a(self):
        skill = SKILL.read_text(encoding="utf-8")
        start = skill.index("#### Patient-level conclusion and qualifier style")
        end = skill.index("\n\nRead only:", start)
        expected = skill[start:end].rstrip()
        source = RULES.read_text(encoding="utf-8")
        for sections in ({0, 1}, {2, 3, 4, 5}, set(range(0, 6))):
            view = prototype_workflow.slice_rules_text(source, sections)
            self.assertIn(expected, view)

    def test_report_omit_taxonomy_is_copied_verbatim_from_legacy_6a_prompt(self):
        analyse = ANALYSE_REPORT.read_text(encoding="utf-8")
        start = analyse.index("## REPORT versus OMIT classification")
        end = analyse.index("\n\n## Task-specific rules", start)
        expected = analyse[start:end].rstrip()
        source = RULES.read_text(encoding="utf-8")
        for sections in ({0, 1}, {2, 3, 4, 5}, set(range(0, 6))):
            view = prototype_workflow.slice_rules_text(source, sections)
            self.assertIn(expected, view)

    def test_terminal_refined_cmc_is_strict_and_canonical(self):
        source = RULES.read_text(encoding="utf-8")
        dx_rules = prototype_workflow.slice_rules_text(source, {0, 1})
        text = draft_for(dx_rules) + "REFINED_CMC: AML\n"
        rule_text, cmc = prototype_workflow.split_diagnosis_draft(text)
        self.assertEqual(cmc, "AML")
        self.assertNotIn("REFINED_CMC", rule_text)
        with self.assertRaisesRegex(ValueError, "not canonical"):
            prototype_workflow.split_diagnosis_draft(
                draft_for(dx_rules) + "REFINED_CMC: imaginary disease\n"
            )

    def test_assemble_uses_dx_plus_remainder_when_cmc_unchanged(self):
        source = RULES.read_text(encoding="utf-8")
        dx_rules = prototype_workflow.slice_rules_text(source, {0, 1})
        rem_rules = prototype_workflow.slice_rules_text(source, {2, 3, 4, 5})
        evidence = "# Evidence\n\n- [card:a1b2c3]: Fixture.\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "case-input.json").write_text(json.dumps({"case_major_category": "AML"}), encoding="utf-8")
            (tmp / "dx.md").write_text(draft_for(dx_rules) + "REFINED_CMC: AML\n", encoding="utf-8")
            (tmp / "rem.md").write_text(draft_for(rem_rules), encoding="utf-8")
            (tmp / "evidence.md").write_text(evidence, encoding="utf-8")
            out, changed, refined = prototype_workflow.assemble_report_draft(
                tmp / "case-input.json", tmp / "dx.md", tmp / "rem.md",
                tmp / "out.md", tmp / "evidence.md", RULES,
            )
            self.assertFalse(changed)
            self.assertEqual(refined, "AML")
            self.assertNotIn("REFINED_CMC", out.read_text(encoding="utf-8"))

    def test_assemble_replaces_dx_when_cmc_changed(self):
        source = RULES.read_text(encoding="utf-8")
        dx_rules = prototype_workflow.slice_rules_text(source, {0, 1})
        full_draft = draft_for(source)
        evidence = "# Evidence\n\n- [card:a1b2c3]: Fixture.\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "case-input.json").write_text(json.dumps({"case_major_category": "MDS"}), encoding="utf-8")
            (tmp / "dx.md").write_text(draft_for(dx_rules) + "REFINED_CMC: AML\n", encoding="utf-8")
            (tmp / "rem.md").write_text(full_draft, encoding="utf-8")
            (tmp / "evidence.md").write_text(evidence, encoding="utf-8")
            out, changed, refined = prototype_workflow.assemble_report_draft(
                tmp / "case-input.json", tmp / "dx.md", tmp / "rem.md",
                tmp / "out.md", tmp / "evidence.md", RULES,
            )
            self.assertTrue(changed)
            self.assertEqual(refined, "AML")
            self.assertEqual(out.read_text(encoding="utf-8"), full_draft)


if __name__ == "__main__":
    unittest.main()
