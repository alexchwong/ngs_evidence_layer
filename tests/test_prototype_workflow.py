import json
import tempfile
import unittest
from pathlib import Path

import yaml

from scripts import report_audit
from scripts.setup_workflow import setup_workflow
from workflows.diagnosis_first_v1 import report_yaml
from workflows.diagnosis_first_v1 import runtime as diagnosis_first
from validation.cases import retrieve_case


ROOT = Path(__file__).resolve().parents[1]
RULES = ROOT / "rules" / "agreed_reporting_rules.md"
POLICY = ROOT / "prompts" / "workflow" / "reporting_rule_policy.md"
DIAGNOSIS_FIRST_PROMPT_DIR = ROOT / "workflows" / "diagnosis_first_v1" / "prompts" / "rule_views"


def draft_document(rules_text, *, refined=None, tag="a1b2c3", retained_ids=()):
    rules = []
    for spec in report_audit.agreed_rule_specs(rules_text):
        rule_id = spec["rule_id"]
        if rule_id == "R0.1":
            rules.append({
                "id": rule_id,
                "omit": False,
                "statements": [{"text": "Detected variants.", "citation": "(no citation required)"}],
            })
        else:
            retained = rule_id in set(retained_ids)
            rules.append({
                "id": rule_id,
                "omit": not retained,
                "statements": [{
                    "text": "Clinically material retained conclusion." if retained else "No reportable implication.",
                    "citation": f"[card:{tag}]",
                }],
            })
    document = {"schema_version": 1}
    if refined is not None:
        document["refined_cmc"] = refined
    document["rules"] = rules
    return document


def write_yaml(path, document):
    path.write_text(yaml.safe_dump(document, sort_keys=False), encoding="utf-8")


class DiagnosisFirstWorkflowTests(unittest.TestCase):
    def test_setup_creates_only_branch_independent_assets_and_preserves_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "existing-work"
            work.mkdir()
            case = work / "case.md"
            case.write_text("existing patient case\n", encoding="utf-8")

            resolved, demo_case, demo_expected = setup_workflow(
                workflow="diagnosis-first-v1", mode="ngs-report", work_dir=work
            )

            self.assertEqual(resolved, work.resolve())
            self.assertIsNone(demo_case)
            self.assertIsNone(demo_expected)
            self.assertEqual(case.read_text(encoding="utf-8"), "existing patient case\n")
            categories = json.loads((work / "case-major-categories.json").read_text(encoding="utf-8"))
            self.assertEqual(
                categories["case_major_categories"],
                list(diagnosis_first.vocab.CASE_MAJOR_CATEGORIES),
            )
            dx_rules = (work / "reporting-rules-dx.md").read_text(encoding="utf-8")
            self.assertTrue(dx_rules.startswith("# Diagnosis-pass reporting rules\n"))
            self.assertFalse((work / "reporting-rules-remainder.md").exists())

    def test_setup_demo_resolves_paths_without_reading_or_copying_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "demo-work"
            resolved, demo_case, demo_expected = setup_workflow(
                workflow="diagnosis-first-v1", mode="nel-demo", work_dir=work, example=1
            )
            self.assertEqual(resolved, work.resolve())
            self.assertEqual(demo_case, ROOT / "examples" / "cases" / "01-escalation-fires.md")
            self.assertEqual(demo_expected, ROOT / "examples" / "expected" / "01-escalation-fires.md")
            self.assertFalse((work / "case.md").exists())

    def test_setup_validation_writes_case_additively_and_refuses_different_existing_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "validation-work"
            setup_workflow(workflow="diagnosis-first-v1", mode="nel-validate", work_dir=work, case_id="1A")
            first = (work / "case.md").read_text(encoding="utf-8")
            self.assertTrue(first.strip())

            setup_workflow(workflow="diagnosis-first-v1", mode="nel-validate", work_dir=work, case_id="1A")
            self.assertEqual((work / "case.md").read_text(encoding="utf-8"), first)

            with self.assertRaisesRegex(ValueError, "will not overwrite case.md"):
                setup_workflow(workflow="diagnosis-first-v1", mode="nel-validate", work_dir=work, case_id="1B")

    def test_setup_function_validation_uses_functional_case_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp) / "functional-work"
            setup_workflow(
                workflow="diagnosis-first-v1", mode="nel-validate-function", work_dir=work, case_id="1A"
            )
            case = (work / "case.md").read_text(encoding="utf-8")
            expected = retrieve_case("1A", "case_functional.md").rstrip() + "\n"
            self.assertEqual(case, expected)

    def test_rule_slices_are_canonical_subsets(self):
        source = RULES.read_text(encoding="utf-8")
        dx = diagnosis_first.slice_rules_text(source, {0, 1})
        remainder = diagnosis_first.slice_rules_text(source, {2, 3, 4, 5})
        self.assertTrue(all(s["rule_id"].startswith(("R0.", "R1.")) for s in report_audit.agreed_rule_specs(dx)))
        self.assertTrue(all(s["rule_id"].startswith(("R2.", "R3.", "R4.", "R5.")) for s in report_audit.agreed_rule_specs(remainder)))

    def test_generated_rule_views_have_yaml_contract(self):
        source = RULES.read_text(encoding="utf-8")
        dx = diagnosis_first.slice_rules_text(source, {0, 1})
        remainder = diagnosis_first.slice_rules_text(source, {2, 3, 4, 5})
        full = diagnosis_first.slice_rules_text(source, set(range(0, 6)))

        self.assertTrue(dx.startswith("# Diagnosis-pass reporting rules\n"))
        self.assertTrue(remainder.startswith("# Downstream reporting rules\n"))
        self.assertTrue(full.startswith("# Full reporting-rule re-analysis\n"))
        for view in (dx, remainder, full):
            self.assertNotIn("# Agreed reporting rules for interpretative myeloid NGS summaries", view)
            self.assertNotIn("# Style requirements", view)
            self.assertIn("## REPORT versus OMIT classification", view)
            self.assertIn("## YAML encoding", view)
            self.assertIn("statement-level", view)

    def test_shared_reporting_policy_is_injected_verbatim_from_prompt_source(self):
        expected = POLICY.read_text(encoding="utf-8").rstrip()
        source = RULES.read_text(encoding="utf-8")
        for sections in ({0, 1}, {2, 3, 4, 5}, set(range(0, 6))):
            view = diagnosis_first.slice_rules_text(source, sections)
            self.assertIn(expected, view)

    def test_diagnosis_first_prompt_prose_is_not_hardcoded_in_python(self):
        script = (ROOT / "workflows" / "diagnosis_first_v1" / "runtime.py").read_text(encoding="utf-8")
        for phrase in (
            "Answer R0-R1 only",
            "Answer R2-R5 only",
            "The diagnostic CMC changed",
            "Treat `diagnostic_evidence.md` as the complete literature-evidence boundary",
            "Treat `downstream_evidence.md` as the complete literature-evidence boundary",
        ):
            self.assertNotIn(phrase, script)
        for template_name in ("diagnosis_rule_view.md", "remainder_rule_view.md", "full_rule_view.md"):
            template = (DIAGNOSIS_FIRST_PROMPT_DIR / template_name).read_text(encoding="utf-8")
            self.assertIn("{{REPORTING_RULE_POLICY}}", template)
            self.assertIn("{{CANONICAL_RULES}}", template)

    def test_refined_cmc_is_yaml_field_and_strictly_canonical(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "dx.yaml"
            write_yaml(path, {"schema_version": 1, "refined_cmc": "AML", "rules": []})
            self.assertEqual(diagnosis_first.extract_refined_cmc(path), "AML")
            write_yaml(path, {"schema_version": 1, "refined_cmc": "imaginary disease", "rules": []})
            with self.assertRaisesRegex(ValueError, "not canonical"):
                diagnosis_first.extract_refined_cmc(path)

    def test_rule_template_prepopulates_ids_and_r0_citation(self):
        source = RULES.read_text(encoding="utf-8")
        dx_rules = diagnosis_first.slice_rules_text(source, {0, 1})
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            rules_path = tmp / "rules.md"
            rules_path.write_text(dx_rules, encoding="utf-8")
            out = report_yaml.write_rule_template(rules_path, tmp / "draft.yaml", include_refined_cmc=True)
            raw = out.read_text(encoding="utf-8")
            document = yaml.safe_load(raw)
            self.assertIsNone(document["refined_cmc"])
            self.assertEqual(document["rules"][0]["id"], "R0.1")
            self.assertIs(document["rules"][0]["omit"], False)
            self.assertEqual(document["rules"][0]["statements"][0]["citation"], "(no citation required)")
            self.assertIn('text: ""', raw)
            self.assertIn('citation: "(no citation required)"', raw)
            self.assertIn('citation: ""', raw)

    def test_assemble_filters_omitted_rules_when_cmc_unchanged(self):
        source = RULES.read_text(encoding="utf-8")
        dx_rules_text = diagnosis_first.slice_rules_text(source, {0, 1})
        rem_rules_text = diagnosis_first.slice_rules_text(source, {2, 3, 4, 5})
        evidence = "# Evidence\n\n- [card:a1b2c3]: Fixture.\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "case-input.json").write_text(json.dumps({"case_major_category": "AML"}), encoding="utf-8")
            (tmp / "dx-rules.md").write_text(dx_rules_text, encoding="utf-8")
            (tmp / "rem-rules.md").write_text(rem_rules_text, encoding="utf-8")
            write_yaml(tmp / "dx.yaml", draft_document(dx_rules_text, refined="AML", retained_ids={"R1.1"}))
            write_yaml(tmp / "rem.yaml", draft_document(rem_rules_text, retained_ids={"R2.1"}))
            (tmp / "dx-evidence.md").write_text(evidence, encoding="utf-8")
            (tmp / "rem-evidence.md").write_text(evidence, encoding="utf-8")
            out, changed, refined = diagnosis_first.assemble_report_draft(
                tmp / "case-input.json", tmp / "dx.yaml", tmp / "rem.yaml", tmp / "out.yaml",
                tmp / "dx-evidence.md", tmp / "rem-evidence.md", tmp / "dx-rules.md", tmp / "rem-rules.md",
            )
            self.assertFalse(changed)
            self.assertEqual(refined, "AML")
            assembled = yaml.safe_load(out.read_text(encoding="utf-8"))
            self.assertEqual([rule["id"] for rule in assembled["rules"]], ["R0.1", "R1.1", "R2.1"])
            self.assertTrue(all(rule["omit"] is False for rule in assembled["rules"]))
            self.assertTrue((tmp / "report-summary.yaml").is_file())

    def test_assemble_replaces_dx_when_cmc_changed_and_accepts_yes_no(self):
        source = RULES.read_text(encoding="utf-8")
        dx_rules_text = diagnosis_first.slice_rules_text(source, {0, 1})
        full_rules_text = diagnosis_first.slice_rules_text(source, set(range(0, 6)))
        evidence = "# Evidence\n\n- [card:a1b2c3]: Fixture.\n"
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            (tmp / "case-input.json").write_text(json.dumps({"case_major_category": "MDS"}), encoding="utf-8")
            (tmp / "dx-rules.md").write_text(dx_rules_text, encoding="utf-8")
            (tmp / "full-rules.md").write_text(full_rules_text, encoding="utf-8")
            dx = draft_document(dx_rules_text, refined="AML", retained_ids={"R1.1"})
            full = draft_document(full_rules_text, retained_ids={"R1.2"})
            for rule in full["rules"]:
                if rule["id"] == "R1.2":
                    rule["omit"] = "No"
                elif rule["id"] != "R0.1":
                    rule["omit"] = "Yes"
            write_yaml(tmp / "dx.yaml", dx)
            write_yaml(tmp / "rem.yaml", full)
            (tmp / "dx-evidence.md").write_text(evidence, encoding="utf-8")
            (tmp / "rem-evidence.md").write_text(evidence, encoding="utf-8")
            out, changed, refined = diagnosis_first.assemble_report_draft(
                tmp / "case-input.json", tmp / "dx.yaml", tmp / "rem.yaml", tmp / "out.yaml",
                tmp / "dx-evidence.md", tmp / "rem-evidence.md", tmp / "dx-rules.md", tmp / "full-rules.md",
            )
            self.assertTrue(changed)
            self.assertEqual(refined, "AML")
            assembled = yaml.safe_load(out.read_text(encoding="utf-8"))
            self.assertEqual([rule["id"] for rule in assembled["rules"]], ["R0.1", "R1.2"])


if __name__ == "__main__":
    unittest.main()
