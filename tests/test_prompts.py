import importlib.util
import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SPEC = importlib.util.spec_from_file_location(
    "build_prompts", ROOT / "scripts" / "build_prompts.py"
)
BUILD_PROMPTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILD_PROMPTS)
MARKER_RE = re.compile(r"{{([A-Z0-9_]+)}}")


class PromptIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.vocabulary = json.loads(
            (ROOT / "schema" / "publication_type_vocabulary.json").read_text()
        )
        cls.allowed = [entry["value"] for entry in cls.vocabulary["types"]]
        cls.manifest = BUILD_PROMPTS.load_manifest()["assets"]

    def test_publication_type_vocabulary_matches_both_schemas(self):
        census = json.loads((ROOT / "schema" / "census_schema.json").read_text())
        package = json.loads(
            (ROOT / "schema" / "ingestion_package_schema.json").read_text()
        )
        self.assertEqual(
            census["properties"]["publication_type"]["enum"], self.allowed
        )
        self.assertEqual(
            package["properties"]["publication_type"]["enum"], self.allowed
        )
        self.assertEqual(BUILD_PROMPTS.vocabulary_errors(), [])

    def test_all_phase_templates_render_without_unresolved_markers(self):
        for phase in (1, 2, 3, 4):
            with self.subTest(phase=phase):
                prompt = BUILD_PROMPTS.render(phase)
                self.assertTrue(prompt.strip())
                self.assertNotRegex(prompt, r"\{\{[^{}]+\}\}")

    def test_file_assets_are_injected_whole(self):
        templates = {
            f"phase{phase}": ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
            for phase in (1, 2, 3, 4)
        }
        rendered = {
            f"phase{phase}": BUILD_PROMPTS.render(phase) for phase in (1, 2, 3, 4)
        }
        for name, template_path in templates.items():
            markers = set(MARKER_RE.findall(template_path.read_text(encoding="utf-8")))
            for marker in markers:
                spec = self.manifest[marker]
                if spec.get("type") != "file":
                    continue
                expected = (ROOT / spec["path"]).read_text(encoding="utf-8").rstrip()
                with self.subTest(prompt=name, asset=marker):
                    self.assertIn(expected, rendered[name])

    def test_phase_validation_assets_contain_declared_file_whole(self):
        for phase in (1, 2, 4):
            keyword = f"PHASE{phase}_VALIDATION_BUNDLE"
            content = BUILD_PROMPTS.asset_content(keyword)
            spec = self.manifest[keyword]
            if spec.get("type") == "bundle":
                for relative in spec.get("paths", []):
                    path = ROOT / relative
                    self.assertIn(f"<!-- BEGIN VERBATIM {relative} -->", content)
                    self.assertIn(path.read_text(encoding="utf-8").rstrip(), content)
            else:
                path = ROOT / spec["path"]
                self.assertIn(path.read_text(encoding="utf-8").rstrip(), content)

    def test_phase2_and_phase4_validators_load_canonical_json_assets(self):
        for phase in (2, 4):
            with self.subTest(phase=phase):
                script = (ROOT / "scripts" / "phase_validation" / f"phase{phase}.py").read_text(encoding="utf-8")
                template = (ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md").read_text(encoding="utf-8")
                self.assertIn('load_json_asset("ingestion_package_schema.json")', script)
                self.assertIn('load_json_asset("disease_vocabulary.json")', script)
                self.assertNotIn("PACKAGE_SCHEMA = json.loads(", script)
                self.assertNotIn("UMBRELLA = json.loads(", script)
                self.assertNotIn("{{PACKAGE_SCHEMA}}", template)
                self.assertNotIn("{{DISEASE_VOCABULARY}}", template)
        phase4 = (ROOT / "scripts" / "phase_validation" / "phase4.py").read_text(encoding="utf-8")
        self.assertIn('load_json_asset("review_schema.json")', phase4)
        self.assertNotIn("REVIEW_SCHEMA = json.loads(", phase4)

    def test_phase2_allows_multi_claim_composite_text(self):
        prompt = " ".join(BUILD_PROMPTS.render(2).split())
        self.assertIn(
            "One or more `claim` fragments may jointly support one source assertion",
            prompt,
        )
        self.assertIn(
            "every `claim` fragment contributes to the same source assertion", prompt
        )

    def test_semantic_assets_are_consolidated_into_three_canonical_policies(self):
        for marker in ("CLINICAL_ASSERTION_POLICY", "CLINICAL_CARD_POLICY", "SOURCE_FIDELITY_POLICY"):
            self.assertIn(marker, self.manifest)
            self.assertEqual(self.manifest[marker]["type"], "file")
        for obsolete in (
            "CLINICAL_REPORTING_GATE", "SOURCE_BOUNDED_REASONING",
            "CATEGORY_SEMANTICS", "ATOMICITY_PRINCIPLES",
            "INTERPRETATION_PRINCIPLES", "SOURCE_SUPPORT_PRINCIPLES",
            "CARD_CONTENT_RULES",
        ):
            self.assertNotIn(obsolete, self.manifest)

    def test_clinical_assertion_policy_enforces_atomicity_and_nonfragmentation(self):
        policy = BUILD_PROMPTS.asset_content("CLINICAL_ASSERTION_POLICY")
        self.assertIn("one independently retainable/rejectable clinical proposition", policy)
        self.assertIn("deletion / independent-retention test", policy)
        self.assertIn("is **not** a qualifier merely because it provides context", policy)
        self.assertIn("A clinical endpoint is **not** by itself a clinical interpretation", policy)
        self.assertIn("not separate ingestion units", policy)

    def test_clinical_card_policy_targets_patient_level_meaning(self):
        policy = BUILD_PROMPTS.asset_content("CLINICAL_CARD_POLICY")
        self.assertIn("patient-level clinical meaning", policy)
        self.assertIn("Study-result packaging versus clinically operative information", policy)
        self.assertIn("prognostic-model internals", policy)
        self.assertIn("Do not convert absence of evidence into evidence of no effect", policy)
        self.assertIn("Parallel-gene consolidation exception", policy)

    def test_phase1_is_sensitive_and_does_not_receive_full_card_policy(self):
        template = (ROOT / "prompts" / "templates" / "phase1_prompt.md").read_text(encoding="utf-8")
        prompt = " ".join(BUILD_PROMPTS.render(1).split())
        self.assertNotIn("{{CLINICAL_CARD_POLICY}}", template)
        self.assertIn("sensitivity-first and source-faithful", prompt)
        self.assertIn("Do not polish census summaries into final card interpretations", prompt)
        self.assertIn("avoid fragmenting one clinical finding", prompt)

    def test_phase2_enforces_single_proposition_and_clinical_abstraction(self):
        prompt = " ".join(BUILD_PROMPTS.render(2).split())
        self.assertIn("single-proposition test", prompt)
        self.assertIn("there must be exactly one", prompt)
        self.assertIn("Do not rescue compound interpretations by relabelling the second proposition as a qualifier", prompt)
        self.assertIn("remove study name, cohort size, analysis method, statistical values", prompt)
        self.assertIn("Preserve clinically operative thresholds and values", prompt)

    def test_phase2_has_mandatory_all_card_human_semantic_gate(self):
        prompt = " ".join(BUILD_PROMPTS.render(2).split())
        self.assertIn("mandatory human semantic review gate", prompt)
        self.assertIn("Category-first semantic grouping rule", prompt)
        self.assertIn("Semantic grouping is conceptual, not syntactic", prompt)
        self.assertIn("category is the outer grouping axis", prompt)
        self.assertIn("current `evidence_tier`", prompt)
        self.assertIn("do not infer or invent a new evidence-quality score", prompt)
        self.assertIn("Adverse prognostic significance in acute myeloid leukemia", prompt)
        self.assertNotIn("normalized assertion template", prompt)
        self.assertNotIn("`<GENE> mutation is adverse in acute myeloid leukemia.`", prompt)
        self.assertIn("every candidate `card_id` appears **exactly once**", prompt)
        self.assertIn("current `category`", prompt)
        self.assertIn("complete interpretation", prompt)
        self.assertIn("group-wise and/or card-wise amendments", prompt)
        self.assertIn("change a card's category", prompt)
        self.assertIn("show **all current cards again**", prompt)
        self.assertIn("reply exactly `APPROVE`", prompt)
        self.assertIn("Approval is invalidated by any later change to the card set, category, or interpretation", prompt)

    def test_phase3_uses_card_policy_as_pass_fail_not_style_rewrite(self):
        prompt = " ".join(BUILD_PROMPTS.render(3).split())
        self.assertIn("pass/fail standard here, not an invitation to rewrite acceptable cards", prompt)
        self.assertIn("Single-proposition atomicity", prompt)
        self.assertIn("Clinical-utility abstraction", prompt)
        self.assertIn("recommend `split_card`", prompt)
        self.assertIn("recommend `rewrite_interpretation`", prompt)

    def test_phase4_applies_current_policy_only_to_authorised_repairs(self):
        prompt = " ".join(BUILD_PROMPTS.render(4).split())
        self.assertIn("authorised repair of a Phase 3-failed card", prompt)
        self.assertIn("Do not use newer wording standards as permission to modernise", prompt)

    def test_source_disease_alias_prompt_view_is_derived_from_terms(self):
        vocabulary = json.loads(
            (ROOT / "schema" / "disease_vocabulary.json").read_text(encoding="utf-8")
        )
        expected = {
            alias: term["name"]
            for term in vocabulary["terms"]
            for alias in term.get("aliases", [])
        }
        rendered = json.loads(BUILD_PROMPTS.asset_content("SOURCE_DISEASE_ALIASES"))
        self.assertEqual(rendered, expected)
        self.assertEqual(self.manifest["SOURCE_DISEASE_ALIASES"]["type"], "derived")

    def test_all_card_handling_prompts_use_canonical_source_disease_alias_policy(self):
        prompts = {
            f"phase{phase}": BUILD_PROMPTS.render(phase)
            for phase in (2, 3, 4)
        }
        for name, rendered in prompts.items():
            with self.subTest(prompt=name):
                prompt = " ".join(rendered.split())
                self.assertIn('"clonal haematopoiesis": "CHIP"', rendered)
                self.assertIn('"clonal haemopoiesis": "CHIP"', rendered)
                self.assertIn(
                    "Do not use fuzzy matching, stemming, punctuation substitution, "
                    "semantic inference, or nearest-term mapping.",
                    prompt,
                )
                self.assertNotIn("{{SOURCE_DISEASE_ALIAS_POLICY}}", rendered)
                self.assertNotIn("{{SOURCE_DISEASE_ALIASES}}", rendered)

    def test_phase1_does_not_apply_card_disease_alias_policy(self):
        prompt = BUILD_PROMPTS.render(1)
        self.assertNotIn("Source disease alias policy", prompt)
        self.assertNotIn('"clonal haematopoiesis": "CHIP"', prompt.split(
            "<!-- BEGIN VERBATIM", 1
        )[0])

    def test_phase3_audits_multi_claim_composites_without_auto_failure(self):
        prompt = " ".join(BUILD_PROMPTS.render(3).split())
        self.assertIn(
            "Multiple `claim` fragments are valid when they jointly support one "
            "source assertion.",
            prompt,
        )
        self.assertIn(
            "a `composite_text` bundle supports one coherent source assertion, "
            "uses compatible scope, and contains only necessary fragments",
            prompt,
        )
        self.assertIn(
            "Fail evidence that combines separate findings, populations, analyses, "
            "classifier branches or independently useful conclusions",
            prompt,
        )

    def test_phase3_uses_separate_publication_type_audit_policy(self):
        prompt = BUILD_PROMPTS.render(3)
        expected = (
            ROOT / "prompts" / "assets" / "publication_type_audit_policy.md"
        ).read_text(encoding="utf-8").rstrip()
        self.assertIn(expected, prompt)
        self.assertNotIn("audit_stability", prompt)

    def test_phase3_omits_deterministic_validation_bundle(self):
        prompt = BUILD_PROMPTS.render(3)
        self.assertNotIn("_VALIDATION_BUNDLE}}", prompt)
        self.assertNotIn("<!-- BEGIN VERBATIM scripts/phase_validation/", prompt)
        self.assertNotIn("validation_bundle/scripts/phase_validation/", prompt)
        self.assertNotIn("## Deterministic exit validation", prompt)

    def test_validation_occurs_at_phase2_exit_and_phase4_entry(self):
        phase2 = BUILD_PROMPTS.render(2)
        self.assertIn("## Step 7 — deterministic output gate", phase2)
        self.assertIn(
            "python validation_bundle/scripts/phase_validation/phase2.py",
            phase2,
        )
        phase4 = BUILD_PROMPTS.render(4)
        entry = phase4.split("## Step 1 — deterministic input gate", 1)[1].split(
            "## Shared semantic principles", 1
        )[0]
        self.assertIn(
            "python validation_bundle/scripts/phase_validation/phase4.py --review-only",
            entry,
        )
        self.assertIn("Before any adjudication or finalization", entry)

    def test_phase4_embeds_canonical_phase4_validator_verbatim(self):
        rendered = BUILD_PROMPTS.render(4)
        relative = "scripts/phase_validation/phase4.py"
        start_marker = f"<!-- BEGIN VERBATIM {relative} -->\n```python\n"
        end_marker = f"\n```\n<!-- END VERBATIM {relative} -->"
        embedded = rendered.split(start_marker, 1)[1].split(end_marker, 1)[0]
        expected = (ROOT / relative).read_text(encoding="utf-8").rstrip()
        self.assertEqual(embedded, expected)

    def test_shared_semantic_invariants_survive_refactor(self):
        rendered = {phase: " ".join(BUILD_PROMPTS.render(phase).split()) for phase in (1, 2, 3, 4)}
        for phase in (1, 2, 3, 4):
            with self.subTest(phase=phase, invariant="geneless molecular modifier"):
                self.assertIn("independent of a molecular treatment modifier", rendered[phase])
            with self.subTest(phase=phase, invariant="atomic qualifier preservation"):
                self.assertIn("qualifiers required to preserve meaning or applicability belong with the assertion", rendered[phase])
        self.assertIn("Phase 1 determines review boundaries, not card eligibility", rendered[1])
        self.assertIn("Phase 2 could reasonably retain one part while rejecting another", rendered[1])
        self.assertIn("freeze the complete candidate evidence bundle before drafting the interpretation", rendered[2])
        self.assertIn("Methodological detail belongs in the evidence unless it changes the patient-level meaning of the proposition", rendered[2])
        self.assertIn("sentence immediately before and after", rendered[2])
        self.assertIn("Do not author a finished replacement card", rendered[3])
        self.assertIn("Do not fail a card merely because another wording would also be defensible", rendered[3])
        self.assertIn("same evidence may legitimately support distinct roles", rendered[3])
        self.assertIn("Any provisional→final card/evidence difference not represented exactly by an approved ledger decision is invalid", rendered[4])
        self.assertIn("A card that Phase 3 passed is not directly editable in Phase 4", rendered[4])

    def test_phase3_bound_shared_assets_are_free_of_forbidden_authoring_context(self):
        template = (ROOT / "prompts" / "templates" / "phase3_prompt.md").read_text(encoding="utf-8")
        markers = set(MARKER_RE.findall(template))
        for marker in markers:
            spec = self.manifest[marker]
            if spec.get("type") != "file":
                continue
            content = BUILD_PROMPTS.asset_content(marker)
            with self.subTest(asset=marker):
                for forbidden in BUILD_PROMPTS.PHASE3_FORBIDDEN_TERMS:
                    self.assertNotIn(forbidden, content)

    def test_phase1_retry_skips_scope_reconfirmation_and_reaudits_whole_census(self):
        prompt = " ".join(BUILD_PROMPTS.render(1).split())
        self.assertIn("For a **Phase 1 retry/redo**, do **not** repeat", prompt)
        self.assertIn("do not ask for another `CONFIRM`", prompt)
        self.assertIn("Its `category_scope` is the already-confirmed scope", prompt)
        self.assertIn("The incoming critique is a minimum repair list, not the boundary of the audit", prompt)
        self.assertIn("The prior census is the working candidate, not merely a reference", prompt)
        self.assertIn("Preserve the existing `claim_id`, wording, genes, category, and locator for unaffected entries", prompt)
        self.assertIn("Do not regenerate the census wholesale", prompt)
        self.assertIn("does not authorize rewriting otherwise valid prior-census entries", prompt)
        self.assertIn("independent audit must reassess the whole census", prompt)

    def test_phase1_and_phase2_share_identical_census_semantic_gate(self):
        gate = (ROOT / "prompts" / "assets" / "census_semantic_gate.md").read_text(encoding="utf-8").rstrip()
        self.assertIn(gate, BUILD_PROMPTS.render(1))
        self.assertIn(gate, BUILD_PROMPTS.render(2))

    def test_census_semantic_gate_is_source_first_and_card_agnostic(self):
        gate = (ROOT / "prompts" / "assets" / "census_semantic_gate.md").read_text(encoding="utf-8")
        self.assertIn("source-first census audit", gate)
        self.assertIn("temporarily ignoring the candidate census", gate)
        self.assertIn("Independently reconstruct the expected set", gate)
        self.assertIn("collect **all** material defects before repairing anything", gate)
        self.assertIn("census quality only", gate)
        self.assertIn("not a finished evidence-card interpretation", gate)
        self.assertIn("Do not apply evidence-card eligibility", gate)

    def test_phase1_drafting_preserves_meaning_critical_qualifiers(self):
        phase1 = " ".join(BUILD_PROMPTS.render(1).split())
        self.assertIn("The summary must preserve every qualifier needed to understand the exact assertion", phase1)
        self.assertIn("Concision must not remove a meaning-critical qualifier", phase1)
        self.assertIn("First reconstruct the expected in-scope source assertions directly from the paper", phase1)

    def test_phase3_output_contract_matches_phase4_review_schema_names(self):
        prompt = BUILD_PROMPTS.render(3)
        schema = json.loads((ROOT / "schema" / "review_schema.json").read_text(encoding="utf-8"))
        for field in schema["required"]:
            with self.subTest(scope="top-level", field=field):
                self.assertIn(f'"{field}"', prompt)
        for field in schema["properties"]["audit"]["required"]:
            with self.subTest(scope="audit", field=field):
                self.assertIn(f'"{field}"', prompt)
        for field in schema["$defs"]["publication_type_verdict"]["required"]:
            with self.subTest(scope="publication_type_verdict", field=field):
                self.assertIn(f'"{field}"', prompt)
        for field in schema["$defs"]["failure_details"]["required"]:
            with self.subTest(scope="failure_details", field=field):
                self.assertIn(f'"{field}"', prompt)
        self.assertIn('"result": "review_complete"', prompt)
        self.assertIn('"verdict": "pass"', prompt)
        self.assertIn('"review_basis": "phase3"', prompt)
        self.assertIn("paper.review-vNNN.json", prompt)
        self.assertIn("paper.review-revRRR-vNNN.json", prompt)
        self.assertIn("strictly author the review to the exact structure", prompt)


    def test_phase_workflow_gate_ordering_matches_contract(self):
        phase1 = BUILD_PROMPTS.render(1)
        self.assertLess(phase1.index("## Step 1 — core census work"), phase1.index("## Step 2 — independent semantic audit"))
        self.assertLess(phase1.index("## Step 2 — independent semantic audit"), phase1.index("## Step 3 — model formatting gate"))
        self.assertLess(phase1.index("## Step 3 — model formatting gate"), phase1.index("## Step 4 — deterministic formatting/structure gate"))
        self.assertIn("There is no fixed-pass escape for unresolved semantic defects", phase1)

        phase2 = BUILD_PROMPTS.render(2)
        positions = [phase2.index(label) for label in (
            "### Step 1 — deterministic census input gate",
            "### Step 2 — census semantic input gate",
            "### Step 3 — Phase 2 card/evidence work",
            "## Step 4 — independent semantic output audit",
            "## Step 5 — mandatory human semantic review gate",
            "## Step 6 — model formatting gate",
            "## Step 7 — deterministic output gate",
        )]
        self.assertEqual(positions, sorted(positions))
        self.assertIn("exact same deterministic Phase 1 validator used on Phase 1 output", phase2)
        self.assertIn("Phase 2R uses a separate workflow and **does not run a deterministic input gate**", phase2)

        phase3 = BUILD_PROMPTS.render(3)
        self.assertLess(phase3.index("## Step 1 — model input formatting gate"), phase3.index("## Step 2 — Phase 3 substantive review"))
        self.assertLess(phase3.index("## Step 2 — Phase 3 substantive review"), phase3.index("## Step 3 — model output formatting gate"))
        self.assertIn("formatting/structure-only", phase3)
        self.assertNotIn("## Deterministic exit validation", phase3)

        phase4 = BUILD_PROMPTS.render(4)
        self.assertLess(phase4.index("## Step 1 — deterministic input gate"), phase4.index("## Step 2 — human adjudication and interactivity"))
        self.assertLess(phase4.index("## Step 2 — human adjudication and interactivity"), phase4.index("## Step 3 — apply agreed decisions and deterministic output gate"))
        self.assertNotIn("## Mandatory pre-output gate", phase4)
        self.assertIn("The final action before returning `paper.final.json` must be a successful run", phase4)

    def test_phase2_input_gate_embeds_exact_phase1_validator(self):
        phase2 = BUILD_PROMPTS.render(2)
        relative = "scripts/phase_validation/phase1.py"
        start_marker = f"<!-- BEGIN VERBATIM {relative} -->\n```python\n"
        end_marker = f"\n```\n<!-- END VERBATIM {relative} -->"
        embedded = phase2.split(start_marker, 1)[1].split(end_marker, 1)[0]
        expected = (ROOT / relative).read_text(encoding="utf-8").rstrip()
        self.assertEqual(embedded, expected)
        self.assertIn("validation_bundle/scripts/phase_validation/phase1.py", phase2)

    def test_deterministic_validation_is_the_final_output_gate_where_required(self):
        phase1 = BUILD_PROMPTS.render(1)
        self.assertGreater(phase1.index("## Step 4 — deterministic formatting/structure gate"), phase1.index("## Step 3 — model formatting gate"))
        phase2 = BUILD_PROMPTS.render(2)
        self.assertGreater(phase2.index("## Step 7 — deterministic output gate"), phase2.index("## Step 6 — model formatting gate"))
        phase4 = BUILD_PROMPTS.render(4)
        self.assertNotIn("Mandatory pre-output gate", phase4)
        self.assertIn("Do not edit `paper.final.json` after the successful run", phase4)

    def test_phase4_requires_successful_validation_as_final_action(self):
        prompt = BUILD_PROMPTS.render(4)
        self.assertIn(
            "python validation_bundle/scripts/phase_validation/phase4.py",
            prompt,
        )
        self.assertNotIn("validation_bundle/scripts/final_validation.py", prompt)
        self.assertIn(
            "The final action before returning `paper.final.json` must be a "
            "successful run",
            " ".join(prompt.split()),
        )
        self.assertIn(
            "Do not edit `paper.final.json` after the successful run.",
            " ".join(prompt.split()),
        )


if __name__ == "__main__":
    unittest.main()


class Phase1CategoryScopePromptTests(unittest.TestCase):
    def test_phase1_requires_scope_confirmation_before_extraction(self):
        prompt = " ".join(BUILD_PROMPTS.render(1).split())
        self.assertIn("Phase 1, diagnosis only", prompt)
        self.assertIn("ask the user to reply exactly `CONFIRM`", prompt)
        self.assertIn(
            "Plain `Phase 1`, or any invocation without an explicit category restriction, "
            "means all five categories",
            prompt,
        )
        self.assertIn("reading remains whole-paper", prompt)

    def test_phase1_summary_and_scope_suggestion_do_not_change_effective_scope(self):
        prompt = " ".join(BUILD_PROMPTS.render(1).split())
        self.assertIn("In 50 words or fewer", prompt)
        self.assertIn("summary of what the paper is about", prompt)
        self.assertIn(
            "recommend a Phase 1 category scope suited to that purpose", prompt
        )
        self.assertIn("the recommendation is advisory", prompt)
        self.assertIn(
            "must not narrow or otherwise change the normalized scope unless the user "
            "explicitly instructs that scope",
            prompt,
        )
        self.assertIn(
            "Disregard any advisory scope suggestion during extraction", prompt
        )
        self.assertIn(
            "retain claims from every category in the confirmed scope", prompt
        )

    def test_phase2_respects_declared_category_scope(self):
        prompt = " ".join(BUILD_PROMPTS.render(2).split())
        self.assertIn("optional `category_scope`", prompt)
        self.assertIn("outside a declared `category_scope`", prompt)
        self.assertIn("Census semantic gate", prompt)
        self.assertIn("complete the **entire census audit before returning the critique**", BUILD_PROMPTS.render(2))
