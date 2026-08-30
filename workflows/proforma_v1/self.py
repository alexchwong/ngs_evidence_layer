#!/usr/bin/env python3
"""Proforma-v1 native self executor.

The current/session model performs the model reasoning directly. This module is
also the single source of truth for native-self progression: callers may invoke
``advance()`` (or the ``run`` CLI command) to obtain the next bounded handoff.
"""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import write_workflow_state
from workflows.proforma_v1 import layout
from workflows.proforma_v1 import self_runtime as sr
from workflows.proforma_v1 import step as staged
from workflows.proforma_v1.engine.context import WorkflowContext
from workflows.proforma_v1.engine.workflow_compiler import compile_workflow, resolve_workflow_path
from workflows.proforma_v1.engine.workflow_runner import WorkflowRunner, condition_applies, executor_enabled
from workflows.proforma_v1.engine import schema_validation as generic_schema_validation
from workflows.proforma_v1.engine import bindings as workflow_bindings, prompt_renderer as workflow_prompt_renderer, control_state, artifacts as workflow_artifacts
from workflows.proforma_v1.executors.self_executor import SelfExecutor
from workflows.proforma_v1.trace import TraceRecorder

EXIT_OK = 0
EXIT_FAILURE = 1


def configure_runtime(*, settings_path=None, pipelines_dir=None):
    """Bind public or frozen per-run configuration through the staged core."""
    return staged.configure_runtime(settings_path=settings_path, pipelines_dir=pipelines_dir)


def _print_manifest(data):
    def convert(value):
        if isinstance(value, Path):
            return str(value.resolve())
        if isinstance(value, dict):
            return {k: convert(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [convert(v) for v in value]
        return value
    print(json.dumps(convert(data), indent=2, ensure_ascii=False))


def _structure_manifest(work: Path, *, prompt: Path | None = None) -> dict:
    work = Path(work).resolve()
    return {
        "pass": "who1",
        "phase": "structure_case",
        "note": "Complete this structure subtask and WHO1 in one continuous self reasoning pass; do not treat this deterministic interleave as another model pass.",
        "contract": sr.contract_path("structure_case"),
        "prompt": prompt,
        "inputs": {
            "case": layout.input(work, "case.md"),
            "allowed_bootstrap_cmcs": layout.setup(work, "case-major-categories.json"),
        },
        "output": staged.artifact_path(work, "structured_case", "case.json", create=True),
    }


def cmd_setup(args):
    compiled=staged._compile_selected_workflow(args.workflow)
    # Native-self owns the established work-location policy independently of
    # staged execution: default -> system temp; --project -> <repo-root>/temp;
    # explicit --work-dir -> that directory.
    plan = staged.pipeline_registry.load("self")
    work = setup_workflow(
        workflow=staged.WORKFLOW_ID,
        mode=args.mode,
        work_dir=args.work_dir,
        project=bool(args.project),
        example=args.example,
        case_id=args.case_id,
    )
    write_workflow_state(work, staged.WORKFLOW_ID, args.mode, model_profile=plan.pipeline_id)

    case_path = layout.input(work, "case.md", existing=False)
    if args.case_file:
        shutil.copyfile(args.case_file.expanduser().resolve(), case_path)
    if not case_path.is_file() or not staged._read(case_path).strip():
        raise staged.StepFailure(f"case.md missing or empty: {case_path}")

    staged._save_run_state(work, {
        "schema_version": staged.RUN_STATE_SCHEMA_VERSION,
        "workflow_id": staged.WORKFLOW_ID,
        "mode": args.mode,
        "validation_case": args.case_id,
        "example": args.example,
        "pipeline": plan.pipeline_id,
        "workflow_definition": staged._workflow_state(compiled),
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    with staged._cli_logging(work):
        print(work)
        print(f"PIPELINE={plan.pipeline_id}")
    return EXIT_OK


def inspect_run(work: Path) -> dict:
    """Return canonical native-self progress without exposing internals to callers."""
    work = Path(work).resolve()
    try:
        meta = staged.run_metadata(work)
    except Exception:
        meta = {"pipeline": "self", "mode": None}

    if (work / "report-final.md").is_file():
        label, stage, nxt, complete = "Complete", "complete", None, True
    elif (
        staged.has_artifact(work, "report_write", "report-write.yaml")
        or staged.has_artifact(work, "report_blocks", "report-blocks.yaml")
        or staged.has_artifact(work, "evidence_enriched", "reportable-elements.yaml")
    ):
        label, stage, nxt, complete = "At report synthesis", "report_synthesis", "complete report", False
    elif any(
        staged.has_artifact(work, group, name)
        for group, name in (
            ("evidence_matches", "self-resolution.yaml"),
            ("evidence_audits", "self-audit.yaml"),
            ("self_evidence", "state.yaml"),
            ("evidence_adjudication", "adjudication.yaml"),
        )
    ):
        label, stage, nxt, complete = "At evidence review", "evidence_review", "continue evidence review", False
    elif (
        staged.has_artifact(work, "diagnosis_who5_pass_2", "who5.yaml")
        or staged.has_artifact(work, "diagnosis", "diagnosis-final.yaml")
        or any(
            staged.has_artifact(work, f"{domain}_state", "model-classification.yaml")
            for domain in ("prognosis", "treatment", "biomarker", "germline")
        )
    ):
        label, stage, nxt, complete = "At PTBG", "ptbg", "complete PTBG", False
    elif staged.has_artifact(work, "structured_case", "case.json"):
        label, stage, nxt, complete = "At diagnosis", "diagnosis", "complete diagnosis", False
    elif (work / "workflow.json").is_file() and (work / "case.md").is_file():
        label, stage, nxt, complete = "Setup only", "setup", "structure case", False
    else:
        label, stage, nxt, complete = "Unrecognized", "unknown", "inspect run", False
    return {"label": label, "stage": stage, "next": nxt, "complete": complete, **meta}


def _self_model_output_path(step_id: str, work: Path) -> Path | None:
    mapping={
        'structure': staged.artifact_path(work,'structured_case','case.json',create=True),
        'diagnosis.who1': sr.output_path(work,'diagnosis_who5_pass_1','who5.yaml'),
        'diagnosis.who1.evidence.assignment': sr._who1_gate_match_final_path(work),
        'diagnosis.who1.evidence.audit': sr._who1_gate_audit_path(work),
        'diagnosis.who1.evidence.adjudication': sr._who1_gate_adjudication_path(work),
        'diagnosis.who2': sr.output_path(work,'diagnosis_who5_pass_2','who5.yaml'),
        'diagnosis.icc': sr.output_path(work,'diagnosis_icc','icc.yaml'),
        'prognosis': sr.output_path(work,'prognosis_state','model-classification.yaml'),
        'treatment': sr.output_path(work,'treatment_state','model-classification.yaml'),
        'biomarker': sr.output_path(work,'biomarker_state','model-classification.yaml'),
        'germline': sr.output_path(work,'germline_state','model-classification.yaml'),
        'evidence.assignment': sr.output_path(work,'evidence_matches','self-resolution.yaml'),
        'evidence.audit': sr.output_path(work,'evidence_audits','self-audit.yaml'),
        'evidence.adjudication': sr.output_path(work,'evidence_adjudication','adjudication.yaml'),
        'report.write': sr.output_path(work,'report_write','report-write.yaml'),
        'report.preservation': sr.output_path(work,'report_write','report-preservation.yaml'),
    }
    if step_id in mapping:
        return mapping[step_id]
    return None


def _self_declared_validate(step_id: str, context: WorkflowContext) -> None:
    workflow=context.get('workflow')
    if workflow is None: return
    try: step=workflow.step(step_id)
    except KeyError: return
    if step.type not in {'model','evidence_review','evidence_adjudication','render/report'}: return
    path=_self_model_output_path(step_id,context.work)
    if path is None:
        path=workflow_artifacts.generic_output_path(context.work,step,create=False)
    if not path.is_file(): return
    schema_rel=(step.output or {}).get('schema')
    schema=generic_schema_validation.load_schema((workflow.asset_root/schema_rel).resolve()) if schema_rel else None
    generic_schema_validation.validate(path.read_text(encoding='utf-8'),fmt=(step.output or {}).get('format','yaml'),schema=schema,check_specs=step.checks,context=context.data)


def _self_step_complete(step_id: str, context: WorkflowContext) -> bool:
    work=context.work
    if step_id in {'prognosis','treatment','biomarker','germline'}:
        model_path=sr.output_path(work,f'{step_id}_state','model-classification.yaml')
        proforma_path=sr.output_path(work,f'{step_id}_state','proforma.yaml')
        if proforma_path.is_file():
            domains=dict(context.get('domains',{}) or {})
            domains[step_id]=sr.read_yaml(proforma_path)
            context.put('domains',domains)
            return True
        if not model_path.is_file():
            return False
        workflow=context.get('workflow')
        contracts,specs=_self_domain_contracts(workflow)
        try:
            accepted=sr.accept_ptbg(
                work,domains_to_accept=(step_id,),contracts=contracts,specs=specs
            )[step_id]
        except Exception as exc:
            feedback=dict(context.get('self_validation_feedback',{}) or {})
            feedback[step_id]=str(exc)
            context.put('self_validation_feedback',feedback)
            return False
        feedback=dict(context.get('self_validation_feedback',{}) or {})
        feedback.pop(step_id,None)
        context.put('self_validation_feedback',feedback)
        domains=dict(context.get('domains',{}) or {})
        domains[step_id]=accepted
        context.put('domains',domains)
        return True
    checks={
        'structure': staged.has_artifact(work,'structured_case','case.json'),
        'corpus': staged.has_artifact(work,'card_identity','card-identity-manifest.json'),
        'diagnosis.who1': staged.has_artifact(work,'diagnosis_who5_pass_1','who5.yaml'),
        'diagnosis.who1.routing_change': sr._who1_routing_change_path(work).is_file(),
        'diagnosis.who1.evidence.assignment': sr._who1_gate_match_final_path(work).is_file(),
        'diagnosis.who1.evidence.audit': sr._who1_gate_audit_path(work).is_file(),
        'diagnosis.who1.evidence.adjudication': sr._who1_gate_adjudication_path(work).is_file(),
        'diagnosis.who1.commit': sr._who1_commit_path(work).is_file(),
        'diagnosis.icc': staged.has_artifact(work,'diagnosis_icc','icc.yaml'),
        'diagnosis.who2': staged.has_artifact(work,'diagnosis_who5_pass_2','who5.yaml'),
        'diagnosis.finalize': staged.has_artifact(work,'diagnosis','diagnosis-final.yaml'),
        'prognosis': staged.has_artifact(work,'prognosis_state','model-classification.yaml'),
        'treatment': staged.has_artifact(work,'treatment_state','model-classification.yaml'),
        'biomarker': staged.has_artifact(work,'biomarker_state','model-classification.yaml'),
        'germline': staged.has_artifact(work,'germline_state','model-classification.yaml'),
        'evidence.assignment': staged.has_artifact(work,'evidence_matches','self-resolution.yaml'),
        'evidence.audit': (
            staged.has_artifact(work,'evidence_audits','self-audit.yaml')
            and (lambda state,path: bool(state.get('processed_audit_sha256')) and state.get('processed_audit_sha256')==sr._audit_sha256(path))(
                sr._load_evidence_state(work), sr.output_path(work,'evidence_audits','self-audit.yaml')
            )
        ) if sr._evidence_state_path(work).is_file() and staged.has_artifact(work,'evidence_audits','self-audit.yaml') else False,
        'evidence.adjudication': staged.has_artifact(work,'evidence_enriched','reportable-elements.yaml') or staged.has_artifact(work,'evidence_adjudication','adjudication.yaml'),
        'evidence.finalize': staged.has_artifact(work,'evidence_enriched','reportable-elements.yaml'),
        'report.blocks': staged.has_artifact(work,'report_blocks','report-blocks.yaml'),
        'report.write': staged.has_artifact(work,'report_write','report-write.yaml'),
        'report.preservation': staged.has_artifact(work,'report_write','report-preservation.yaml'),
        'report.finalize': (work/'report-final.md').is_file(),
    }
    if step_id in checks:
        done = bool(checks[step_id])
        if done and step_id == 'report.blocks':
            path = sr.output_path(work, 'report_blocks', 'report-blocks.yaml')
            doc = sr.read_yaml(path)
            blocks = doc.get('blocks') if isinstance(doc, dict) else None
            sr.schema_validation.validate_report_source_blocks(blocks)
            context.put('blocks', blocks)
        return done
    workflow=context.get('workflow')
    if workflow is not None:
        try: step=workflow.step(step_id)
        except KeyError: return False
        if step.type in {'model','evidence_review','evidence_adjudication','render/report'}:
            path=workflow_artifacts.generic_output_path(work,step,create=False)
            if path.is_file():
                _self_declared_validate(step_id,context)
                artifact_name=(step.output or {}).get('artifact')
                if artifact_name:
                    raw=path.read_text(encoding='utf-8'); fmt=(step.output or {}).get('format','yaml')
                    context.put(artifact_name,json.loads(raw) if fmt=='json' else staged.yaml.safe_load(raw))
                return True
    return False


def _handoff(stage: str, manifest: dict) -> dict:
    return {'status': 'handoff', 'handoff': {'stage': stage, 'manifest': manifest}}


def _self_who2_required(ctx):
    cfg=((staged.load_settings().get('diagnosis') or {}).get('who5') or {})
    if not bool(cfg.get('reconsider_after_cmc_expansion', False)):
        return False
    case,_reg=sr.load_case_registry(ctx.work)
    who1=ctx.get('committed_who1') or sr.committed_who1(ctx.work, required=False)
    if not who1:
        return False
    return sr.runtime.has_cmc_expansion(list(case.get('bootstrap_cmcs') or []), sr.runtime.derive_cmcs(who1))


def _self_render_prompt(step, ctx, manifest: dict | None = None) -> Path | None:
    if not step.prompt:
        return None
    inputs=workflow_bindings.resolve_inputs(step,ctx)
    output_template=""
    if manifest:
        candidate=manifest.get("output_contract")
        if isinstance(candidate,Path) and candidate.is_file():
            output_template=candidate.read_text(encoding="utf-8")
    text=workflow_prompt_renderer.render(step.prompt,root=ctx.get('workflow').asset_root,inputs=inputs,output_template=output_template)
    feedback=(ctx.get('self_validation_feedback',{}) or {}).get(step.id)
    if feedback:
        text += (
            "\n\n# Deterministic validation feedback\n"
            "The previous complete artifact failed deterministic validation. Return the complete artifact again, not a patch. "
            "Fix every issue below and preserve unrelated clinical decisions and supplied IDs exactly.\n\n"
            + str(feedback).rstrip() + "\n"
        )
    group=layout.intermediate_dir(ctx.work,f"workflow_prompt_{step.id}",existing=False)
    path=group/'rendered-prompt.md'
    path.write_text(text,encoding='utf-8')
    return path


def _self_domain_contracts(workflow):
    from workflows.proforma_v1 import domain_contract
    contracts={}; specs={}
    for domain in ('prognosis','treatment','biomarker','germline'):
        step=workflow.step(domain); specs[domain]=step.stage_spec_obj
        contracts[domain]=domain_contract.from_spec(step.stage_spec_obj) if step.stage_spec_obj and step.stage_spec_obj.type=='domain_proforma' else domain_contract.contract(domain)
    return contracts,specs


def _self_handlers():
    def decorate(manifest,step,ctx):
        manifest=dict(manifest)
        manifest['prompt']=_self_render_prompt(step,ctx,manifest)
        schema_rel=(step.output or {}).get('schema')
        if schema_rel: manifest['schema']=(ctx.get('workflow').asset_root/schema_rel).resolve()
        return manifest

    def structure(step, ctx):
        return _handoff('case_structure',decorate(_structure_manifest(ctx.work,prompt=step.prompt),step,ctx))

    def corpus(step, ctx):
        sr.accept_structured_case(ctx.work); _self_declared_validate('structure',ctx); staged.stage_corpus(ctx.work)
        return {'status':'complete'}

    def who1(step, ctx):
        return _handoff('diagnosis',decorate(sr.prepare_who(ctx.work,pass_number=1,prompt=step.prompt),step,ctx))

    def who1_routing_change(step, ctx):
        change=sr.assess_who1_routing_change(ctx.work); ctx.put('who1_routing_change',change); return {'status':'complete','artifact':change}

    def who1_evidence_assignment(step, ctx):
        max_passes=int((step.evidence or {}).get('match_passes',2))
        manifest=sr.prepare_who1_evidence_resolution(ctx.work,max_match_passes=max_passes,prompt=step.prompt)
        if manifest.get('complete'):
            doc=sr.accept_who1_evidence_resolution(ctx.work) if manifest.get('required') else {'matches':[]}
            ctx.put('who1_evidence_assignments',doc); return {'status':'complete','artifact':doc}
        return _handoff('diagnosis_who1_evidence_match',decorate(manifest,step,ctx))

    def who1_evidence_audit(step, ctx):
        manifest=sr.prepare_who1_evidence_audit(ctx.work,prompt=step.prompt)
        if not manifest.get('required'):
            doc={'audits':[]}; ctx.put('who1_evidence_audits',doc); return {'status':'skipped','reason':'no_matched_cards','artifact':doc}
        return _handoff('diagnosis_who1_evidence_audit',decorate(manifest,step,ctx))

    def who1_evidence_adjudication(step, ctx):
        manifest=sr.prepare_who1_evidence_adjudication(ctx.work,prompt=step.prompt)
        if not manifest.get('required'):
            return {'status':'skipped','reason':'no_disagreement','artifact':{'adjudications':[]}}
        return _handoff('diagnosis_who1_evidence_adjudication',decorate(manifest,step,ctx))

    def who1_commit(step, ctx):
        commit=sr.commit_who1_routing(ctx.work); ctx.put('who1_commit',commit); ctx.put('committed_who1',commit['accepted_who1']); return {'status':'complete','artifact':commit}

    def who2(step, ctx):
        return _handoff('diagnosis',decorate(sr.prepare_who(ctx.work,pass_number=2,prompt=step.prompt),step,ctx))

    def icc(step, ctx):
        manifest=sr.prepare_icc(ctx.work,prompt=step.prompt)
        _self_declared_validate('diagnosis.who1',ctx)
        if staged.has_artifact(ctx.work,'diagnosis_who5_pass_2','who5.yaml'):
            _self_declared_validate('diagnosis.who2',ctx)
        return _handoff('diagnosis',decorate(manifest,step,ctx))

    def diagnosis_finalize(step, ctx):
        sr.finalize_diagnosis(ctx.work); _self_declared_validate('diagnosis.icc',ctx); return {'status':'complete'}

    def ptbg(step, ctx):
        sr.finalize_diagnosis(ctx.work)
        members=ctx.get('self_group_step_objects') or (step,)
        domains=tuple(member.id for member in members)
        prompts={member.id:member.prompt for member in members}
        contracts,_specs=_self_domain_contracts(ctx.get('workflow'))
        manifest=sr.prepare_ptbg(ctx.work,domains=domains,prompts=prompts,contracts=contracts)
        for member in members:
            sub=manifest['domains'][member.id]
            sub['prompt']=_self_render_prompt(member,ctx,sub)
            schema_rel=(member.output or {}).get('schema')
            if schema_rel: sub['schema']=(ctx.get('workflow').asset_root/schema_rel).resolve()
        return _handoff('ptbg',manifest)

    def evidence_assignment(step, ctx):
        contracts,specs=_self_domain_contracts(ctx.get('workflow'))
        sr.accept_ptbg(ctx.work,contracts=contracts,specs=specs)
        for domain in ('prognosis','treatment','biomarker','germline'):
            _self_declared_validate(domain,ctx)
        rescue_passes=int((step.evidence or {}).get('rescue_match_passes',(step.evidence or {}).get('match_passes',1)))
        workflow=ctx.get('workflow')
        owner_domains={d for d in ('prognosis','treatment','biomarker','germline') if bool((workflow.step(d).evidence or {}).get('owner_assignment',False))}
        manifest=sr.prepare_evidence_resolution(
            ctx.work,prompt=step.prompt,contracts=contracts,specs=specs,rescue_match_passes=rescue_passes,owner_assignment_domains=owner_domains
        )
        if manifest.get('complete'):
            doc=sr.accept_evidence_resolution(ctx.work)
            ctx.put('evidence_assignments',doc)
            return {'status':'complete','artifact':doc}
        public_manifest={k:v for k,v in manifest.items() if k!='validation_items'}
        return _handoff('evidence_resolution',decorate(public_manifest,step,ctx))

    def evidence_audit(step, ctx):
        manifest=sr.prepare_evidence_audit(ctx.work,prompt=step.prompt)
        _self_declared_validate('evidence.assignment',ctx)
        if not manifest.get('required'):
            sr.apply_evidence_audit(ctx.work)
            doc={'audits':[]}; ctx.put('evidence_audits',doc)
            return {'status':'skipped','reason':'no_matched_cards','artifact':doc}
        if Path(manifest['output']).is_file():
            doc,_targets=sr.accept_evidence_audit(ctx.work); sr.apply_evidence_audit(ctx.work); ctx.put('evidence_audits',doc)
            return {'status':'complete','artifact':doc}
        return _handoff('evidence_audit',decorate(manifest,step,ctx))

    def evidence_adjudication(step, ctx):
        manifest=decorate(sr.prepare_evidence_adjudication(ctx.work,prompt=step.prompt),step,ctx)
        _self_declared_validate('evidence.audit',ctx)
        if not manifest.get('required'):
            return {'status':'complete','reason':'no_disagreement'}
        return _handoff('evidence_adjudication',manifest)

    def evidence_finalize(step, ctx):
        sr.finalize_evidence(ctx.work)
        if staged.has_artifact(ctx.work,'evidence_adjudication','adjudication.yaml'):
            _self_declared_validate('evidence.adjudication',ctx)
        return {'status':'complete'}

    def report_blocks(step, ctx):
        elements_path = sr.output_path(ctx.work, 'evidence_enriched', 'reportable-elements.yaml')
        if not elements_path.is_file():
            sr.finalize_evidence(ctx.work)
        elements_doc = sr.read_yaml(elements_path)
        elements = elements_doc.get('elements') if isinstance(elements_doc, dict) else None
        if not isinstance(elements, list):
            raise ValueError(f"report.blocks requires evidence-enriched elements: {elements_path}")
        diagnosis = sr.finalize_diagnosis(ctx.work)
        _case, reg = sr.load_case_registry(ctx.work)
        blocks = staged.stage_blocks(ctx.work, diagnosis, elements, reg)
        sr.schema_validation.validate_report_source_blocks(blocks)
        ctx.put('blocks', blocks)
        return {'status':'complete','artifact':blocks}

    def report_write(step, ctx):
        return _handoff('report_synthesis',decorate(sr.prepare_report(ctx.work,prompt=step.prompt),step,ctx))

    def report_preservation(step, ctx):
        return _handoff('report_preservation',decorate(sr.prepare_report_preservation(ctx.work,prompt=step.prompt),step,ctx))

    def report_finalize(step, ctx):
        _self_declared_validate('report.write',ctx)
        if staged.has_artifact(ctx.work,'report_write','report-preservation.yaml'):
            _self_declared_validate('report.preservation',ctx)
        sr.finalize_report(ctx.work); sr.package_debug_bundle(ctx.work)
        return {'status':'complete'}

    def generic_model(step,ctx):
        manifest={
            'pass':step.id,
            'prompt':_self_render_prompt(step,ctx),
            'output':workflow_artifacts.generic_output_path(ctx.work,step,create=True),
        }
        schema_rel=(step.output or {}).get('schema')
        if schema_rel: manifest['schema']=(ctx.get('workflow').asset_root/schema_rel).resolve()
        return _handoff(step.id,manifest)

    return {
        'structure':structure,'corpus':corpus,
        'diagnosis_who1':who1,'who1_routing_change':who1_routing_change,
        'who1_evidence_assignment':who1_evidence_assignment,'who1_evidence_audit':who1_evidence_audit,
        'who1_evidence_adjudication':who1_evidence_adjudication,'who1_commit':who1_commit,
        'diagnosis_who2':who2,'diagnosis_icc':icc,
        'diagnosis_finalize':diagnosis_finalize,
        'ptbg':ptbg,'evidence_assignment':evidence_assignment,'evidence_audit':evidence_audit,
        'evidence_adjudication':evidence_adjudication,'evidence_finalize':evidence_finalize,
        'report_blocks':report_blocks,'report_write':report_write,
        'report_preservation':report_preservation,'report_finalize':report_finalize,
        'generic_model':generic_model,
    }

def _self_invalidate(step_ids: set[str], context: WorkflowContext) -> None:
    """Delete persisted outputs invalidated by a bounded semantic review retry."""
    workflow=context.get('workflow')
    for step_id in step_ids:
        path=_self_model_output_path(step_id,context.work)
        if path is None and workflow is not None:
            try: path=workflow_artifacts.generic_output_path(context.work,workflow.step(step_id),create=False)
            except KeyError: path=None
        if path is not None:
            Path(path).unlink(missing_ok=True)
        if step_id in {'prognosis','treatment','biomarker','germline'}:
            sr.output_path(context.work,f'{step_id}_state','proforma.yaml').unlink(missing_ok=True)
        if step_id=='evidence.finalize':
            sr.output_path(context.work,'evidence_enriched','reportable-elements.yaml').unlink(missing_ok=True)
        if step_id=='report.finalize':
            for name in ('report-final.md','report-final.json'):
                (context.work/name).unlink(missing_ok=True)


def _write_self_trace(work: Path, workflow, context: WorkflowContext, current=None) -> None:
    trace=TraceRecorder(workflow.workflow_id)
    for step in workflow.steps:
        if not executor_enabled(step,'self'):
            trace.record(step.id,step.type,'skipped',dependencies=list(step.needs),executor='self',reason='executor_disabled')
        elif step.id in context.completed or _self_step_complete(step.id,context):
            trace.record(step.id,step.type,'complete',dependencies=list(step.needs),executor='self')
        elif all((need in context.completed or _self_step_complete(need,context) or not executor_enabled(workflow.step(need),'self')) for need in step.needs) and not condition_applies(step.when,context):
            trace.record(step.id,step.type,'skipped',dependencies=list(step.needs),executor='self',reason='condition_false')
        elif current==step.id:
            trace.record(step.id,step.type,'handoff',dependencies=list(step.needs),executor='self')
        else:
            trace.record(step.id,step.type,'pending',dependencies=list(step.needs),executor='self')
    trace.write(layout.logs(work)/'workflow-trace.json')


def advance(work: Path, *, workflow_path=None) -> dict:
    """Advance native self by one bounded handoff using the selected workflow."""
    work=Path(work).resolve(); staged._require_work(work); layout.ensure_dirs(work)
    workflow=staged._workflow_for_run(work,workflow_path)
    context=WorkflowContext(work,executor='self',profile='self',data={'settings':staged.load_settings(),'workflow':workflow})
    control_state.hydrate(context)
    for candidate in workflow.steps:
        if candidate.type not in {'model','evidence_review','evidence_adjudication','render/report'}:
            continue
        if _self_model_output_path(candidate.id,work) is not None:
            continue
        path=workflow_artifacts.generic_output_path(work,candidate,create=False)
        if path.is_file() and (candidate.output or {}).get('artifact'):
            raw=path.read_text(encoding='utf-8'); fmt=(candidate.output or {}).get('format','yaml')
            context.put(candidate.output['artifact'],json.loads(raw) if fmt=='json' else staged.yaml.safe_load(raw))
    context.put('predicates',{'who2_required':_self_who2_required,'who1_routing_changed':lambda c: bool(sr.assess_who1_routing_change(c.work).get('changed'))})
    context.put('review_predicates',{'evidence_audit_resolved':lambda step,c,result: sr.evidence_audit_resolved(c.work)})
    runner=WorkflowRunner(workflow,SelfExecutor(_self_handlers(),completion=_self_step_complete,invalidator=_self_invalidate))
    result=runner.advance(context)
    control_state.save(context)
    _write_self_trace(work,workflow,context,result.step_id)
    if result.status=='handoff':
        payload=result.handoff or {}
        return {'status':'handoff','stage':payload.get('stage') or result.step_id,'manifest':payload.get('manifest')}
    if result.status=='complete':
        if not (work/sr.DEBUG_ZIP_NAME).is_file() and (work/'report-final.md').is_file(): sr.package_debug_bundle(work)
        return {'status':'complete','stage':'complete','artifacts':sr.final_artifacts(work)}
    return {'status':'pending','stage':result.step_id or 'workflow'}


def cmd_run(args):
    result = advance(Path(args.work_dir).resolve(),workflow_path=args.workflow)
    print(f"STATUS={result['status']}")
    print(f"STAGE={result['stage']}")
    if result["status"] == "handoff":
        _print_manifest(result["manifest"])
    else:
        for key, value in result["artifacts"].items():
            print(f"{key}={value if value is not None else 'none'}")
    return EXIT_OK


def cmd_structure(args):
    work = Path(args.work_dir).resolve()
    staged._require_work(work)
    layout.ensure_dirs(work)
    _print_manifest(_structure_manifest(work))
    return EXIT_OK


def cmd_who1(args):
    _print_manifest(sr.prepare_who(Path(args.work_dir).resolve(), pass_number=1))
    return EXIT_OK


def cmd_icc(args):
    sr.accept_who(Path(args.work_dir).resolve(), pass_number=1)
    _print_manifest(sr.prepare_icc(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_who2(args):
    sr.accept_icc(Path(args.work_dir).resolve())
    _print_manifest(sr.prepare_who(Path(args.work_dir).resolve(), pass_number=2))
    return EXIT_OK


def cmd_ptbg(args):
    sr.accept_who(Path(args.work_dir).resolve(), pass_number=2)
    _print_manifest(sr.prepare_ptbg(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_evidence_resolution(args):
    work=Path(args.work_dir).resolve()
    sr.accept_ptbg(work)
    workflow=staged._workflow_for_run(work,args.workflow)
    step=workflow.step('evidence.assignment')
    rescue_passes=int((step.evidence or {}).get('rescue_match_passes',(step.evidence or {}).get('match_passes',1)))
    workflow=staged._workflow_for_run(work,args.workflow)
    owner_domains={d for d in ('prognosis','treatment','biomarker','germline') if bool((workflow.step(d).evidence or {}).get('owner_assignment',False))}
    manifest=sr.prepare_evidence_resolution(work,prompt=step.prompt,rescue_match_passes=rescue_passes,owner_assignment_domains=owner_domains)
    _print_manifest({k:v for k,v in manifest.items() if k!='validation_items'})
    return EXIT_OK


def cmd_evidence_audit(args):
    _print_manifest(sr.prepare_evidence_audit(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_evidence_adjudication(args):
    _print_manifest(sr.prepare_evidence_adjudication(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_finalize_evidence(args):
    work = Path(args.work_dir).resolve()
    elements = sr.finalize_evidence(work)
    print(f"SUPPORTED_ELEMENTS={len(elements)}")
    dissent = work / "dissent.md"
    print(f"DISSENT={dissent}" if dissent.is_file() else "DISSENT=none")
    return EXIT_OK


def cmd_report(args):
    _print_manifest(sr.prepare_report(Path(args.work_dir).resolve()))
    return EXIT_OK


def cmd_finalize_report(args):
    work = Path(args.work_dir).resolve()
    sr.finalize_report(work)
    sr.package_debug_bundle(work)
    for key, value in sr.final_artifacts(work).items():
        print(f"{key}={value if value is not None else 'none'}")
    return EXIT_OK


def build_parser():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)
    s = sub.add_parser("setup")
    s.add_argument("--mode", required=True, choices=staged.supported_modes())
    s.add_argument("--case-file", type=Path)
    s.add_argument("--example", type=int)
    s.add_argument("--case-id")
    s.add_argument("--workflow", type=Path)
    sw = s.add_mutually_exclusive_group()
    sw.add_argument("--work-dir", type=Path)
    sw.add_argument("--project", action="store_true")
    for name in ("run", "structure", "who1", "icc", "who2", "ptbg", "evidence-resolution", "evidence-audit", "evidence-adjudication", "finalize-evidence", "report", "finalize-report"):
        q = sub.add_parser(name)
        q.add_argument("--work-dir", type=Path, required=True)
        q.add_argument("--workflow", type=Path)
    wc=sub.add_parser("workflow-check"); wc.add_argument("--workflow",type=Path)
    return p


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        if args.command=="workflow-check":
            [print(x) for x in staged.describe_workflow(staged._compile_selected_workflow(args.workflow))]
            return EXIT_OK
        fn = globals()["cmd_" + args.command.replace("-", "_")]
        return fn(args)
    except Exception as exc:
        print(f"proforma-v1 self failed: {exc}", file=sys.stderr)
        return EXIT_FAILURE


if __name__ == "__main__":
    raise SystemExit(main())
