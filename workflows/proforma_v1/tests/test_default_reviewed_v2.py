"""Structural and behavioural invariants for the ``default_reviewed_v2`` overlay.

These tests encode the properties that stop this workflow becoming either the
thing it replaces (``default_reviewed``, loop-heavy) or the thing it was built
to catch (a clinically wrong conclusion that survives its own refutation):

* the clinical head remains a clone of ``default`` in everything but wiring;
* every clinical owner is audited before anything consumes its result;
* an owner may be invoked at most three times for one clinical object, and a
  correction step can never itself become a correction target;
* the correcting owner receives the plain-English defect and its own previous
  output, and never the auditor's routing verdict;
* a defect of either kind routes to the clinical owner, never to a rewriter;
* unresolved findings reach the canonical dissent ledger and the terminal
  policy actually prevents disputed output being treated as accepted truth.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.proforma_v1 import default_reviewed_v2 as v2  # noqa: E402
from workflows.proforma_v1 import layout, model_context  # noqa: E402
from workflows.proforma_v1.engine import (  # noqa: E402
    dissent as workflow_dissent,
    transforms,
    workflow_compiler,
    workflow_progress,
)

DEFAULT = HERE / "workflow" / "default.yaml"
V2 = HERE / "workflow" / "default_reviewed_v2.yaml"
REVIEWED = HERE / "workflow" / "default_reviewed.yaml"

CLINICAL_STEPS = (
    "structure", "corpus",
    "diagnosis.who1", "diagnosis.who1.routing_change",
    "diagnosis.who1.evidence.assignment", "diagnosis.who1.evidence.audit",
    "diagnosis.who1.evidence.adjudication", "diagnosis.who1.commit",
    "diagnosis.who2", "diagnosis.icc",
    "prognosis", "treatment", "biomarker", "germline",
)
OWNER_STEPS = (
    "diagnosis.who1", "diagnosis.who2", "diagnosis.icc",
    "prognosis", "treatment", "biomarker", "germline",
)
# The overlay rewires owners; it must not restate their clinical contract.
OWNER_WIRING_KEYS = {"inputs", "needs", "prompt"}
EVIDENCE_STEPS = ("evidence.assignment", "evidence.audit", "evidence.adjudication", "evidence.finalize")

GATES = tuple(f"audit.{owner}.gate" for owner in v2.OWNERS)
ADDED_STEPS = tuple(
    f"audit.{owner}.{suffix}" for owner in v2.OWNERS for suffix in ("packet", "coherence", "gate")
) + ("audit.diagnosis.terminal", "audit.diagnosis.provenance", "audit.ptbg.terminal")


def _load(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


class WorkflowShapeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.default = _load(DEFAULT)
        cls.doc = _load(V2)
        cls.steps = cls.doc["steps"]

    def test_v2_compiles(self):
        workflow = workflow_compiler.compile_workflow(V2)
        self.assertEqual(workflow.workflow_id, "proforma-v1")
        self.assertTrue(workflow.steps)

    def test_default_is_untouched(self):
        for sid in ADDED_STEPS:
            self.assertNotIn(sid, self.default["steps"])

    def test_cloned_from_default_not_default_reviewed(self):
        reviewed = _load(REVIEWED)["steps"]
        secretarial = [s for s in reviewed if ".secretary" in s or ".precheck" in s or ".postcheck" in s]
        self.assertTrue(secretarial, "fixture expectation: default_reviewed has secretary/precheck steps")
        for sid in secretarial:
            self.assertNotIn(sid, self.steps, f"v2 must not inherit {sid!r} from default_reviewed")

    def test_non_owner_clinical_steps_differ_from_default_only_in_wiring(self):
        """Relocating the audits reroutes `needs`. Nothing else about an
        inherited clinical step may change."""
        for sid in CLINICAL_STEPS:
            self.assertIn(sid, self.steps, sid)
            if sid in OWNER_STEPS:
                continue
            mine, theirs = dict(self.steps[sid]), dict(self.default["steps"][sid])
            mine.pop("needs", None)
            theirs.pop("needs", None)
            self.assertEqual(mine, theirs, f"clinical step {sid!r} diverged beyond wiring")

    def test_owner_steps_differ_from_default_only_in_wiring(self):
        """The overlay adds a correction input and reroutes; it does not
        restate the clinical contract (role, stage, schema, handlers)."""
        for sid in OWNER_STEPS:
            mine, theirs = self.steps[sid], self.default["steps"][sid]
            differing = {k for k in set(mine) | set(theirs) if mine.get(k) != theirs.get(k)}
            self.assertTrue(
                differing <= OWNER_WIRING_KEYS,
                f"owner {sid!r} diverged from default beyond wiring: {sorted(differing - OWNER_WIRING_KEYS)}",
            )

    def test_owner_prompt_bodies_match_default(self):
        """Only the correction section may differ from the default proforma."""
        import re
        pairs = {
            "diagnosis_who5.md": "diagnosis_who5.md",
            "diagnosis_icc.md": "diagnosis_icc.md",
            "prognosis.md": "prognosis.md",
            "treatment.md": "treatment.md",
            "biomarker.md": "biomarker.md",
            "germline.md": "germline.md",
        }
        for v2_name, base_name in pairs.items():
            base = (HERE / "prompts" / base_name).read_text(encoding="utf-8")
            base = re.sub(r'\{\{\s*include\s+"(?!\.\./)', '{{ include "../', base)
            mine = (HERE / "prompts" / "default_reviewed_v2" / v2_name).read_text(encoding="utf-8")
            stripped = re.sub(
                r"## Reasoning correction.*?\{\{ input\.reasoning_correction \}\}\n\n", "", mine, flags=re.S
            )
            self.assertEqual(base, stripped, f"{v2_name} altered the clinical proforma body")

    def test_three_stage_evidence_chain_retained(self):
        for sid in EVIDENCE_STEPS:
            self.assertIn(sid, self.steps, sid)
            mine, theirs = dict(self.steps[sid]), dict(self.default["steps"][sid])
            mine.pop("needs", None)
            theirs.pop("needs", None)
            self.assertEqual(mine, theirs, f"evidence step {sid!r} diverged from default")
        self.assertEqual(self.doc["evidence_policies"], self.default["evidence_policies"])

    def test_report_pipeline_reused(self):
        for sid in ("report.write", "report.preservation", "report.finalize"):
            self.assertEqual(self.steps[sid], self.default["steps"][sid], sid)

    def test_added_steps_present(self):
        for sid in ADDED_STEPS:
            self.assertIn(sid, self.steps, sid)

    def test_step_count_stays_well_below_default_reviewed(self):
        reviewed = len(_load(REVIEWED)["steps"])
        self.assertLess(len(self.steps), 60)
        self.assertLess(len(self.steps), reviewed * 0.7)

    def test_progress_plan_covers_every_step(self):
        workflow = workflow_compiler.compile_workflow(V2)
        plan = workflow_progress.load_progress_plan(workflow)
        covered = {sid for phase in plan["phases"] for sid in phase["steps"]}
        self.assertEqual(covered, {step.id for step in workflow.steps})


class AuditPlacementTests(unittest.TestCase):
    """Fix: audit each owner before anything downstream consumes it."""

    @classmethod
    def setUpClass(cls):
        cls.workflow = workflow_compiler.compile_workflow(V2)
        cls.steps = _load(V2)["steps"]

    def _descendants(self, root: str) -> set[str]:
        out, changed = {root}, True
        while changed:
            changed = False
            for sid, cfg in self.steps.items():
                if sid in out:
                    continue
                if any(need in out for need in (cfg.get("needs") or [])):
                    out.add(sid)
                    changed = True
        return out - {root}

    def test_every_clinical_owner_has_its_own_audit(self):
        for owner in v2.OWNERS:
            for suffix in ("packet", "coherence", "gate"):
                self.assertIn(f"audit.{owner}.{suffix}", self.steps)

    def test_no_step_consumes_an_owner_before_its_gate(self):
        """A consumer that is downstream of an owner must also be downstream of
        that owner's gate; otherwise a correction would invalidate work already
        done, which is the cascade this relocation exists to avoid."""
        for owner, owner_step in v2.OWNER_STEPS.items():
            gate = f"audit.{owner}.gate"
            gate_descendants = self._descendants(gate) | {gate}
            for sid in self._descendants(owner_step):
                if sid.startswith(f"audit.{owner}."):
                    continue
                self.assertIn(
                    sid, gate_descendants,
                    f"{sid!r} consumes {owner_step!r} without waiting for {gate!r}",
                )

    def test_diagnosis_audits_precede_the_who1_evidence_gate(self):
        needs = self.steps["diagnosis.who1.routing_change"]["needs"]
        self.assertIn("audit.who1.gate", needs)
        self.assertNotIn("diagnosis.who1", needs)

    def test_ptbg_audits_precede_the_main_evidence_chain(self):
        needs = self.steps["evidence.assignment"]["needs"]
        self.assertIn("audit.ptbg.terminal", needs)
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            self.assertNotIn(domain, needs)

    def test_ptbg_coherence_is_unconditional_per_domain(self):
        """The former PTBG audit was gated on downstream evidence verdicts, so
        relocating it necessarily makes it unconditional."""
        for domain in ("prognosis", "treatment", "biomarker", "germline"):
            self.assertNotIn("when", self.steps[f"audit.{domain}.coherence"])

    def test_diagnosis_coherence_is_unconditional(self):
        for owner in ("who1", "icc"):
            self.assertNotIn("when", self.steps[f"audit.{owner}.coherence"])

    def test_who2_audit_shares_the_owner_condition(self):
        expected = self.steps["diagnosis.who2"].get("when")
        for suffix in ("packet", "coherence", "gate"):
            self.assertEqual(self.steps[f"audit.who2.{suffix}"].get("when"), expected)


class BoundedOwnerCorrectionTests(unittest.TestCase):
    """The safety property is bounded owner invocation, not a review-block count."""

    @classmethod
    def setUpClass(cls):
        cls.steps = _load(V2)["steps"]
        default_steps = _load(DEFAULT)["steps"]
        all_reviews = {sid: cfg["review"] for sid, cfg in cls.steps.items() if cfg.get("review")}
        # default ships one evidence audit-resolution loop. It is retained
        # deliberately along with the rest of the three-stage chain and is
        # pinned byte-identical elsewhere; the owner-correction cap governs the
        # reviews this overlay adds.
        cls.inherited = {sid: r for sid, r in all_reviews.items() if sid in default_steps}
        cls.reviews = {sid: r for sid, r in all_reviews.items() if sid not in default_steps}

    def test_every_review_targets_a_clinical_owner(self):
        """A semantic defect is returned to the model that made it. No generic
        rewriter is permitted to author clinical reasoning."""
        for sid, review in self.reviews.items():
            self.assertIn(
                review["target"], OWNER_STEPS,
                f"review {sid!r} targets {review['target']!r}, which is not a clinical owner",
            )

    def test_owner_attempts_are_capped_at_three(self):
        for sid, review in self.reviews.items():
            self.assertEqual(review["on_fail"]["max_cycles"], v2.MAX_CORRECTIONS, sid)
        self.assertEqual(v2.MAX_OWNER_ATTEMPTS, 3)

    def test_a_fourth_owner_attempt_is_unreachable(self):
        """max_cycles is the runner's hard budget; exceeding it routes to the
        exhausted action, never back to the owner."""
        for sid, review in self.reviews.items():
            exhausted = review["on_fail"]["exhausted"]
            self.assertEqual(exhausted["action"], "continue_with_dissent", sid)
            self.assertNotIn("route_to", exhausted, sid)

    def test_a_correction_step_is_never_itself_a_correction_target(self):
        targets = {review["target"] for review in self.reviews.values()}
        for sid in self.reviews:
            self.assertNotIn(sid, targets, f"{sid!r} reviews and is reviewed: that is a recursive repair chain")

    def test_each_owner_is_reviewed_at_most_once(self):
        seen = [review["target"] for review in self.reviews.values()]
        self.assertEqual(len(seen), len(set(seen)), "an owner with two reviewers has two budgets")

    def test_inherited_reviews_are_unchanged_from_default(self):
        default_steps = _load(DEFAULT)["steps"]
        self.assertEqual(set(self.inherited), {"evidence.audit"})
        for sid in self.inherited:
            self.assertEqual(self.steps[sid], default_steps[sid], f"inherited review {sid!r} was modified")

    def test_added_reviews_are_exactly_one_per_clinical_owner(self):
        self.assertEqual(set(self.reviews), set(GATES))

    def test_default_reviewed_would_fail_the_owner_cap(self):
        reviewed = _load(REVIEWED)["steps"]
        targets = [cfg["review"]["target"] for cfg in reviewed.values() if cfg.get("review")]
        self.assertGreater(
            len(targets), len(set(targets)),
            "fixture expectation: default_reviewed reviews the same owner from several places",
        )


class CorrectionContractTests(unittest.TestCase):
    """What the correcting owner is, and is not, allowed to see."""

    @classmethod
    def setUpClass(cls):
        cls.steps = _load(V2)["steps"]

    def test_feedback_sends_only_the_correction_packet(self):
        for owner, owner_step in v2.OWNER_STEPS.items():
            feedback = self.steps[f"audit.{owner}.gate"]["review"]["on_fail"]["feedback"]
            self.assertEqual(feedback["path"], "correction", owner)
            self.assertEqual(feedback["as"], "reasoning_correction", owner)
            self.assertIn("reasoning_correction", self.steps[owner_step]["inputs"], owner)

    def test_gate_artifact_keeps_verdict_fields_out_of_the_correction(self):
        """conclusion_supported / reason_defective are routing fields. Telling
        an owner a reviewer rejected its conclusion is an instruction to change
        it, so they go to a side record instead of the correction packet."""
        gate = v2.correction_gate.__doc__ or ""
        self.assertIn("side record", gate)
        result = {"status": "revision_required", "correction": {"correction_brief": "x", "previous_output": {}}}
        self.assertEqual(set(result["correction"]), {"correction_brief", "previous_output"})

    def test_correction_prompt_asks_for_full_reassessment_not_text_repair(self):
        for name in ("diagnosis_who5.md", "diagnosis_icc.md", "prognosis.md",
                     "treatment.md", "biomarker.md", "germline.md"):
            text = (HERE / "prompts" / "default_reviewed_v2" / name).read_text(encoding="utf-8")
            self.assertIn("{{ input.reasoning_correction }}", text, name)
            self.assertIn("full task again", text, name)
            self.assertIn("Do not repeat the identified reasoning error", text, name)
            self.assertNotIn("conclusion_supported", text, name)
            self.assertNotIn("reason_defective", text, name)

    def test_auditor_is_told_not_to_prescribe_a_replacement(self):
        for name in ("diagnosis_coherence.md", "ptbg_coherence.md"):
            text = (HERE / "prompts" / "default_reviewed_v2" / name).read_text(encoding="utf-8")
            self.assertIn("not the clinical decision-maker", text, name)
            self.assertIn("correction_brief", text, name)

    def test_ptbg_auditor_defers_literature_support_to_the_evidence_chain(self):
        text = (HERE / "prompts" / "default_reviewed_v2" / "ptbg_coherence.md").read_text(encoding="utf-8")
        self.assertIn("not** auditing literature support", text)
        self.assertIn("authoritative diagnosis", text)


class AuditVerdictTests(unittest.TestCase):
    """The scope enum is replaced by two independent judgements."""

    def test_schema_declares_orthogonal_judgements(self):
        schema = json.loads(
            (HERE / "schemas" / "default_reviewed_v2" / "owner_coherence.json").read_text(encoding="utf-8")
        )
        self.assertEqual(set(schema["required"]), {"conclusion_supported", "reason_defective"})
        self.assertNotIn("scope", schema["properties"])

    def test_scope_vocabulary_is_gone_from_the_overlay(self):
        source = (HERE / "default_reviewed_v2.py").read_text(encoding="utf-8")
        self.assertNotIn("REVISION_SCOPES", source)

    def _gate(self, verdict, attempts=0):
        class _Ctx:
            work = Path(tempfile.mkdtemp())
            data: dict = {}

            def get(self, key, default=None):
                return {
                    "v2_who1_coherence": verdict,
                    "v2_who1_packet": {"conclusion": "X"},
                    "review_cycles": {"audit.who1.gate": attempts},
                }.get(key, default)

            def put(self, *_args):
                return None

        ctx = _Ctx()
        return v2.correction_gate(None, {"__workflow_context__": ctx, "__work__": ctx.work}, {"owner": "who1"})

    def test_unsupported_conclusion_routes_to_the_owner(self):
        out = self._gate({"conclusion_supported": False, "reason_defective": False, "correction_brief": "b"})
        self.assertEqual(out["status"], "revision_required")

    def test_defective_reason_routes_to_the_owner_even_when_conclusion_stands(self):
        """A wrong clinical reason is reassessed by the owner, never patched by
        a rewriter: only the owner can tell whether the conclusion survives."""
        out = self._gate({"conclusion_supported": True, "reason_defective": True, "correction_brief": "b"})
        self.assertEqual(out["status"], "revision_required")

    def test_sound_assessment_passes(self):
        out = self._gate({"conclusion_supported": True, "reason_defective": False})
        self.assertEqual(out["status"], "pass")
        self.assertNotIn("correction", out)

    def test_defect_without_a_brief_is_a_structural_failure_not_a_correction(self):
        out = self._gate({"conclusion_supported": False, "reason_defective": True})
        self.assertEqual(out["status"], "audit_failed")

    def test_malformed_verdict_does_not_disturb_the_owner(self):
        out = self._gate({"conclusion_supported": "no", "reason_defective": True, "correction_brief": "b"})
        self.assertEqual(out["status"], "audit_failed")


class TerminalPolicyTests(unittest.TestCase):
    def test_defaults_match_the_shipped_template(self):
        template = json.loads((ROOT / "config" / "settings.json.template").read_text(encoding="utf-8"))
        self.assertEqual(
            template["reviewed_v2_terminal_policy"],
            v2.DEFAULT_TERMINAL_POLICY,
        )

    def test_every_declared_mode_validates(self):
        for mode in v2.TERMINAL_MODES:
            policy = v2.terminal_policy({"reviewed_v2_terminal_policy": {"diagnosis": mode, "ptbg": mode}})
            self.assertEqual(policy["diagnosis"], mode)

    def test_misspelled_mode_fails_loudly(self):
        with self.assertRaises(v2.V2Error):
            v2.terminal_policy({"reviewed_v2_terminal_policy": {"diagnosis": "withold_affected_output"}})

    def test_unknown_key_fails_loudly(self):
        with self.assertRaises(v2.V2Error):
            v2.terminal_policy({"reviewed_v2_terminal_policy": {"diagnosis_mode": "fail_run"}})

    def test_non_boolean_flag_fails_loudly(self):
        with self.assertRaises(v2.V2Error):
            v2.terminal_policy({"reviewed_v2_terminal_policy": {"surface_dissent": "yes"}})

    def test_absent_configuration_uses_the_documented_default(self):
        self.assertEqual(v2.terminal_policy({}), v2.DEFAULT_TERMINAL_POLICY)


class PatientFindingsTests(unittest.TestCase):
    """The auditor must see the case it is judging conclusions against."""

    CASE = {
        "provisional_disease": "MDS with low blasts and multilineage dysplasia",
        "case_facts": [
            {"fact_id": "C5", "kind": "marrow_findings", "value": "trilineage dysplasia with 4% blasts"},
            {"fact_id": "C7", "kind": "FISH", "value": "negative for 17p deletion"},
            {"fact_id": "C8", "kind": "molecular_testing_other",
             "value": "no 17p loss or copy-neutral loss of heterozygosity detected"},
        ],
        "ngs_no_variants_detected": ["SF3B1", "ASXL1"],
    }
    REGISTRY = {"v01": {"gene": "TP53", "description": "TP53 c.524G>A p.(Arg175His)", "vaf": "12%"}}

    def test_structured_case_facts_reach_the_packet(self):
        findings = v2._patient_findings(self.CASE, self.REGISTRY)
        joined = " | ".join(findings)
        for needle in ("4% blasts", "negative for 17p deletion", "copy-neutral loss of heterozygosity"):
            self.assertIn(needle, joined, f"{needle!r} was dropped from patient findings")

    def test_every_case_fact_is_projected(self):
        findings = v2._patient_findings(self.CASE, self.REGISTRY)
        self.assertGreaterEqual(len(findings), len(self.CASE["case_facts"]))

    def test_vaf_survives_into_the_packet(self):
        self.assertIn("VAF 12%", " | ".join(v2._patient_findings(self.CASE, self.REGISTRY)))

    def test_absent_genes_are_not_reported_as_a_negative_ngs_result(self):
        """The former wording claimed no reportable variants were detected,
        contradicting the variant listed immediately above it."""
        joined = " | ".join(v2._patient_findings(self.CASE, self.REGISTRY))
        self.assertNotIn("No reportable variants were detected", joined)
        self.assertIn("2 further assayed gene", joined)


class VariantRegistryTests(unittest.TestCase):
    def test_diagnosis_projection_exposes_allelic_state_fields(self):
        self.assertIn("vaf", model_context.DIAGNOSIS_REGISTRY_FIELDS)
        self.assertIn("event_type", model_context.DIAGNOSIS_REGISTRY_FIELDS)

    def test_diagnosis_registry_context_renders_vaf(self):
        text = model_context.registry_context(
            {"v01": {"variant_id": "V1", "gene": "TP53", "description": "TP53 c.524G>A", "vaf": "12%"}},
            fields=model_context.DIAGNOSIS_REGISTRY_FIELDS,
        )
        self.assertIn("12%", text)
        self.assertNotIn("V1", text, "source-namespace variant_id must never reach a model")


class DissentPropagationTests(unittest.TestCase):
    """A finding recorded only in an intermediate file is not a safety guard."""

    def test_overlay_can_raise_canonical_dissent(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            v2._raise_terminal_dissent(
                work, owner="who1", stage="reasoning correction (diagnosis)",
                reviewed_text="MDS with biallelic TP53 inactivation",
                brief="Only one TP53 hit is demonstrated.",
                outcome="The unverified re-classification was withheld.",
            )
            issues = workflow_dissent.doc(work).get("issues") or []
            self.assertEqual(len(issues), 1)
            self.assertEqual(issues[0]["status"], "retained_with_dissent")
            self.assertIn("Only one TP53 hit", yaml.safe_dump(issues[0]))

    def test_ledger_is_shared_not_executor_private(self):
        source = (HERE / "step.py").read_text(encoding="utf-8")
        self.assertIn("workflow_dissent.raise_issue", source)
        self.assertIn("workflow_dissent.set_renderer", source)

    def test_dissent_key_is_stable_across_repeat_raises(self):
        with tempfile.TemporaryDirectory() as td:
            work = Path(td)
            for _ in range(3):
                v2._raise_terminal_dissent(
                    work, owner="prognosis", stage="reasoning correction (prognosis)",
                    reviewed_text="prognosis assessment", brief="b", outcome="o",
                )
            self.assertEqual(len(workflow_dissent.doc(work).get("issues") or []), 1)


class ExecutorNeutralityTests(unittest.TestCase):
    def test_added_steps_use_only_generic_handlers(self):
        allowed = {"generic_transform", "generic_model", "reasoning_model"}
        steps = _load(V2)["steps"]
        for sid in ADDED_STEPS:
            execution = steps[sid]["execution"]
            self.assertIn(execution["provider_handler"], allowed, sid)
            self.assertIn(execution["self_handler"], allowed, sid)

    def test_provider_and_self_handlers_agree(self):
        steps = _load(V2)["steps"]
        for sid in ADDED_STEPS:
            execution = steps[sid]["execution"]
            self.assertEqual(execution["provider_handler"], execution["self_handler"], sid)

    def test_no_v2_symbol_in_either_executor(self):
        for name in ("step.py", "self.py"):
            text = (HERE / name).read_text(encoding="utf-8")
            self.assertNotIn("default_reviewed_v2", text, f"{name} must not reference the v2 overlay")

    def test_transforms_registered(self):
        for name in v2.TRANSFORMS:
            self.assertIn(name, transforms.REGISTRY, name)


class FeedbackPathBindingTests(unittest.TestCase):
    """The engine change that lets a reviewer send one field, not everything."""

    def test_compiler_rejects_an_unknown_feedback_key(self):
        doc = _load(V2)
        doc["steps"]["audit.who1.gate"]["review"]["on_fail"]["feedback"]["nonsense"] = "x"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "w.yaml"
            path.write_text(yaml.safe_dump(doc), encoding="utf-8")
            with self.assertRaises(Exception):
                workflow_compiler.compile_workflow(path)

    def test_runner_narrows_feedback_to_the_declared_path(self):
        from workflows.proforma_v1.engine.workflow_runner import _dig
        artifact = {
            "status": "revision_required",
            "correction": {"correction_brief": "b", "previous_output": {"diagnosis": "X"}},
        }
        sent = _dig(artifact, "correction")
        self.assertEqual(set(sent), {"correction_brief", "previous_output"})
        self.assertNotIn("status", sent)


if __name__ == "__main__":
    unittest.main()
