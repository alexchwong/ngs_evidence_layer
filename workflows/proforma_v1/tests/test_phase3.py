from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from jsonschema import Draft202012Validator

from workflows.proforma_v1 import domain_contract, layout, rules, self as self_executor, self_runtime, step as staged
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_compiler import compile_workflow

HERE = Path(__file__).resolve().parents[1]
DEFAULT = HERE / "workflow" / "default.yaml"


class Phase3WorkflowTests(unittest.TestCase):
    def test_default_workflow_declares_phase3_routing_and_owner_evidence(self):
        workflow=compile_workflow()
        self.assertEqual(workflow.step("diagnosis.who1.routing_change").transform, "assess_who1_routing_change")
        self.assertEqual(workflow.step("diagnosis.who1.evidence.assignment").evidence["timing"], "blocking")
        self.assertEqual(workflow.step("diagnosis.who1.evidence.assignment").evidence["policy"], "diagnosis_complete_support")
        self.assertEqual(workflow.step("diagnosis.who1.commit").transform, "commit_who1_routing")
        self.assertEqual(workflow.step("diagnosis.who2").needs, ("diagnosis.who1.commit",))
        for domain in ("prognosis","treatment","biomarker","germline"):
            self.assertTrue(workflow.step(domain).evidence["owner_assignment"])
        self.assertEqual(workflow.step("evidence.assignment").evidence["rescue_match_passes"], 1)
        self.assertEqual(workflow.step("evidence.adjudication").role, "evidence_adjudication")

    def test_who2_default_setting_is_off(self):
        settings=json.loads((HERE/"settings.json.template").read_text(encoding="utf-8"))
        self.assertIs(settings["diagnosis"]["who5"]["reconsider_after_cmc_expansion"], False)
        self.assertNotIn("max_cmc_passes", settings["diagnosis"]["who5"])


    def test_devel_documents_every_default_workflow_mapping_term(self):
        doc=yaml.safe_load(DEFAULT.read_text(encoding="utf-8"))
        keys=set()
        def collect(value):
            if isinstance(value,dict):
                for key,child in value.items():
                    keys.add(str(key)); collect(child)
            elif isinstance(value,list):
                for child in value: collect(child)
        collect(doc)
        devel=(HERE/"DEVEL.md").read_text(encoding="utf-8")
        missing=sorted(key for key in keys if f"`{key}`" not in devel)
        self.assertEqual(missing,[],f"Undocumented workflow/default.yaml terms: {missing}")

    def test_all_shipped_pipelines_have_separate_adjudication_role(self):
        for path in sorted((HERE/"pipelines").glob("*.yaml")):
            doc=yaml.safe_load(path.read_text(encoding="utf-8"))
            roles=doc.get("model_roles") or doc.get("models")
            with self.subTest(path=path.name):
                self.assertIn("evidence_adjudication", roles)

    def test_provider_completion_check_for_structure_does_not_touch_downstream_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            context=WorkflowContext(work,executor="provider",profile="self",data={})
            # Regression: Phase 3 originally constructed every completion check
            # eagerly, causing the WHO1 routing predicate to read case.json while
            # merely asking whether the initial structure step was complete.
            with patch.object(self_runtime,"assess_who1_routing_change",side_effect=AssertionError("downstream completion check evaluated eagerly")):
                self.assertFalse(staged._provider_step_complete("structure",context))

    def test_step_self_resume_requires_deterministic_structure_tail_but_provider_completion_is_unchanged(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case_text=(HERE/"tests"/"fixtures"/"structure_case"/"valid.json").read_text(encoding="utf-8")
            staged._case_json(work).write_text(case_text,encoding="utf-8")
            root=layout.model_step_dir(work,"structure-case",existing=False)
            (root/"validated.txt").write_text("accepted\n",encoding="utf-8")

            self_ctx=WorkflowContext(work,executor="provider",profile="self",data={})
            staged._hydrate_provider_context(work,self_ctx)
            self.assertNotIn("registry",self_ctx.data)
            self.assertFalse(staged._provider_step_complete("structure",self_ctx))

            provider_ctx=WorkflowContext(work,executor="provider",profile="lmstudio",data={})
            self.assertTrue(staged._provider_step_complete("structure",provider_ctx))

            staged._variants_path(work).write_text("variants: {}\n",encoding="utf-8")
            staged._hydrate_provider_context(work,self_ctx)
            self.assertEqual(self_ctx.get("registry"),{})
            self.assertTrue(staged._provider_step_complete("structure",self_ctx))

    def test_step_self_structure_reentry_finishes_deterministic_tail_without_another_model_call(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case_text=(HERE/"tests"/"fixtures"/"structure_case"/"valid.json").read_text(encoding="utf-8")
            staged._case_json(work).write_text(case_text,encoding="utf-8")
            layout.input(work,"case.md",existing=False).write_text("MDS with SRSF2 mutation",encoding="utf-8")
            layout.setup(work,"case-major-categories.json",existing=False).write_text('["MDS"]\n',encoding="utf-8")
            scope=(staged.REPO_ROOT/"config"/"ngs-panel-scope.md").read_text(encoding="utf-8")
            layout.setup(work,"ngs-panel-scope.md",existing=False).write_text(scope,encoding="utf-8")
            with patch.object(staged.model_client,"complete_messages",side_effect=AssertionError("existing self handoff output must be consumed without another model call")):
                case,registry=staged.stage_structure(work,"self",prompt_text="structure")
            self.assertEqual(case["variants"][0]["gene"],"SRSF2")
            self.assertIn("v01",registry)
            self.assertTrue(staged.has_artifact(work,"variant_registry","variants.yaml"))
            self.assertTrue((layout.model_step_dir(work,"structure-case",existing=True)/"validated.txt").is_file())

    def test_provider_usage_summary_separates_logical_operations_physical_calls_and_repairs(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            staged._record_usage(work,"prognosis","model-a",1,{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15},role="ptbg",duration_ms=100,logical_operation="prognosis")
            staged._record_usage(work,"prognosis","model-a",2,{"prompt_tokens":12,"completion_tokens":6,"total_tokens":18},role="ptbg",duration_ms=120,logical_operation="prognosis")
            staged._record_usage(work,"prognosis-syntax-1","model-b",1,{"prompt_tokens":4,"completion_tokens":2,"total_tokens":6},role="syntax_repair",duration_ms=30,logical_operation="prognosis",call_kind="syntax_repair")
            staged._record_usage(work,"treatment","model-a",1,None,role="ptbg",duration_ms=80,logical_operation="treatment")
            summary=staged._usage_summary(work)
            self.assertEqual(summary["logical_operations"],2)
            self.assertEqual(summary["physical_calls"],4)
            self.assertEqual(summary["retry_calls"],1)
            self.assertEqual(summary["syntax_repair_calls"],1)
            self.assertEqual(summary["duration_ms"],330)
            self.assertEqual(summary["totals"]["total_tokens"],39)
            self.assertEqual(summary["by_operation"]["prognosis"]["physical_calls"],3)
            self.assertEqual(summary["by_operation"]["prognosis"]["retry_calls"],1)
            self.assertEqual(summary["by_operation"]["prognosis"]["syntax_repair_calls"],1)

    def test_proforma_devel_sync_does_not_own_root_config(self):
        from workflows.proforma_v1 import devel_sync
        self.assertEqual(devel_sync.check(),0)
        self.assertEqual(devel_sync.sync(),2)

    def test_diagnosis_evidence_prompts_show_exact_machine_contracts(self):
        audit=(HERE/"prompts"/"evidence"/"diagnosis_audit.md").read_text(encoding="utf-8")
        adjudicate=(HERE/"prompts"/"evidence"/"diagnosis_adjudicate.md").read_text(encoding="utf-8")
        self.assertIn("audits:",audit)
        self.assertIn("card_audits:",audit)
        self.assertIn("card_is_element_of_reason:",audit)
        self.assertIn("adjudications:",adjudicate)
        self.assertIn("decision: include",adjudicate)
        self.assertIn("reason:",adjudicate)

    def test_who1_read_only_path_probes_do_not_create_intermediate_directories(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            before=sorted(p.name for p in (work/"intermediates").iterdir())
            probes=(
                self_runtime._who1_routing_change_path(work),
                self_runtime._who1_gate_state_path(work),
                self_runtime._who1_gate_match_pass_path(work,1),
                self_runtime._who1_gate_match_final_path(work),
                self_runtime._who1_gate_audit_path(work),
                self_runtime._who1_gate_adjudication_path(work),
                self_runtime._who1_commit_path(work),
            )
            self.assertTrue(all(not path.exists() for path in probes))
            after=sorted(p.name for p in (work/"intermediates").iterdir())
            self.assertEqual(after,before)

    def test_aml_subtype_refinement_with_unchanged_aml_route_skips_who1_gate(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case={
                "provisional_disease":"acute myeloid leukaemia (AML)",
                "bootstrap_cmcs":["AML"],
                "morphologic_diagnosis_origin":"supplied",
            }
            who1={
                "schema_disease":"AML",
                "diagnosis":"AML with myelodysplasia-related gene mutation",
                "diagnostic_effect":"refined",
                "variants":["v01"],
                "reason":"refinement within AML",
            }
            with patch.object(self_runtime,"load_case_registry",return_value=(case,{})), \
                 patch.object(self_runtime,"accept_who",return_value=who1), \
                 patch.object(self_runtime.runtime,"derive_cmcs",return_value=["AML"]):
                change=self_runtime.assess_who1_routing_change(work)
            self.assertFalse(change["changed"])
            self.assertEqual(change["previous"]["cmcs"],["AML"])
            self.assertEqual(change["proposed"]["cmcs"],["AML"])

    def test_bootstrap_cmc_contraction_does_not_trigger_who1_gate(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case={
                "provisional_disease":"myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)",
                "bootstrap_cmcs":["MDS","germline predisposition syndrome"],
                "morphologic_diagnosis_origin":"supplied",
            }
            who1={
                "schema_disease":"MDS",
                "diagnosis":"MDS with increased blasts-2",
                "diagnostic_effect":"unchanged",
                "variants":[],
                "reason":"unchanged",
            }
            with patch.object(self_runtime,"load_case_registry",return_value=(case,{})), \
                 patch.object(self_runtime,"accept_who",return_value=who1):
                change=self_runtime.assess_who1_routing_change(work)
            self.assertIsNone(change["previous"]["schema_disease"])
            self.assertEqual(change["previous"]["cmcs"],["MDS","germline predisposition syndrome"])
            self.assertEqual(change["proposed"]["cmcs"],["MDS"])
            self.assertFalse(change["changed"])

    def test_new_cmc_still_triggers_who1_gate_after_multi_bootstrap(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case={
                "provisional_disease":"myelodysplastic neoplasm with increased blasts-2 (MDS-IB2)",
                "bootstrap_cmcs":["MDS","germline predisposition syndrome"],
                "morphologic_diagnosis_origin":"supplied",
            }
            who1={
                "schema_disease":"AML",
                "diagnosis":"AML",
                "diagnostic_effect":"updated",
                "variants":[],
                "reason":"new route",
            }
            with patch.object(self_runtime,"load_case_registry",return_value=(case,{})), \
                 patch.object(self_runtime,"accept_who",return_value=who1):
                change=self_runtime.assess_who1_routing_change(work)
            self.assertEqual(change["proposed"]["cmcs"],["AML"])
            self.assertTrue(change["changed"])



class Phase3OwnerEvidenceTests(unittest.TestCase):
    def test_owner_assignment_schemas_accept_runtime_card_tag_format(self):
        valid_tag="[card:3be59917dd3e]"
        invalid_tag="card:3be59917dd3e"

        def collect_tag_item_schemas(value):
            found=[]
            if isinstance(value,dict):
                for key,child in value.items():
                    if key=="evidence_card_tags" and isinstance(child,dict):
                        items=child.get("items")
                        if isinstance(items,dict):
                            found.append(items)
                    found.extend(collect_tag_item_schemas(child))
            elif isinstance(value,list):
                for child in value:
                    found.extend(collect_tag_item_schemas(child))
            return found

        for name in ("prognosis.json","treatment.json","biomarker.json","domain_classification.json"):
            schema=json.loads((HERE/"schemas"/name).read_text(encoding="utf-8"))
            tag_schemas=collect_tag_item_schemas(schema)
            self.assertTrue(tag_schemas,f"{name} has no evidence_card_tags item schema")
            for item_schema in tag_schemas:
                validator=Draft202012Validator(item_schema)
                with self.subTest(schema=name,pattern=item_schema.get("pattern")):
                    self.assertTrue(validator.is_valid(valid_tag),f"{name} rejected a valid runtime card tag")
                    self.assertFalse(validator.is_valid(invalid_tag),f"{name} accepted a malformed card tag")

    def test_out_of_owner_envelope_card_is_deterministic_owner_validation_issue(self):
        doc={"classification":[{"variant":"v01","evidence_card_tags":["[card:bbbbbbbbbbbb]"]}]}
        issues=rules.owner_evidence_card_tags(doc,{"owner_card_tags":["[card:aaaaaaaaaaaa]"]},{})
        self.assertEqual(len(issues),1)
        self.assertEqual(issues[0].path,"classification[0].evidence_card_tags[0]")
        self.assertIn("not supplied to this owner step",issues[0].problem)
        self.assertIn("empty list",issues[0].required_fix)

    def test_ptbg_consolidation_unions_owner_evidence_tags(self):
        contract=domain_contract.contract("treatment")
        doc={
            "applicable_disease":"AML",
            "drug_target":[],
            "drug_sensitive":[
                {"variants":["v01"],"gene":"ASXL1","therapy":"azacitidine","reason":"Same proposition.","evidence_card_tags":["[card:aaaaaaaaaaaa]"]},
                {"variants":["v02"],"gene":"ASXL1","therapy":"azacitidine","reason":"Same proposition.","evidence_card_tags":["[card:bbbbbbbbbbbb]"]},
            ],
            "drug_resistant":[],"no_drug_implication":[],
        }
        reg={"v01":{"gene":"ASXL1"},"v02":{"gene":"ASXL1"}}
        out,_records=staged._consolidate_rows("treatment",doc,reg,contract)
        self.assertEqual(len(out["drug_sensitive"]),1)
        self.assertEqual(out["drug_sensitive"][0]["variants"],["v01","v02"])
        self.assertEqual(out["drug_sensitive"][0]["evidence_card_tags"],["[card:aaaaaaaaaaaa]","[card:bbbbbbbbbbbb]"])




class Phase3NativeSelfOwnerRepairTests(unittest.TestCase):
    def test_invalid_owner_card_assignment_is_fed_back_to_that_ptbg_step(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            workflow=compile_workflow()
            context=WorkflowContext(work,executor="self",profile="self",data={"workflow":workflow,"settings":{}})
            model_path=self_runtime.output_path(work,"treatment_state","model-classification.yaml")
            model_path.write_text("classification: []\n",encoding="utf-8")
            with patch.object(self_executor,"_self_domain_contracts",return_value=({"treatment":object()},{"treatment":object()})), \
                 patch.object(self_runtime,"accept_ptbg",side_effect=ValueError("classification[0].evidence_card_tags[0]: card '[card:bbbbbbbbbbbb]' was not supplied to this owner step")) as accept:
                self.assertFalse(self_executor._self_step_complete("treatment",context))
            accept.assert_called_once()
            self.assertEqual(accept.call_args.kwargs["domains_to_accept"],("treatment",))
            self.assertIn("not supplied to this owner step",context.get("self_validation_feedback")["treatment"])
            step=workflow.step("treatment")
            with patch.object(self_executor.workflow_bindings,"resolve_inputs",return_value={}):
                prompt_path=self_executor._self_render_prompt(step,context)
            rendered=prompt_path.read_text(encoding="utf-8")
            self.assertIn("Deterministic validation feedback",rendered)
            self.assertIn("not supplied to this owner step",rendered)
            self.assertIn("Return the complete artifact again, not a patch",rendered)

    def test_valid_owner_output_is_accepted_before_evidence_assignment(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            workflow=compile_workflow()
            context=WorkflowContext(work,executor="self",profile="self",data={"workflow":workflow,"settings":{}})
            model_path=self_runtime.output_path(work,"treatment_state","model-classification.yaml")
            model_path.write_text("classification: []\n",encoding="utf-8")
            accepted={"drug_target":[],"drug_sensitive":[],"drug_resistant":[],"no_drug_implication":[],"applicable_disease":"AML"}
            with patch.object(self_executor,"_self_domain_contracts",return_value=({"treatment":object()},{"treatment":object()})), \
                 patch.object(self_runtime,"accept_ptbg",return_value={"treatment":accepted}) as accept:
                self.assertTrue(self_executor._self_step_complete("treatment",context))
            accept.assert_called_once()
            self.assertEqual(context.get("domains")["treatment"],accepted)
            self.assertFalse((context.get("self_validation_feedback") or {}).get("treatment"))

class Phase3EvidenceRescueTests(unittest.TestCase):
    def _state(self):
        return {
            "elements":[{"schema_id":"S1","domain":"treatment","bucket":"drug_sensitive","statement":"fact","reason":"fact","variants":["v01"],"evidence_domain":"treatment","required":False,"source":{}}],
            "items":[{
                "evidence_id":"E0001","schema_id":"S1","reason":"fact","statement":"fact",
                "candidate_card_ids":["A","B"],
                "candidate_card_tags":["[card:aaaaaaaaaaaa]","[card:bbbbbbbbbbbb]"],
                "owner_card_tags":["[card:aaaaaaaaaaaa]"],
            }],
            "no_candidate_schema_ids":[],"catalog_card_ids":["A","B"],"authoritative_disease":"AML","corpus_sha256":"x",
            "rescue_match_passes":1,"rescue_round":1,"owner_assignment_domains":["treatment"],
            "current_assignment_by_evidence_id":{"E0001":["[card:aaaaaaaaaaaa]"]},
            "accepted_card_tags_by_evidence_id":{"E0001":[]},
            "rejected_card_tags_by_evidence_id":{"E0001":[]},
            "assignment_meta_by_evidence_id":{"E0001":{"[card:aaaaaaaaaaaa]":{"origin":"owner","rescue_round":0,"match_pass":0}}},
            "audit_by_evidence_id":{},"unresolved_disputes":[],"processed_audit_sha256":None,"match_pass_by_evidence_id":{},
        }

    def test_audit_rejection_excludes_bad_owner_card_and_requests_rescue_remaining_card(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            state=self._state(); self_runtime.write_yaml(self_runtime._evidence_state_path(work),state)
            self_runtime.write_yaml(self_runtime._evidence_match_final_path(work),{"matches":[{"evidence_id":"E0001","card_tags":["[card:aaaaaaaaaaaa]"]}]})
            self_runtime.write_yaml(self_runtime.output_path(work,"evidence_audits","self-audit.yaml"),{
                "audits":[{"evidence_id":"E0001","card_audits":[{"card_tag":"[card:aaaaaaaaaaaa]","card_is_element_of_reason":False,"risk":"none","comments":["Does not support the fact."]}]}]
            })
            cards=[{"card_id":"A","interpretation":"A text"},{"card_id":"B","interpretation":"B text"}]
            tags={"A":"aaaaaaaaaaaa","B":"bbbbbbbbbbbb"}
            with patch.object(self_runtime,"_assert_audit_targets_applicable",return_value=None), \
                 patch.object(self_runtime,"corpus_state",return_value=(cards,[],"x",{})), \
                 patch.object(self_runtime.card_identity,"tag_by_id",return_value=tags), \
                 patch.object(self_runtime.staged,"_render_cards",side_effect=lambda selected,tagmap:selected[0]["interpretation"]):
                updated=self_runtime.apply_evidence_audit(work)
                self.assertEqual(updated["rejected_card_tags_by_evidence_id"]["E0001"],["[card:aaaaaaaaaaaa]"])
                self.assertEqual(updated["needs_rescue_evidence_ids"],["E0001"])
                self.assertEqual(updated["rescue_round"],2)
                self.assertFalse(self_runtime.evidence_audit_resolved(work))
                # Simulate the workflow review invalidating only the logical assignment/audit outputs.
                self_runtime._evidence_match_final_path(work).unlink()
                self_runtime.output_path(work,"evidence_audits","self-audit.yaml").unlink()
                manifest=self_runtime.prepare_evidence_resolution(work,rescue_match_passes=1)
                self.assertFalse(manifest["complete"])
                text=manifest["facts"].read_text(encoding="utf-8")
                self.assertNotIn("aaaaaaaaaaaa",text)
                self.assertIn("bbbbbbbbbbbb",text)

    def test_provider_reaudit_validates_exact_cropped_manifest_targets(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            workflow=compile_workflow()
            step=workflow.step("evidence.audit")
            ctx=WorkflowContext(work,executor="provider",profile="self",data={"workflow":workflow,"settings":{}})
            output=work/"reaudit.yaml"
            cropped=[{"evidence_id":"E0004","selected_card_tags":["[card:bbbbbbbbbbbb]"]}]
            manifest={"required":True,"output":output,"targets":cropped}
            response={"audits":[{"evidence_id":"E0004","card_audits":[{
                "card_tag":"[card:bbbbbbbbbbbb]","card_is_element_of_reason":True,"risk":"none","comments":[]
            }]}]}

            def fake_model_call(*args,**kwargs):
                text=yaml.safe_dump(response,sort_keys=False)
                kwargs["output"].write_text(text,encoding="utf-8")
                kwargs["validator"](text)
                return text

            handler=staged._provider_handlers(workflow)["evidence_audit"]
            with patch.object(self_runtime,"prepare_evidence_audit",return_value=manifest), \
                 patch.object(self_runtime,"audit_targets",side_effect=AssertionError("audit targets recalculated outside manifest")), \
                 patch.object(self_runtime,"apply_evidence_audit",return_value={}), \
                 patch.object(staged,"_model_call",side_effect=fake_model_call):
                result=handler(step,ctx)
            self.assertEqual(result["artifact"],response)
            self.assertEqual(ctx.get("evidence_audits"),response)

    def test_audit_pass_resolves_fact_without_rescue(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            state=self._state(); self_runtime.write_yaml(self_runtime._evidence_state_path(work),state)
            self_runtime.write_yaml(self_runtime._evidence_match_final_path(work),{"matches":[{"evidence_id":"E0001","card_tags":["[card:aaaaaaaaaaaa]"]}]})
            self_runtime.write_yaml(self_runtime.output_path(work,"evidence_audits","self-audit.yaml"),{
                "audits":[{"evidence_id":"E0001","card_audits":[{"card_tag":"[card:aaaaaaaaaaaa]","card_is_element_of_reason":True,"risk":"none","comments":[]}]}]
            })
            with patch.object(self_runtime,"_assert_audit_targets_applicable",return_value=None):
                updated=self_runtime.apply_evidence_audit(work)
            self.assertEqual(updated["accepted_card_tags_by_evidence_id"]["E0001"],["[card:aaaaaaaaaaaa]"])
            self.assertEqual(updated["needs_rescue_evidence_ids"],[])
            self.assertTrue(self_runtime.evidence_audit_resolved(work))
            self.assertEqual(updated["unresolved_disputes"],[])

    def test_committed_audit_replay_does_not_recalculate_now_empty_targets(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            state=self._state(); self_runtime.write_yaml(self_runtime._evidence_state_path(work),state)
            self_runtime.write_yaml(self_runtime._evidence_match_final_path(work),{"matches":[{"evidence_id":"E0001","card_tags":["[card:aaaaaaaaaaaa]"]}]})
            audit_path=self_runtime.output_path(work,"evidence_audits","self-audit.yaml")
            self_runtime.write_yaml(audit_path,{
                "audits":[{"evidence_id":"E0001","card_audits":[{"card_tag":"[card:aaaaaaaaaaaa]","card_is_element_of_reason":True,"risk":"none","comments":[]}]}]
            })
            with patch.object(self_runtime,"_assert_audit_targets_applicable",return_value=None):
                first=self_runtime.apply_evidence_audit(work)
            digest=first["processed_audit_sha256"]
            with patch.object(self_runtime,"audit_targets",side_effect=AssertionError("committed audit targets must not be recalculated")):
                doc,targets=self_runtime.accept_evidence_audit(work)
                manifest=self_runtime.prepare_evidence_audit(work)
                second=self_runtime.apply_evidence_audit(work)
            self.assertEqual(doc["audits"][0]["evidence_id"],"E0001")
            self.assertEqual(targets,[{"evidence_id":"E0001","selected_card_tags":["[card:aaaaaaaaaaaa]"]}])
            self.assertTrue(manifest["committed"])
            self.assertEqual(second["processed_audit_sha256"],digest)
            self.assertEqual(audit_path.read_text(encoding="utf-8"),yaml.safe_dump(doc,sort_keys=False,allow_unicode=True,width=110))

    def test_final_adjudication_input_is_blind_and_cropped(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            state=self._state()
            state["current_assignment_by_evidence_id"]={"E0001":[]}
            state["rejected_card_tags_by_evidence_id"]={"E0001":["[card:aaaaaaaaaaaa]"]}
            state["unresolved_disputes"]=[{
                "evidence_id":"E0001","schema_id":"S1","reason":"fact","card_tag":"[card:aaaaaaaaaaaa]",
                "resolver_decision":"include","auditor_decision":"exclude","audit_comments":["bad"]
            }]
            self_runtime.write_yaml(self_runtime._evidence_state_path(work),state)
            cards=[{"card_id":"A","interpretation":"A text"}]; tags={"A":"aaaaaaaaaaaa"}
            with patch.object(self_runtime,"corpus_state",return_value=(cards,[],"x",{})), \
                 patch.object(self_runtime.card_identity,"tag_by_id",return_value=tags), \
                 patch.object(self_runtime,"_write_pool",return_value=(Path(td)/"cards.md",["A"])):
                manifest=self_runtime.prepare_evidence_adjudication(work)
            self.assertTrue(manifest["required"])
            crop=self_runtime.read_yaml(manifest["disputes"])["disputes"][0]
            self.assertEqual(set(crop),{"evidence_id","schema_id","reason","card_tag"})
            self.assertNotIn("resolver_decision",crop)
            self.assertNotIn("audit_comments",crop)


class Phase3WhoRoutingTests(unittest.TestCase):
    def _patch_common(self, case, who1, change, agreed):
        return (
            patch.object(self_runtime,"assess_who1_routing_change",return_value=change),
            patch.object(self_runtime,"accept_who",return_value=who1),
            patch.object(self_runtime,"load_case_registry",return_value=(case,{})),
            patch.object(self_runtime,"accept_who1_evidence_resolution",return_value={"matches":[{"evidence_id":"EWHO1","card_tags":list(agreed)}]}),
            patch.object(self_runtime,"accept_who1_evidence_audit",return_value={"audits":[]}),
            patch.object(self_runtime,"who1_evidence_disputes",return_value=(list(agreed),[])),
        )

    def test_supported_routing_change_commits_proposed_who1(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case={"provisional_disease":"MDS","morphologic_diagnosis_origin":"supplied","bootstrap_cmcs":["MDS"]}
            who1={"schema_disease":"AML","diagnosis":"AML, myelodysplasia-related","diagnostic_effect":"updated","variants":["v01"],"reason":"supported"}
            change={"changed":True,"previous":{"schema_disease":"MDS","cmcs":["MDS"]},"proposed":{"schema_disease":"AML","cmcs":["AML"]}}
            patches=self._patch_common(case,who1,change,["[card:aaaaaaaaaaaa]"])
            with patches[0],patches[1],patches[2],patches[3],patches[4],patches[5]:
                doc=self_runtime.commit_who1_routing(work)
            self.assertTrue(doc["accepted"]); self.assertFalse(doc["fallback"])
            self.assertEqual(doc["accepted_who1"]["schema_disease"],"AML")
            self.assertIn("AML",doc["routing_cmcs"])

    def test_no_routing_change_commits_who1_without_evidence_gate_artifacts(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case={"provisional_disease":"AML","morphologic_diagnosis_origin":"supplied","bootstrap_cmcs":["AML"]}
            who1={"schema_disease":"AML","diagnosis":"AML","diagnostic_effect":"unchanged","variants":[],"reason":"unchanged"}
            change={"changed":False,"previous":{"schema_disease":"AML","cmcs":["AML"]},"proposed":{"schema_disease":"AML","cmcs":["AML"]}}
            with patch.object(self_runtime,"assess_who1_routing_change",return_value=change), \
                 patch.object(self_runtime,"accept_who",return_value=who1), \
                 patch.object(self_runtime,"load_case_registry",return_value=(case,{})), \
                 patch.object(self_runtime,"accept_who1_evidence_resolution",side_effect=AssertionError("evidence gate must be skipped")):
                doc=self_runtime.commit_who1_routing(work)
            self.assertTrue(doc["accepted"]); self.assertFalse(doc["fallback"])
            self.assertEqual(doc["accepted_who1"],who1)
            self.assertEqual(doc["routing_cmcs"],["AML"])

    def test_who2_setting_controls_reconsideration_without_disabling_committed_routing(self):
        ctx=WorkflowContext(Path("/tmp/nonexistent-phase3-who2"),executor="provider",data={})
        ctx.put("case",{"bootstrap_cmcs":["MDS"]})
        ctx.put("committed_who1",{"schema_disease":"AML","diagnosis":"AML","diagnostic_effect":"updated","variants":[]})
        off={"diagnosis":{"who5":{"reconsider_after_cmc_expansion":False}}}
        on={"diagnosis":{"who5":{"reconsider_after_cmc_expansion":True}}}
        with patch.object(staged,"load_settings",return_value=off):
            self.assertFalse(staged._who2_required(ctx))
        with patch.object(staged,"load_settings",return_value=on):
            self.assertTrue(staged._who2_required(ctx))

    def test_who2_reconsideration_ignores_bootstrap_contraction_in_both_executors(self):
        work=Path("/tmp/nonexistent-phase3-who2-contraction")
        case={"bootstrap_cmcs":["MDS","germline predisposition syndrome"]}
        who1={"schema_disease":"MDS","diagnosis":"MDS","diagnostic_effect":"unchanged","variants":[]}
        ctx=WorkflowContext(work,executor="provider",data={})
        ctx.put("case",case)
        ctx.put("committed_who1",who1)
        on={"diagnosis":{"who5":{"reconsider_after_cmc_expansion":True}}}
        with patch.object(staged,"load_settings",return_value=on):
            self.assertFalse(staged._who2_required(ctx))
        with patch.object(staged,"load_settings",return_value=on), \
             patch.object(self_runtime,"load_case_registry",return_value=(case,{})):
            self.assertFalse(self_executor._self_who2_required(ctx))

    def test_rejected_routing_change_falls_back_to_supplied_morphology(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case={"provisional_disease":"MDS","morphologic_diagnosis_origin":"supplied","bootstrap_cmcs":["MDS"]}
            who1={"schema_disease":"AML","diagnosis":"AML, myelodysplasia-related","diagnostic_effect":"updated","variants":["v01"],"reason":"unsupported"}
            change={"changed":True,"previous":{"schema_disease":"MDS","cmcs":["MDS"]},"proposed":{"schema_disease":"AML","cmcs":["AML"]}}
            patches=self._patch_common(case,who1,change,[])
            with patches[0],patches[1],patches[2],patches[3],patches[4],patches[5], \
                 patch.object(self_runtime.staged,"_semantic_dissent"),patch.object(self_runtime.staged,"_semantic_dissent_address"):
                doc=self_runtime.commit_who1_routing(work)
            self.assertFalse(doc["accepted"]); self.assertTrue(doc["fallback"])
            self.assertEqual(doc["accepted_who1"]["schema_disease"],"MDS")
            self.assertNotIn("AML",doc["routing_cmcs"])

    def test_rejected_inferred_routing_change_has_no_fabricated_fallback(self):
        with tempfile.TemporaryDirectory() as td:
            work=Path(td); layout.ensure_dirs(work)
            case={"provisional_disease":"MDS","morphologic_diagnosis_origin":"inferred","bootstrap_cmcs":["MDS"]}
            who1={"schema_disease":"AML","diagnosis":"AML","diagnostic_effect":"updated","variants":[],"reason":"unsupported"}
            change={"changed":True,"previous":{},"proposed":{}}
            patches=self._patch_common(case,who1,change,[])
            with patches[0],patches[1],patches[2],patches[3],patches[4],patches[5]:
                with self.assertRaisesRegex(ValueError,"inferred"):
                    self_runtime.commit_who1_routing(work)


if __name__ == "__main__":
    unittest.main()
