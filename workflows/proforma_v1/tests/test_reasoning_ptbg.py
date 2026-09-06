from __future__ import annotations

import tempfile
import unittest
from unittest.mock import patch
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import yaml

from workflows.proforma_v1 import reasoning_runtime as rr
from workflows.proforma_v1.executors.self_executor import SelfExecutor
from workflows.proforma_v1.executors.provider import ProviderExecutor

CARD_A = "[card:aaaaaaaaaaaa]"
CARD_B = "[card:bbbbbbbbbbbb]"


class FakeContext:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.work = Path(tempfile.mkdtemp())
        self.executor = "self"
    def get(self, key, default=None):
        return self.data.get(key, default)
    def put(self, key, value):
        self.data[key] = value


def pack(domain):
    return {
        "domain": domain,
        "structured_case": {"case_facts": [
            {"fact_id": "C1", "kind": "molecular", "value": "NPM1 mutation present"},
            {"fact_id": "C2", "kind": "molecular", "value": "IDH1 R132H present"},
            {"fact_id": "C3", "kind": "germline", "value": "VAF 12%"},
        ]},
        "case_fact_registry": {
            "C1": {"fact_id": "C1", "kind": "molecular", "value": "NPM1 mutation present"},
            "C2": {"fact_id": "C2", "kind": "molecular", "value": "IDH1 R132H present"},
            "C3": {"fact_id": "C3", "kind": "germline", "value": "VAF 12%"},
        },
        "variant_registry": {"v01": {"description": "NPM1 mutation"}, "v02": {"description": "IDH1 R132H"}},
        "candidate_cards": [
            {"card_tag": CARD_A, "card_id": "A", "claim": "framework rule"},
            {"card_tag": CARD_B, "card_id": "B", "claim": "other rule"},
        ],
    }


def proposition(domain):
    prefix = rr.PTBG_PREFIX[domain]
    if domain == "prognosis":
        return {
            "proposition_id": prefix+"P1", "bucket": "prognostic_framework", "text": "Framework adverse effect applies", "reason": "Framework interpretation", "variant_ids": ["v01"], "reportable": True,
            "rules": [{"rule_id": prefix+"R1", "statement": "The framework assigns an adverse effect to the qualifying molecular state.", "evidence_required": True, "proposed_card_tags": [CARD_A], "direct_requirement": None}],
            "derived_states": [{"state_id": prefix+"S1", "label": "qualifying molecular state", "case_fact_ids": ["C1"], "variant_ids": ["v01"], "proposed_value": "qualifying", "reason": "Requires semantic interpretation."}],
            "applications": [{"application_id": prefix+"A1", "rule_ids": [prefix+"R1"], "case_fact_ids": ["C1"], "state_ids": [prefix+"S1"], "mode": "semantic", "direct_match": None, "proposed_status": "met", "reason": "Apply framework to patient state."}],
            "conclusion": {"operator": "all_of", "application_ids": [prefix+"A1"]},
            "framework": {"name": "Example framework", "applicability_application_id": prefix+"A1"}, "worksheet": [],
        }
    if domain == "treatment":
        return {
            "proposition_id": prefix+"P1", "bucket": "drug_target", "text": "IDH1-directed treatment implication", "reason": "Exact mutation present", "variant_ids": ["v02"], "reportable": True,
            "rules": [{"rule_id": prefix+"R1", "statement": "IDH1 R132H is an actionable treatment target in this disease context.", "evidence_required": True, "proposed_card_tags": [CARD_B], "direct_requirement": {"fact_kind": "molecular", "expected_value": "IDH1 R132H present"}}],
            "derived_states": [],
            "applications": [{"application_id": prefix+"A1", "rule_ids": [prefix+"R1"], "case_fact_ids": ["C2"], "state_ids": [], "mode": "direct", "direct_match": {"case_fact_id": "C2", "expected_value": "IDH1 R132H present"}, "proposed_status": "met", "reason": "Literal mutation match."}],
            "conclusion": {"operator": "all_of", "application_ids": [prefix+"A1"]}, "framework": None, "worksheet": [],
        }
    if domain == "biomarker":
        return {
            "proposition_id": prefix+"P1", "bucket": "mrd_marker", "text": "NPM1 is a follow-up marker", "reason": "Marker is present", "variant_ids": ["v01"], "reportable": False,
            "rules": [], "derived_states": [], "applications": [], "conclusion": {"operator": "all_of", "application_ids": []}, "framework": None, "worksheet": [],
        }
    return {
        "proposition_id": prefix+"P1", "bucket": "germline_uncertain", "text": "Germline predisposition remains uncertain", "reason": "Discordant VAF requires interpretation", "variant_ids": ["v01"], "reportable": True,
        "rules": [{"rule_id": prefix+"R1", "statement": "The gene is associated with inherited predisposition.", "evidence_required": True, "proposed_card_tags": [CARD_A], "direct_requirement": None}],
        "derived_states": [],
        "applications": [{"application_id": prefix+"A1", "rule_ids": [prefix+"R1"], "case_fact_ids": ["C3"], "state_ids": [], "mode": "semantic", "direct_match": None, "proposed_status": "unknown", "reason": "VAF needs clinical interpretation."}],
        "conclusion": {"operator": "all_of", "application_ids": [prefix+"A1"]}, "framework": None,
        "worksheet": [
            {"factor":"predisposition_evidence","application_id":None,"status":"supportive","reason":"A predisposition rule was proposed for independent evidence audit."},
            {"factor":"event_compatibility","application_id":None,"status":"not_assessable","reason":"No separate event-compatibility fact was supplied in this fixture."},
            {"factor":"age","application_id":None,"status":"not_supplied","reason":"Age is not supplied in this fixture."},
            {"factor":"vaf","application_id":prefix+"A1","status":"discordant","reason":"Observed VAF is discordant with a simple constitutional expectation."},
            {"factor":"personal_history","application_id":None,"status":"not_supplied","reason":"Personal history is not supplied in this fixture."},
            {"factor":"family_history","application_id":None,"status":"not_supplied","reason":"Family history is not supplied in this fixture."},
            {"factor":"phenotype","application_id":None,"status":"not_supplied","reason":"Phenotype is not supplied in this fixture."},
        ],
    }


def build_context():
    ctx=FakeContext()
    for domain in rr.PTBG_DOMAINS:
        ctx.put(rr._ptbg_pack_key(domain), pack(domain))
        ctx.put(rr._ptbg_owner_key(domain), {"domain": domain, "propositions": [proposition(domain)]})
    return ctx


class ReasoningPtbgTests(unittest.TestCase):
    def test_ptbg_owner_validation_reports_all_reference_and_direct_match_errors(self):
        ctx=build_context(); owner=ctx.get("treatment_reasoning_owner"); prop=owner["propositions"][0]
        prop["rules"][0]["rule_id"]="BAD-R"; prop["rules"][0]["proposed_card_tags"]=["[card:cccccccccccc]"]
        prop["applications"][0]["rule_ids"]=["MISSING"]; prop["applications"][0]["case_fact_ids"]=["C999"]; prop["applications"][0]["direct_match"]={"case_fact_id":"C2","expected_value":"IDH1 R132H present"}
        result=rr.validate_ptbg_owner({"__workflow_context__":ctx},{"step_id":"treatment.validate"})
        self.assertEqual(result["status"],"fail")
        codes={x["code"] for x in result["issues"]}
        self.assertIn("wrong_reasoning_namespace",codes); self.assertIn("card_outside_owner_envelope",codes); self.assertIn("unknown_rule_id",codes); self.assertIn("unknown_case_fact_id",codes); self.assertIn("direct_fact_not_declared",codes)
        self.assertGreaterEqual(result["feedback"].count("What is wrong:"),5)

    def test_valid_owner_assignments_make_matching_rescue_only(self):
        ctx=build_context(); payload={"__workflow_context__":ctx}; reg=rr.build_ptbg_registry(payload,{}); ctx.put("ptbg_atomic_registry",reg)
        state=rr.collect_ptbg_owner_assignments(payload,{}); ctx.put("ptbg_owner_assignments",state)
        self.assertEqual(state["rescue_items"],[])
        self.assertEqual({x["source"] for x in state["pairs"]},{"owner"})

    def test_direct_treatment_application_bypasses_reasoning_model(self):
        ctx=build_context(); payload={"__workflow_context__":ctx}; reg=rr.build_ptbg_registry(payload,{}); ctx.put("ptbg_atomic_registry",reg)
        ctx.put("ptbg_evidence_decisions",{"rule_support":{r["rule_id"]:True for r in reg["rules"]}})
        direct=rr.evaluate_ptbg_direct_applications(payload,{}); ctx.put("ptbg_direct_applications",direct)
        self.assertEqual(next(x for x in direct if x["application_id"]=="T-A1")["status"],"met")
        items=rr.prepare_ptbg_reasoning_audit(payload,{})
        semantic_ids={x["application"]["application_id"] for x in items if x.get("item_type")=="application"}
        self.assertNotIn("T-A1",semantic_ids); self.assertIn("P-A1",semantic_ids); self.assertIn("G-A1",semantic_ids)

    def test_ptbg_evaluation_separates_framework_state_and_germline_factor(self):
        ctx=build_context(); payload={"__workflow_context__":ctx}; reg=rr.build_ptbg_registry(payload,{}); ctx.put("ptbg_atomic_registry",reg)
        support={r["rule_id"]:True for r in reg["rules"]}; ctx.put("ptbg_evidence_decisions",{"rule_support":support})
        ctx.put("ptbg_direct_applications",rr.evaluate_ptbg_direct_applications(payload,{}))
        ctx.put("ptbg_reasoning_audit",{"derived_states":[{"state_id":"P-S1","status":"supported","value":"qualifying","case_fact_ids":["C1"],"comments":["supported"]}],"criteria":[{"criterion_id":"P-A1","status":"met","case_fact_ids":["C1"],"comments":["framework applies"]},{"criterion_id":"G-A1","status":"not_met","case_fact_ids":["C3"],"comments":["discordant VAF weighs against the proposed application"]}]})
        result=rr.evaluate_ptbg(payload,{}); ctx.put("ptbg_evaluation",result)
        by={x["proposition_id"]:x for x in result["propositions"]}
        self.assertEqual(by["P-P1"]["disposition"],"kept"); self.assertEqual(by["T-P1"]["disposition"],"kept"); self.assertEqual(by["B-P1"]["disposition"],"not_reportable"); self.assertEqual(by["G-P1"]["disposition"],"dropped")
        review=rr.ptbg_owner_review(payload,{"step_id":"germline.review"}); self.assertEqual(review["status"],"fail"); self.assertIn("G-P1",review["feedback"]); self.assertIn("discordant VAF",review["feedback"])

    def test_decision_ledger_and_dissent_show_facts_kept_and_dropped_reasons(self):
        ctx=build_context(); payload={"__workflow_context__":ctx}; reg=rr.build_ptbg_registry(payload,{}); ctx.put("ptbg_atomic_registry",reg)
        pairs=[]; accepted={}; support={}
        for r in reg["rules"]:
            support[r["rule_id"]]=True; accepted[r["rule_id"]]=list(r.get("proposed_card_tags") or []); pairs += [{"rule_id":r["rule_id"],"card_tag":tag,"supports_rule":True} for tag in accepted[r["rule_id"]]]
        ctx.put("ptbg_evidence_decisions",{"rule_support":support,"accepted_card_tags_by_rule":accepted,"pairs":pairs}); ctx.put("ptbg_direct_applications",rr.evaluate_ptbg_direct_applications(payload,{}))
        ctx.put("ptbg_reasoning_audit",{"derived_states":[{"state_id":"P-S1","status":"supported","value":"qualifying","case_fact_ids":["C1"],"comments":["supported"]}],"criteria":[{"criterion_id":"P-A1","status":"met","case_fact_ids":["C1"],"comments":["met"]},{"criterion_id":"G-A1","status":"not_met","case_fact_ids":["C3"],"comments":["discordant VAF"]}]})
        ctx.put("ptbg_evaluation",rr.evaluate_ptbg(payload,{})); ctx.put("diagnostic_evaluation",{"owner_status":{"who5":"pass","icc":"pass","second_diagnosis":"pass"},"feedback":{}}); ctx.put("diagnostic_evidence_decisions",{"rule_support":{},"pairs":[]}); ctx.put("diagnostic_atomic_registry",{"rules":[],"derived_states":[]}); ctx.put("diagnostic_reasoning_audit",{"derived_states":[],"criteria":[]})
        ledger=rr.build_decision_ledger(payload,{}); ctx.put("decision_ledger",ledger)
        dispositions={x["decision_id"]:x["disposition"] for x in ledger["decisions"]}
        self.assertEqual(dispositions["P-P1"],"kept"); self.assertEqual(dispositions["G-P1"],"dropped"); self.assertEqual(dispositions["P-S1"],"kept")
        fact_ids={x["fact_id"] for x in ledger["facts_considered"]}
        self.assertIn("C1",fact_ids); self.assertIn("C3",fact_ids); self.assertIn("v01",fact_ids); self.assertIn("v02",fact_ids)
        treatment_decision=next(x for x in ledger["decisions"] if x["decision_id"]=="T-P1")
        self.assertEqual(treatment_decision["variant_ids"],["v02"])
        text=rr.render_reasoning_dissent(ledger,{"summary":"A concise ledger summary.","highlights":[]})
        self.assertIn("## Facts considered",text); self.assertIn("## Considered and kept",text); self.assertIn("## Dropped",text); self.assertIn("G-P1",text); self.assertIn("discordant",text.lower()); self.assertIn("Variants considered",text)

    def test_dissent_summary_cannot_change_ledger_disposition(self):
        ctx=FakeContext({"decision_ledger":{"decisions":[{"decision_id":"P-P1","disposition":"dropped"}],"facts_considered":[],"counts":{"kept":0,"revised":0,"dropped":1,"unresolved":0,"not_reportable":0}},"dissent_summary":{"summary":"Wrong","highlights":[{"decision_id":"P-P1","disposition":"kept","explanation":"changed"}]}})
        result=rr.validate_dissent_summary({"__workflow_context__":ctx},{})
        self.assertEqual(result["status"],"fail"); self.assertIn("changed_ledger_disposition",{x["code"] for x in result["issues"]})

    def test_self_groups_four_ptbg_owners_into_one_frontier_handoff(self):
        calls=[]
        def generic(step,ctx):
            calls.append(step.id); return {"status":"handoff","handoff":{"stage":step.id,"manifest":{"output":step.id+".yaml"}}}
        ex=SelfExecutor({"generic_model":generic}); ctx=FakeContext()
        steps=[SimpleNamespace(id=d,execution={"self_handler":"reasoning_model","self_group":"ptbg_owners"},output={}) for d in rr.PTBG_DOMAINS]
        result=ex.execute_group(steps,ctx); manifest=result["handoff"]["manifest"]
        self.assertEqual(result["handoff"]["stage"],"ptbg_owners"); self.assertEqual(set(manifest["operations"]),set(rr.PTBG_DOMAINS)); self.assertEqual(calls,list(rr.PTBG_DOMAINS))

    def test_self_final_presentation_groups_report_and_summary(self):
        def report(step,ctx): return {"status":"handoff","handoff":{"stage":"report","manifest":{"output":"report.yaml"}}}
        def generic(step,ctx): return {"status":"handoff","handoff":{"stage":"summary","manifest":{"output":"summary.yaml"}}}
        ex=SelfExecutor({"report_write":report,"generic_model":generic}); ctx=FakeContext()
        steps=[SimpleNamespace(id="report.write",execution={"self_handler":"report_write","self_group":"final_presentation"},output={}),SimpleNamespace(id="dissent.summary",execution={"self_handler":"reasoning_optional_model","self_group":"final_presentation"},output={})]
        result=ex.execute_group(steps,ctx); self.assertEqual(result["handoff"]["stage"],"final_presentation"); self.assertEqual(set(result["handoff"]["manifest"]["operations"]),{"report.write","dissent.summary"})



    def test_germline_worksheet_requires_all_canonical_factors_and_explicit_statuses(self):
        ctx=build_context(); owner=ctx.get("germline_reasoning_owner"); owner["propositions"][0]["worksheet"]=owner["propositions"][0]["worksheet"][:-1]
        result=rr.validate_ptbg_owner({"__workflow_context__":ctx},{"step_id":"germline.validate"})
        self.assertEqual(result["status"],"fail")
        self.assertIn("missing_germline_factors",{x["code"] for x in result["issues"]})
        self.assertIn("phenotype",result["feedback"])

    def test_direct_application_requires_requirement_from_evidence_audited_rule(self):
        ctx=build_context(); owner=ctx.get("treatment_reasoning_owner"); owner["propositions"][0]["rules"][0]["direct_requirement"]=None
        result=rr.validate_ptbg_owner({"__workflow_context__":ctx},{"step_id":"treatment.validate"})
        self.assertEqual(result["status"],"fail")
        self.assertIn("unaudited_direct_requirement",{x["code"] for x in result["issues"]})

    def test_optional_dissent_summary_provider_failure_falls_back_without_blocking(self):
        ctx=FakeContext(); out=ctx.work/"summary.yaml"
        artifacts=types.ModuleType("workflows.proforma_v1.engine.artifacts")
        artifacts.generic_output_path=lambda work,step,create=False: out
        step=SimpleNamespace(id="dissent.summary",execution={"provider_handler":"reasoning_optional_model"},output={"artifact":"dissent_summary","format":"yaml","schema":"ignored.json"})
        ex=ProviderExecutor({"generic_model":lambda step,ctx: (_ for _ in ()).throw(RuntimeError("provider down"))})
        with patch.dict(sys.modules,{"workflows.proforma_v1.engine.artifacts":artifacts}):
            result=ex.execute(step,ctx)
        self.assertEqual(result["status"],"complete")
        self.assertTrue(out.is_file())
        self.assertEqual(yaml.safe_load(out.read_text()),{"summary":"","highlights":[]})

    def test_reasoning_owner_invalidation_deletes_generic_artifact_not_legacy_ptbg_path(self):
        ctx=FakeContext(); out=ctx.work/"prognosis-owner.yaml"; out.write_text("domain: prognosis\npropositions: []\n")
        artifacts=types.ModuleType("workflows.proforma_v1.engine.artifacts")
        artifacts.generic_output_path=lambda work,step,create=False: out
        step=SimpleNamespace(id="prognosis",execution={"self_handler":"reasoning_model"},output={})
        workflow=SimpleNamespace(step=lambda sid: step)
        ctx.put("workflow",workflow)
        ex=SelfExecutor({})
        with patch.dict(sys.modules,{"workflows.proforma_v1.engine.artifacts":artifacts}):
            ex.invalidate({"prognosis"},ctx)
        self.assertFalse(out.exists())

    def test_committed_diagnostic_fallback_remains_reportable_without_false_evidence(self):
        ctx=FakeContext({
            "diagnosis": {
                "who5": {"schema_disease":"MDS","diagnosis":"MDS","reason":"Supplied diagnosis retained after unsupported refinement.","variants":[]},
                "icc": {"diagnosis":"MDS","reason":"Supplied diagnosis retained after unsupported refinement.","variants":[]},
                "concurrent_pathology": [],
            },
            "diagnostic_atomic_registry": {"rules": []},
            "diagnostic_evidence_decisions": {"pairs": []},
            "diagnostic_evaluation": {"owner_status": {"who5":"fail","icc":"fail","second_diagnosis":"pass"}},
            "ptbg_atomic_registry": {"rules": [], "propositions": []},
            "ptbg_evaluation": {"propositions": []},
            "ptbg_evidence_decisions": {"accepted_card_tags_by_rule": {}},
        })
        elements=rr.finalize_atomic_evidence({"__workflow_context__":ctx},{})
        by={x["schema_id"]:x for x in elements}
        self.assertIn("DX-WHO5",by); self.assertIn("DX-ICC",by)
        self.assertEqual(by["DX-WHO5"]["source"]["diagnosis"],"MDS")
        self.assertEqual(by["DX-WHO5"]["evidence"],[])
        self.assertEqual(by["DX-ICC"]["evidence"],[])

    def test_ptbg_evidence_adjudication_is_not_continuation_of_auditor_pass(self):
        ex=SelfExecutor({"generic_model":lambda step,ctx:{"status":"handoff","handoff":{"stage":step.id,"manifest":{}}}}); ctx=FakeContext()
        for sid,expected,continuous in (("ptbg.evidence.audit","ptbg_review",True),("ptbg.reasoning.audit","ptbg_review",True),("ptbg.evidence.adjudication","ptbg_adjudication",False)):
            step=SimpleNamespace(id=sid,execution={"self_handler":"reasoning_model"},output={}); m=ex.execute(step,ctx)["handoff"]["manifest"]; self.assertEqual(m["self_pass"],expected); self.assertEqual(m["continue_in_same_frontier_pass"],continuous)


if __name__ == "__main__":
    unittest.main()
