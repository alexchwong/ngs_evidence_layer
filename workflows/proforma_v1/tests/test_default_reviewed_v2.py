"""Structural invariants for the ``default_reviewed_v2`` audit overlay.

These tests encode the two properties that stop this workflow becoming the
thing it replaces:

* the clinical head is a byte-identical clone of ``default``;
* repair loops are capped structurally, not by convention.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parents[1]
ROOT = HERE.parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from workflows.proforma_v1 import default_reviewed_v2 as v2  # noqa: E402
from workflows.proforma_v1.engine import transforms, workflow_compiler, workflow_progress  # noqa: E402

DEFAULT = HERE / "workflow" / "default.yaml"
V2 = HERE / "workflow" / "default_reviewed_v2.yaml"
REVIEWED = HERE / "workflow" / "default_reviewed.yaml"

# Every clinical owner step must survive the clone untouched.
CLINICAL_STEPS = (
    "structure", "corpus",
    "diagnosis.who1", "diagnosis.who1.routing_change",
    "diagnosis.who1.evidence.assignment", "diagnosis.who1.evidence.audit",
    "diagnosis.who1.evidence.adjudication", "diagnosis.who1.commit",
    "diagnosis.who2", "diagnosis.icc",
    "prognosis", "treatment", "biomarker", "germline",
)
# The three-stage evidence chain is retained, not merged.
EVIDENCE_STEPS = ("evidence.assignment", "evidence.audit", "evidence.adjudication", "evidence.finalize")

ADDED_STEPS = (
    "audit.dx.packet", "audit.dx.coherence", "audit.dx.validate",
    "audit.dx.targets", "audit.dx.revise", "audit.dx.commit",
    "audit.ptbg.packet", "audit.ptbg.coherence", "audit.ptbg.validate",
    "audit.ptbg.targets", "audit.ptbg.revise", "audit.ptbg.commit",
)


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
        """Cloning must not have edited the shipped workflow."""
        self.assertNotIn("audit.dx.coherence", self.default["steps"])
        self.assertNotIn("audit.ptbg.coherence", self.default["steps"])

    def test_cloned_from_default_not_default_reviewed(self):
        reviewed = _load(REVIEWED)["steps"]
        secretarial = [sid for sid in reviewed if ".secretary" in sid or ".precheck" in sid or ".postcheck" in sid]
        self.assertTrue(secretarial, "fixture expectation: default_reviewed has secretary/precheck steps")
        for sid in secretarial:
            self.assertNotIn(sid, self.steps, f"v2 must not inherit {sid!r} from default_reviewed")

    def test_clinical_owner_steps_identical_to_default(self):
        for sid in CLINICAL_STEPS:
            self.assertIn(sid, self.steps, sid)
            self.assertEqual(self.steps[sid], self.default["steps"][sid], f"clinical step {sid!r} diverged from default")

    def test_three_stage_evidence_chain_retained_unchanged(self):
        for sid in EVIDENCE_STEPS:
            self.assertIn(sid, self.steps, sid)
            self.assertEqual(self.steps[sid], self.default["steps"][sid], f"evidence step {sid!r} diverged from default")
        self.assertEqual(self.doc["evidence_policies"], self.default["evidence_policies"])

    def test_report_pipeline_reused(self):
        for sid in ("report.write", "report.preservation", "report.finalize"):
            self.assertEqual(self.steps[sid], self.default["steps"][sid], sid)

    def test_added_steps_present(self):
        for sid in ADDED_STEPS:
            self.assertIn(sid, self.steps, sid)

    def test_step_count_stays_small(self):
        # default_reviewed is 92 declared steps; the overlay must not drift there.
        self.assertLessEqual(len(self.steps), 40, "v2 step count is drifting toward default_reviewed")

    def test_progress_plan_covers_every_step(self):
        workflow = workflow_compiler.compile_workflow(V2)
        plan = workflow_progress.load_progress_plan(workflow)
        covered = {sid for phase in plan["phases"] for sid in phase["steps"]}
        self.assertEqual(covered, {step.id for step in workflow.steps})


class RepairLoopCapTests(unittest.TestCase):
    """Fix 2: repair loops are capped by the build, not by convention.

    The cap governs steps the overlay adds.  ``default``'s single inherited
    evidence audit-resolution loop is retained deliberately, along with the rest
    of the three-stage chain, and is separately pinned byte-identical so it
    cannot be widened under cover of this exemption.
    """

    @classmethod
    def setUpClass(cls):
        cls.default = _load(DEFAULT)["steps"]
        cls.steps = _load(V2)["steps"]
        cls.reviews = {sid: cfg["review"] for sid, cfg in cls.steps.items() if cfg.get("review")}
        cls.added = {sid: r for sid, r in cls.reviews.items() if sid in ADDED_STEPS}
        cls.inherited = {sid: r for sid, r in cls.reviews.items() if sid not in ADDED_STEPS}

    def test_at_most_one_added_review_block(self):
        self.assertLessEqual(
            len(self.added), 1,
            f"v2 adds {len(self.added)} review blocks: {sorted(self.added)}. "
            "Each additional block is a feedback loop with cascade invalidation.",
        )

    def test_inherited_reviews_are_unchanged_from_default(self):
        for sid in self.inherited:
            self.assertIn(sid, self.default, f"{sid!r} is not an inherited default step")
            self.assertEqual(self.steps[sid], self.default[sid], f"inherited review {sid!r} was modified")

    def test_no_added_review_declares_feedback(self):
        for sid, review in self.added.items():
            self.assertNotIn(
                "feedback", review["on_fail"],
                f"{sid!r} feeds prior output back to the model; retries must regenerate cleanly",
            )

    def test_added_review_allows_at_most_one_regeneration(self):
        for sid, review in self.added.items():
            self.assertLessEqual(review["on_fail"].get("max_cycles", 0), 1, sid)

    def test_added_review_failure_is_visible_not_terminal_silence(self):
        for sid, review in self.added.items():
            self.assertEqual(review["on_fail"]["exhausted"]["action"], "continue_with_dissent", sid)

    def test_no_added_model_step_beyond_the_capped_one_is_reviewed(self):
        reviewed_targets = {r["target"] for r in self.added.values()}
        self.assertEqual(reviewed_targets, {"audit.dx.coherence"})

    def test_default_reviewed_would_fail_this_cap(self):
        """Guards against the cap being weakened until it no longer bites."""
        reviewed = _load(REVIEWED)["steps"]
        count = sum(1 for cfg in reviewed.values() if cfg.get("review"))
        self.assertGreater(count, 1, "fixture expectation: default_reviewed is loop-heavy")


class ExecutorNeutralityTests(unittest.TestCase):
    """Fix 3: no new handler code in either executor."""

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


class GatingTests(unittest.TestCase):
    """Fix 4: diagnosis coherence is unconditional; PTBG coherence is gated."""

    @classmethod
    def setUpClass(cls):
        cls.steps = _load(V2)["steps"]

    def test_diagnosis_coherence_is_unconditional(self):
        self.assertNotIn(
            "when", self.steps["audit.dx.coherence"],
            "gating diagnosis coherence drops the conclusion-vs-premise case it exists to catch",
        )
        self.assertNotIn("when", self.steps["audit.dx.packet"])

    def test_ptbg_coherence_is_gated(self):
        self.assertEqual(
            self.steps["audit.ptbg.coherence"]["when"], {"has_items": {"artifact": "v2_ptbg_packet"}}
        )

    def test_revision_steps_are_gated(self):
        self.assertEqual(self.steps["audit.dx.revise"]["when"], {"has_items": {"artifact": "v2_dx_targets"}})
        self.assertEqual(self.steps["audit.ptbg.revise"]["when"], {"has_items": {"artifact": "v2_ptbg_targets"}})

    def test_coherence_prompts_supply_no_corpus(self):
        for name in ("diagnosis_coherence.md", "ptbg_coherence.md", "revise.md"):
            text = (HERE / "prompts" / "default_reviewed_v2" / name).read_text(encoding="utf-8")
            self.assertNotIn("{{ input.cards", text)
            self.assertIn("no corpus", text.lower())

    def test_coherence_call_count_is_bounded(self):
        """At most one diagnosis coherence call, not one per authority."""
        coherence = [sid for sid in self.steps if sid.endswith(".coherence")]
        self.assertEqual(sorted(coherence), ["audit.dx.coherence", "audit.ptbg.coherence"])


class DeterministicValidationTests(unittest.TestCase):
    """Validation enforces deterministic facts only; dissent is never a failure."""

    def _validate(self, doc, expected, field="authority"):
        return v2._validate_review_rows(doc, expected, field)

    def test_accepts_well_formed_output(self):
        doc = {"reviews": [
            {"authority": "who1", "status": "pass", "issues": []},
            {"authority": "icc", "status": "pass", "issues": []},
        ]}
        self.assertEqual(self._validate(doc, ["who1", "icc"]), [])

    def test_semantic_disagreement_is_not_a_structural_failure(self):
        doc = {"reviews": [{
            "authority": "who1", "status": "revision_required", "scope": "reason",
            "issues": ["The stated reasons deny the named entity."],
        }]}
        self.assertEqual(self._validate(doc, ["who1"]), [])

    def test_missing_row_is_rejected(self):
        doc = {"reviews": [{"authority": "who1", "status": "pass"}]}
        self.assertTrue(self._validate(doc, ["who1", "icc"]))

    def test_unsupplied_key_is_rejected(self):
        doc = {"reviews": [{"authority": "who2", "status": "pass"}]}
        issues = self._validate(doc, ["who1"])
        self.assertTrue(any("unsupplied" in i for i in issues))

    def test_duplicate_key_is_rejected(self):
        doc = {"reviews": [
            {"authority": "who1", "status": "pass"},
            {"authority": "who1", "status": "pass"},
        ]}
        self.assertTrue(any("duplicate" in i for i in self._validate(doc, ["who1"])))

    def test_unknown_status_is_rejected(self):
        doc = {"reviews": [{"authority": "who1", "status": "probably_fine"}]}
        self.assertTrue(self._validate(doc, ["who1"]))

    def test_revision_without_scope_is_rejected(self):
        doc = {"reviews": [{"authority": "who1", "status": "revision_required", "issues": ["x"]}]}
        self.assertTrue(any("scope" in i for i in self._validate(doc, ["who1"])))

    def test_revision_without_issue_is_rejected(self):
        doc = {"reviews": [{"authority": "who1", "status": "revision_required", "scope": "reason", "issues": []}]}
        self.assertTrue(any("states no issue" in i for i in self._validate(doc, ["who1"])))

    def test_non_mapping_output_is_rejected(self):
        self.assertTrue(self._validate(["reviews"], ["who1"]))


class AddressingTests(unittest.TestCase):
    """Revision targets resolve positionally; never by matching prose."""

    def test_schema_id_resolves_to_domain_bucket_index(self):
        self.assertEqual(
            v2.resolve_ptbg_address("PX-OTHER_EVIDENCE_ADVERSE-01"),
            ("prognosis", "other_evidence_adverse", 0),
        )
        self.assertEqual(v2.resolve_ptbg_address("TX-THERAPY-03")[0], "treatment")
        self.assertEqual(v2.resolve_ptbg_address("MRD-MARKER-02")[0], "biomarker")
        self.assertEqual(v2.resolve_ptbg_address("GL-SUSPECTED-01")[0], "germline")

    def test_malformed_address_is_refused_not_guessed(self):
        for reference in ("", "PX", "PX-BUCKET", "ZZ-BUCKET-01", "PX-BUCKET-XX", "PX-BUCKET-00"):
            self.assertIsNone(v2.resolve_ptbg_address(reference), reference)

    def test_evidence_context_is_derived_from_address_only(self):
        self.assertEqual(v2.evidence_context("DX-WHO5"), "diagnosis_who5")
        self.assertEqual(v2.evidence_context("DX-ICC"), "diagnosis_icc")
        self.assertEqual(v2.evidence_context("PX-FRAMEWORK-01"), "prognosis_framework")
        self.assertEqual(v2.evidence_context("PX-OTHER_EVIDENCE_ADVERSE-01"), "prognosis_other")
        self.assertEqual(v2.evidence_context("TX-A-01"), "treatment")
        self.assertEqual(v2.evidence_context("MRD-A-01"), "biomarker")
        self.assertEqual(v2.evidence_context("GL-A-01"), "germline")

    def test_who_and_icc_contexts_never_collide(self):
        self.assertNotEqual(v2.evidence_context("DX-WHO5"), v2.evidence_context("DX-ICC"))

    def test_framework_and_non_framework_contexts_are_distinct(self):
        self.assertNotEqual(
            v2.evidence_context("PX-FRAMEWORK-01"),
            v2.evidence_context("PX-OTHER_EVIDENCE_ADVERSE-01"),
        )


class ConclusionSafetyTests(unittest.TestCase):
    """Python patches named owner fields only; it never rewrites a conclusion."""

    def test_patchable_fields_are_reason_only(self):
        self.assertEqual(v2.PATCHABLE_DIAGNOSIS_FIELDS, ("reason",))
        self.assertEqual(v2.PATCHABLE_PTBG_FIELDS, ("reason",))

    def test_revision_schema_permits_only_index_and_reason(self):
        import json
        schema = json.loads((HERE / "schemas" / "default_reviewed_v2" / "revision.json").read_text())
        row = schema["properties"]["revisions"]["items"]
        self.assertEqual(set(row["properties"]), {"index", "reason"})
        self.assertFalse(row["additionalProperties"])

    def test_coherence_schema_forbids_extra_fields(self):
        import json
        for name in ("diagnosis_coherence.json", "ptbg_coherence.json"):
            schema = json.loads((HERE / "schemas" / "default_reviewed_v2" / name).read_text())
            self.assertFalse(schema["additionalProperties"], name)
            self.assertFalse(schema["properties"]["reviews"]["items"]["additionalProperties"], name)

    def test_conclusion_scope_is_a_declared_status(self):
        self.assertIn("conclusion", v2.REVISION_SCOPES)
        self.assertEqual(v2.COHERENCE_STATUSES, ("pass", "revision_required"))


class PatchBehaviourTests(unittest.TestCase):
    """The commit step patches named fields and nothing else."""

    def setUp(self):
        import tempfile
        from workflows.proforma_v1 import self_runtime as sr
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)
        self.proforma = {
            "applicable_disease": "MDS",
            "other_evidence_adverse": [
                {"variants": ["V1"], "reason": "Monoallelic TP53 is independently adverse in MDS.",
                 "evidence_card_tags": ["[card:aaaaaaaaaaaa]"]},
                {"variants": ["V2"], "reason": "Untouched row.",
                 "evidence_card_tags": ["[card:bbbbbbbbbbbb]"]},
            ],
        }
        sr.write_yaml(sr.output_path(self.work, "prognosis_state", "proforma.yaml"), self.proforma)

    def _read(self):
        from workflows.proforma_v1 import self_runtime as sr
        return sr.read_yaml(sr.output_path(self.work, "prognosis_state", "proforma.yaml"))

    def test_rescope_replaces_only_the_addressed_reason(self):
        ok = v2._patch_ptbg_reason(self.work, "PX-OTHER_EVIDENCE_ADVERSE-01", "A single TP53 variant is monoallelic.")
        self.assertTrue(ok)
        doc = self._read()
        rows = doc["other_evidence_adverse"]
        self.assertEqual(rows[0]["reason"], "A single TP53 variant is monoallelic.")
        self.assertEqual(rows[0]["evidence_card_tags"], ["[card:aaaaaaaaaaaa]"])
        self.assertEqual(rows[1], self.proforma["other_evidence_adverse"][1])
        self.assertEqual(doc["applicable_disease"], "MDS")

    def test_removal_clears_the_orphaned_card_tags(self):
        self.assertTrue(v2._patch_ptbg_reason(self.work, "PX-OTHER_EVIDENCE_ADVERSE-01", None))
        row = self._read()["other_evidence_adverse"][0]
        self.assertIsNone(row["reason"])
        self.assertEqual(row["evidence_card_tags"], [])

    def test_out_of_range_address_changes_nothing(self):
        self.assertFalse(v2._patch_ptbg_reason(self.work, "PX-OTHER_EVIDENCE_ADVERSE-09", "x"))
        self.assertEqual(self._read(), self.proforma)

    def test_unknown_bucket_changes_nothing(self):
        self.assertFalse(v2._patch_ptbg_reason(self.work, "PX-NO_SUCH_BUCKET-01", "x"))
        self.assertEqual(self._read(), self.proforma)

    def test_reasons_split_on_line_breaks_only(self):
        """Presentation split, never sentence-level atomisation."""
        text = "one TP53 variant. no del(17p).\ntherefore not MDS with mutated TP53"
        self.assertEqual(v2._reasons(text), [
            "one TP53 variant. no del(17p).",
            "therefore not MDS with mutated TP53",
        ])
        self.assertEqual(v2._reasons(None), [])


if __name__ == "__main__":
    unittest.main()
