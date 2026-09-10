from __future__ import annotations

import unittest
from pathlib import Path
from unittest.mock import patch

from workflows.proforma_v1 import reasoning_runtime as rr
from workflows.proforma_v1.executors.self_executor import _reasoning_self_pass

CASE = {"case_facts": [{"fact_id": "C1", "kind": "result", "value": "Finding present"}]}
REGISTRY = {"v01": {"variant_id": "V1", "gene": "GENE1", "description": "GENE1 variant"}}
CARDS = [{"card_tag": "[card:aaaaaaaaaaaa]", "card_id": "c1", "text": "Finding has a domain-specific implication."}]
DIAGNOSIS = {"who5": {"schema_disease": "MDS"}, "icc": {}, "concurrent_pathology": []}


def point(rule="Finding has a domain-specific implication."):
    return {"rule": rule, "case_fact_ids": ["C1"], "variant_ids": ["V1"], "assessment": "met", "supports_conclusion": True, "reason": "The finding is supplied."}


def ptbg(domain):
    if domain == "prognosis":
        return {"domain":"prognosis","frameworks":[{"name":"IPSS-M","applicable":True,"tier":None,"reason":"MDS uses IPSS-M.","reasoning":[point("IPSS-M is the accepted prognostic framework for MDS.")]}],"variant_assessments":[{"variant_id":"V1","framework_effects":[],"other_evidence":{"effect":"adverse","reason":"The variant has adverse non-framework prognostic evidence.","reasoning":[point()]}}]}
    if domain == "treatment":
        return {"domain":"treatment","variant_assessments":[{"variant_id":"V1","implications":[{"category":"drug_sensitive","therapy":"Drug A","reason":"Drug A sensitivity is supported.","reasoning":[point()]}]}]}
    if domain == "biomarker":
        return {"domain":"biomarker","variant_assessments":[{"variant_id":"V1","status":"not_mrd_marker","reason":"No disease-specific MRD use is established.","reasoning":[point()]}]}
    return {"domain":"germline","variant_assessments":[{"variant_id":"V1","eligibility":"assess","predisposition_evidence":"Inherited predisposition is established for this gene/mechanism.","event_compatibility":{"status":"consistent","reason":"Compatible event."},"age":{"status":"not_assessable","reason":"No supported age direction."},"vaf":{"status":"discordant","reason":"Observed VAF weighs against constitutional origin."},"personal_history":{"status":"not_supplied","reason":"Not supplied."},"family_history":{"status":"not_supplied","reason":"Not supplied."},"phenotype":{"status":"not_assessable","reason":"No supported phenotype direction."},"bucket":"germline_uncertain","reason":"Discordant VAF and unavailable history leave the origin uncertain.","reasoning":[point()]}]}


class ReasoningPtbgTests(unittest.TestCase):
    def setUp(self):
        self.ctx = {"diagnosis": DIAGNOSIS}
        self.wrap = {"__workflow_context__": self.ctx, "__work__": Path("/tmp/reasoning-test")}
        self.cards_patch = patch.object(rr, "_ptbg_cards_for", lambda domain, context: (CASE, REGISTRY, CARDS, {}, DIAGNOSIS))
        self.envelope_patch = patch.object(rr, "_candidate_card_envelope", lambda cards, manifest: cards)
        self.cards_patch.start(); self.envelope_patch.start()
        self.addCleanup(self.cards_patch.stop); self.addCleanup(self.envelope_patch.stop)

    def test_domain_specific_ptbg_reason_then_em_contracts(self):
        for domain in rr.PTBG_DOMAINS:
            with self.subTest(domain=domain):
                self.ctx[f"{domain}_reasoning"] = ptbg(domain)
                result = rr.validate_ptbg_reasoning_v2(self.wrap, {"domain": domain})
                self.assertEqual(result["status"], "pass", result)
                pack = rr.prepare_ptbg_evidence_match_v2(self.wrap, {"domain": domain})
                self.assertEqual(len(pack["candidate_cards"]), 1)
                self.assertTrue(pack["items"])
                self.assertTrue(all("candidate_cards" not in x for x in pack["items"]))
                self.ctx[f"{domain}_evidence_match_items"] = pack
                self.ctx[f"{domain}_evidence_match"] = {"assignments": [{"reasoning_id": x["reasoning_id"], "card_tags": ["[card:aaaaaaaaaaaa]"]} for x in pack["items"]]}
                self.assertEqual(rr.validate_ptbg_evidence_match(self.wrap, {"domain": domain})["status"], "pass")


    def test_prognostic_framework_preset_uses_selected_module_asset(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as tmp:
            v1 = Path(tmp) / "v1.md"
            v2 = Path(tmp) / "v2.md"
            v1.write_text("- MDS: `IPSS-M`\n", encoding="utf-8")
            v2.write_text("- MDS: `TEST-FRAMEWORK`\n", encoding="utf-8")
            selected = {"version": "v1"}

            def fake_spec(name):
                return {"enabled": True, "version": selected["version"]}

            def fake_path(name):
                return v1 if selected["version"] == "v1" else v2

            with patch.object(rr.default_config, "module_spec", fake_spec), patch.object(rr.default_config, "module_asset_path", fake_path):
                self.assertEqual(rr._prognostic_framework_preset()["MDS"], ("IPSS-M",))
                selected["version"] = "v2"
                self.assertEqual(rr._prognostic_framework_preset()["MDS"], ("TEST-FRAMEWORK",))

    def test_prognostic_framework_preset_rejects_malformed_bullet(self):
        with self.assertRaisesRegex(ValueError, "invalid prognostic framework preset line"):
            rr._parse_prognostic_framework_preset("- MDS: IPSS-M\n")

    def test_mds_requires_ipss_m(self):
        bad = ptbg("prognosis"); bad["frameworks"] = []
        self.ctx["prognosis_reasoning"] = bad
        result=rr.validate_ptbg_reasoning_v2(self.wrap,{"domain":"prognosis"})
        self.assertEqual(result["status"],"fail")
        self.assertIn("IPSS-M",result["feedback"])

    def test_python_owns_ptbg_reportability_and_internal_ids(self):
        self.ctx["prognosis_reasoning"] = ptbg("prognosis")
        owner = rr.compile_ptbg_reasoning(self.wrap, {"domain": "prognosis"})
        self.assertTrue(owner["propositions"])
        self.assertTrue(any(p["framework"] and p["framework"]["name"]=="IPSS-M" for p in owner["propositions"]))
        adverse=[p for p in owner["propositions"] if p["bucket"]=="other_evidence_adverse"][0]
        self.assertEqual(adverse["variant_ids"],["v01"])
        self.assertTrue(adverse["reportable"])

    def test_germline_requires_full_factor_worksheet(self):
        bad=ptbg("germline"); bad["variant_assessments"][0]["vaf"]=None
        self.ctx["germline_reasoning"]=bad
        result=rr.validate_ptbg_reasoning_v2(self.wrap,{"domain":"germline"})
        self.assertEqual(result["status"],"fail")

    def test_self_passes_do_not_combine_reasoning_matching_or_audits(self):
        ids=["prognosis.reason","prognosis.em","treatment.reason","treatment.em","biomarker.reason","biomarker.em","germline.reason","germline.em","ptbg.evidence.audit","ptbg.evidence.adjudication","ptbg.reasoning.audit"]
        passes=[_reasoning_self_pass(x) for x in ids]
        self.assertTrue(all(continuous is False for _name,continuous,_note in passes))
        self.assertEqual(len({name for name,_continuous,_note in passes}),len(ids))

    def test_bad_ptbg_card_audit_routes_to_em_not_owner_reasoning(self):
        self.ctx["prognosis_reasoning"] = ptbg("prognosis")
        self.ctx["prognosis_reasoning_owner"] = rr.compile_ptbg_reasoning(self.wrap, {"domain": "prognosis"})
        mapping=rr._ptbg_atomic_rule_map(self.ctx,"prognosis")
        rid=next(iter(mapping)); atomic=mapping[rid]
        self.ctx["ptbg_evidence_audit"]={"audits":[{"rule_id":atomic,"card_tag":"[card:aaaaaaaaaaaa]","supports_rule":False,"comments":["wrong match"]}]}
        result=rr.ptbg_em_audit_review(self.wrap,{"domain":"prognosis"})
        self.assertEqual(result["status"],"fail")
        self.assertIn(rid,result["feedback"])
        self.assertNotIn(atomic,result["feedback"])


    def test_nonframework_prognosis_report_names_source(self):
        self.assertEqual(rr._source_label_for_card({"card_id":"bernard-2020-tp53-mds-C0002"}), "Bernard et al., 2020")
        self.ctx["supported"]=[{
            "schema_id":"PX-P-PROPOSITION-001", "domain":"prognosis",
            "bucket":"other_evidence_adverse", "reason":"TP53 p.Arg175His is associated with inferior survival in MDS.",
            "variants":["v01"],
            "source":{"text":"TP53 p.Arg175His is associated with inferior survival in MDS."},
            "evidence":[{"card_tag":"[card:aaaaaaaaaaaa]","card_id":"bernard-2020-tp53-mds-C0002","source_label":"Bernard et al., 2020"}],
        }]
        blocks=rr.reasoning_report_blocks(self.wrap,{})
        text=blocks[0]["components"][0]["reason"]
        self.assertIn("Bernard et al., 2020", text)
        self.assertIn("inferior survival", text)

    def test_ptbg_conclusion_coherence_is_required(self):
        self.ctx["ptbg_reasoning_items"]=[{"item_type":"conclusion","conclusion_id":"P-PROPOSITION-001"}]
        self.ctx["ptbg_reasoning_audit"]={"derived_states":[],"criteria":[],"conclusions":[{"conclusion_id":"P-PROPOSITION-001","status":"incoherent","comments":["Conclusion overstates the reasoning."]}]}
        validation=rr.validate_ptbg_reasoning_audit(self.wrap,{})
        self.assertEqual(validation["status"],"pass")

if __name__ == "__main__": unittest.main()
