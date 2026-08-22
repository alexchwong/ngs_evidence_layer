"""Generic declarative scheduler engine for terraced-v3 phase schedulers."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import yaml

from workflows.terraced_v3 import layout, runtime, contract_registry
from workflows.terraced_v3 import scheduler_primitives as prim

_SLOT_RE = re.compile(r"\{\{([A-Za-z0-9_.-]+)\}\}")
PHASES = {"diagnosis", "ptbg", "summarization"}
MODEL_VALIDATORS = {
    "domain", "normalized_evidence", "variant_cross_domain", "germline_clinical_picture",
    "global_ledger", "global_patch", "adaptive_cell_review",
    "icc", "who5", "summary_text", "sentence_alignment", "summary_pairs",
}


@dataclass
class SchedulerPlan:
    scheduler_id: str
    phase: str
    description: str
    path: Path
    doc: dict


def load_yaml(path: Path, expected_phase: str | None = None) -> SchedulerPlan:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise ValueError(f"scheduler YAML must be a mapping: {path}")
    meta = doc.get("scheduler")
    if not isinstance(meta, dict):
        raise ValueError("scheduler.yaml requires scheduler mapping")
    sid = meta.get("id"); version = meta.get("version"); phase = meta.get("phase")
    if not isinstance(sid, str) or not sid:
        raise ValueError("scheduler.id must be non-empty")
    if version != 1:
        raise ValueError(f"unsupported scheduler schema version {version!r}")
    if phase not in PHASES:
        raise ValueError(f"scheduler.phase must be one of {sorted(PHASES)}")
    if expected_phase and phase != expected_phase:
        raise ValueError(f"scheduler {sid!r} declares phase {phase!r}, expected {expected_phase!r}")
    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps:
        raise ValueError("scheduler.steps must be a non-empty list")
    ids=[]
    for i, step in enumerate(steps):
        if not isinstance(step, dict):
            raise ValueError(f"steps[{i}] must be a mapping")
        if not isinstance(step.get("id"), str):
            raise ValueError(f"steps[{i}].id missing")
        if step["id"] in ids:
            raise ValueError(f"duplicate scheduler step id {step['id']!r}")
        previous=set(ids); kind=step.get("kind")
        if kind not in {"model", "operation", "diagnosis_loop", "summarization_loop"}:
            raise ValueError(f"step {step['id']!r} has unsupported kind {kind!r}")
        if kind == "diagnosis_loop" and phase != "diagnosis":
            raise ValueError("diagnosis_loop is only valid in diagnosis schedulers")
        if kind == "summarization_loop" and phase != "summarization":
            raise ValueError("summarization_loop is only valid in summarization schedulers")
        for dep in step.get("depends_on") or []:
            if dep not in previous:
                raise ValueError(f"step {step['id']!r} depends on unknown or later step {dep!r}")
        foreach=step.get("foreach")
        if isinstance(foreach,str) and foreach.startswith("steps."):
            ref=foreach[len("steps."):].split(".")[0]
            if ref not in previous:
                raise ValueError(f"step {step['id']!r} foreach references unknown or later step {ref!r}")
        for name, rule in (step.get("inputs") or {}).items():
            source=rule if isinstance(rule,str) else rule.get("source") if isinstance(rule,dict) else None
            if isinstance(source,str) and source.startswith("steps."):
                rest=source[len("steps."):].split("[$item]",1)[0]
                ref=rest.split(".")[0]
                if ref not in previous:
                    raise ValueError(f"step {step['id']!r} input {name!r} references unknown or later step {ref!r}")
        if kind == "operation" and step.get("operation") not in prim.OPERATIONS:
            raise ValueError(f"step {step['id']!r} uses unknown operation {step.get('operation')!r}")
        if kind == "model":
            output=step.get("output") or {}; fmt=output.get("format")
            if fmt not in {"yaml","text"}:
                raise ValueError(f"scheduler model step {step['id']!r} output.format must be yaml or text")
            if output.get("validator") not in MODEL_VALIDATORS:
                raise ValueError(f"step {step['id']!r} uses unknown validator {output.get('validator')!r}")
        ids.append(step["id"])
    _validate_prompt_assets(path.parent,doc)
    interface=doc.get("interface")
    if not isinstance(interface,dict):
        raise ValueError("scheduler.yaml requires interface mapping with inputs and outputs")
    for side in ("inputs","outputs"):
        rows=interface.get(side)
        if not isinstance(rows,dict):
            raise ValueError(f"scheduler.interface.{side} must be a mapping")
        for name,rule in rows.items():
            if not isinstance(rule,dict) or not isinstance(rule.get("contract"),str):
                raise ValueError(f"scheduler.interface.{side}.{name} must declare contract")
            contract_registry.load(rule["contract"],base=path.parent)
    outputs=doc.get("outputs")
    if not isinstance(outputs,dict) or not outputs:
        raise ValueError("scheduler.outputs must be a non-empty mapping")
    if set(outputs) != set(interface["outputs"]):
        raise ValueError("scheduler.outputs keys must exactly match scheduler.interface.outputs keys")
    for key,ref in outputs.items():
        if not isinstance(ref,str) or not ref.startswith("steps."):
            raise ValueError(f"scheduler output {key!r} must reference steps.<id>...")
        target=ref[len("steps."):].split(".")[0]
        if target not in ids:
            raise ValueError(f"scheduler output {key!r} references unknown step {target!r}")
    _validate_step_contracts(path.parent,doc)
    _validate_core_source_assets(doc)
    return SchedulerPlan(sid,phase,str(meta.get("description") or ""),path,doc)


def _validate_core_source_assets(doc: dict) -> None:
    """Require every scheduler-facing core.* source to have an inspectable contract asset."""
    for step in doc.get("steps") or []:
        for name, rule in (step.get("inputs") or {}).items():
            source = rule if isinstance(rule, str) else rule.get("source") if isinstance(rule, dict) else None
            if isinstance(source, str) and source.startswith("core."):
                try:
                    contract_registry.load(source)
                except ValueError as exc:
                    raise ValueError(f"step {step['id']!r} input {name!r} uses undocumented core source {source!r}: {exc}") from exc
        loop = step.get("loop") or {}
        max_passes = loop.get("max_passes")
        if isinstance(max_passes, str) and max_passes.startswith("core."):
            contract_registry.load(max_passes)


def _validate_step_contracts(base: Path, doc: dict) -> None:
    for step in doc.get("steps") or []:
        output=step.get("output") or {}
        ref=output.get("contract")
        if ref:
            contract_registry.load(ref,base=base)
        selected=output.get("contract_select")
        if selected is not None:
            if not isinstance(selected,dict) or not selected:
                raise ValueError(f"step {step['id']!r} output.contract_select must be a non-empty mapping")
            for cref in selected.values(): contract_registry.load(cref,base=base)


def output_contract(plan: SchedulerPlan, output_name: str) -> contract_registry.Contract:
    rule=(plan.doc.get("interface") or {}).get("outputs",{}).get(output_name)
    if not isinstance(rule,dict) or not isinstance(rule.get("contract"),str):
        raise ValueError(f"scheduler {plan.scheduler_id!r} has no contract for output {output_name!r}")
    return contract_registry.load(rule["contract"],base=plan.path.parent)


def output_name_for_semantic_type(plan: SchedulerPlan, semantic_type: str) -> str:
    matches=[]
    for name in (plan.doc.get("interface") or {}).get("outputs",{}):
        if output_contract(plan,name).semantic_type == semantic_type:
            matches.append(name)
    if len(matches) != 1:
        raise ValueError(f"scheduler {plan.scheduler_id!r} must expose exactly one output with semantic_type {semantic_type!r}; found {matches}")
    return matches[0]


def output_by_semantic_type(plan: SchedulerPlan, outputs: dict[str,Any], semantic_type: str) -> Any:
    return outputs[output_name_for_semantic_type(plan,semantic_type)]


def _check_prompt(base: Path, owner: str, pspec: dict) -> None:
    if not isinstance(pspec,dict) or not isinstance(pspec.get("template"),str):
        raise ValueError(f"{owner} requires prompt.template")
    template=(base/pspec["template"]).resolve()
    if not template.is_file():
        raise ValueError(f"missing prompt template for {owner}: {template}")
    slots=set(_SLOT_RE.findall(template.read_text(encoding="utf-8")))
    inject=pspec.get("inject") or {}
    if not isinstance(inject,dict):
        raise ValueError(f"{owner} prompt.inject must be mapping")
    if slots != set(inject):
        raise ValueError(f"{owner} prompt slots mismatch; missing declarations={sorted(slots-set(inject))}, unused declarations={sorted(set(inject)-slots)}")
    for name,rule in inject.items():
        if not isinstance(rule,dict):
            raise ValueError(f"{owner} inject {name!r} must be mapping")
        if "prompt" in rule:
            p=(base/rule["prompt"]).resolve()
            if not p.is_file(): raise ValueError(f"missing injected prompt {name!r}: {p}")
        if "contract" in rule:
            contract_registry.load(rule["contract"],base=base)
        if "contract_select" in rule:
            mapping=rule["contract_select"]
            if not isinstance(mapping,dict): raise ValueError(f"contract_select for {name!r} must be mapping")
            for ref in mapping.values(): contract_registry.load(ref,base=base)
        if "prompt_select" in rule:
            mapping=rule["prompt_select"]
            if not isinstance(mapping,dict): raise ValueError(f"prompt_select for {name!r} must be mapping")
            for rel in mapping.values():
                p=(base/rel).resolve()
                if not p.is_file(): raise ValueError(f"missing selected prompt {name!r}: {p}")


def _validate_prompt_assets(base: Path, doc: dict) -> None:
    for step in doc.get("steps") or []:
        if step.get("kind") in {"model","diagnosis_loop"}:
            _check_prompt(base,f"step {step['id']!r}",step.get("prompt"))
        elif step.get("kind") == "summarization_loop":
            prompts=step.get("prompts") or {}
            if set(prompts)!={"draft","align"}:
                raise ValueError(f"summarization_loop {step['id']!r} requires prompts.draft and prompts.align")
            _check_prompt(base,f"step {step['id']!r} draft",prompts["draft"])
            _check_prompt(base,f"step {step['id']!r} align",prompts["align"])


def describe(plan: SchedulerPlan) -> list[str]:
    lines=[]
    for step in plan.doc["steps"]:
        suffix=f" foreach={step['foreach']}" if step.get("foreach") else ""
        if step["kind"] in {"model","diagnosis_loop","summarization_loop"}:
            lines.append(f"{step['id']}: {step['kind']}{suffix} -> {step.get('output',{}).get('contract') or step.get('output',{}).get('contract_select') or 'untyped'}")
        else:
            lines.append(f"{step['id']}: {step['operation']}{suffix}")
    return lines


def _item_key(item: Any,index:int)->str:
    if isinstance(item,str): return item
    if isinstance(item,dict):
        return str(item.get("variant_id") or item.get("domain") and f"{item.get('domain')}-{item.get('key')}" or item.get("key") or index)
    return str(index)


def _get_path(value:Any,parts:list[str])->Any:
    for part in parts:
        if isinstance(value,dict): value=value[part]
        else: raise ValueError(f"cannot resolve .{part} from non-mapping")
    return value


def _core_source(token:str,ctx:prim.SchedulerContext,item:Any)->Any:
    # Public scheduler-facing core names mirror contract references so a developer
    # can resolve core.a.b directly to contracts/core/a/b.md.  Legacy aliases are
    # retained only for resume/backward compatibility with older run snapshots.
    aliases = {
        "case": "case.structured",
        "panel_scope": "setup.panel-scope",
        "allowed_who5_diseases": "setup.allowed-who5-diseases",
        "max_who5_passes": "diagnosis.max-who5-passes",
        "diagnoses": "diagnosis.who5.active",
        "final_cmcs": "diagnosis.routing.final-cmcs",
        "specs": "ptbg.task-scopes",
        "specs[$item]": "ptbg.task-scope",
        "diagnosis_context": "diagnosis.context",
        "treatment_owner[$item]": "ptbg.treatment-owner-current",
        "cited_facts": "facts.cited",
    }
    token = aliases.get(token, token)
    if token == "case.structured": return ctx.case
    if token == "setup.panel-scope": return ctx.values["panel_scope"]
    if token == "setup.allowed-who5-diseases": return ctx.values["allowed_who5_diseases"]
    if token == "diagnosis.bootstrap-evidence": return ctx.values["bootstrap_evidence"]
    if token == "diagnosis.max-who5-passes": return ctx.values["max_who5_passes"]
    if token == "diagnosis.who5.active": return ctx.diagnoses
    if token == "diagnosis.routing.final-cmcs": return ctx.final_cmcs
    if token == "diagnosis.context": return {"diagnoses":ctx.diagnoses,"final_cmcs":ctx.final_cmcs}
    if token == "ptbg.task-scopes": return ctx.specs
    if token == "ptbg.task-scope": return ctx.specs[item]
    if token == "ptbg.treatment-owner-current": return prim.treatment_owner_map(ctx.case)[item["gene"]] == item["variant_id"]
    if token == "facts.cited": return ctx.values["cited_facts"]
    if token == "evidence.domain-current": return ctx.ensure_evidence(item)
    if token == "evidence.cell-domain": return ctx.ensure_evidence(item["domain"])
    if token == "evidence.all-domains": return {d:ctx.ensure_evidence(d) for d in prim.DOMAINS}
    if token == "evidence.germline": return ctx.ensure_evidence("germline")
    # Older generic convenience sources remain internal/backward-compatible.
    if token == "variants": return ctx.case.get("variants") or []
    if token == "domains": return list(prim.DOMAINS)
    if token == "diagnosis_ids": return [d["diagnosis_id"] for d in ctx.diagnoses]
    if token == "treatment_owner_map": return prim.treatment_owner_map(ctx.case)
    if token in ctx.values: return ctx.values[token]
    if "." in token:
        head,*tail=token.split(".")
        if head in ctx.values: return _get_path(ctx.values[head],tail)
    raise ValueError(f"unknown core scheduler source core.{token}")


def _resolve_source(source:str,*,ctx:prim.SchedulerContext,results:dict,item:Any=None)->Any:
    if source == "$item": return item
    if source.startswith("$item."): return _get_path(item,source[len("$item."):].split("."))
    if source.startswith("core."): return _core_source(source[len("core."):],ctx,item)
    if source == "core.evidence.domain-current": return ctx.ensure_evidence(item)
    if source == "core.evidence.cell-domain": return ctx.ensure_evidence(item["domain"])
    if source == "core.evidence.all-domains": return {d:ctx.ensure_evidence(d) for d in prim.DOMAINS}
    if source == "core.evidence.germline": return ctx.ensure_evidence("germline")
    # Legacy aliases retained for frozen scheduler snapshots.
    if source == "diagnosis.bootstrap_evidence": return ctx.values["bootstrap_evidence"]
    if source == "evidence[$item]": return ctx.ensure_evidence(item)
    if source == "evidence[$item.domain]": return ctx.ensure_evidence(item["domain"])
    if source == "evidence.all": return {d:ctx.ensure_evidence(d) for d in prim.DOMAINS}
    if source.startswith("evidence.") and source[len("evidence."):] in prim.DOMAINS: return ctx.ensure_evidence(source[len("evidence."):])
    if source.startswith("steps."):
        rest=source[len("steps."):]
        if "[$item]" in rest:
            step_id,tail_text=rest.split("[$item]",1)
            if step_id not in results: raise ValueError(f"unresolved step source {source!r}")
            value=results[step_id][_item_key(item,1)]
            if tail_text.startswith(".") and tail_text[1:]: value=_get_path(value,tail_text[1:].split("."))
            return value
        step_id,*tail=rest.split(".")
        if step_id not in results: raise ValueError(f"unresolved step source {source!r}")
        value=results[step_id]
        if tail: value=_get_path(value,tail)
        return value
    raise ValueError(f"unknown scheduler source {source!r}")


def _resolve_inputs(spec:dict,*,ctx:prim.SchedulerContext,results:dict,item:Any=None)->dict:
    out={}
    for name,rule in (spec or {}).items():
        if isinstance(rule,str): out[name]=_resolve_source(rule,ctx=ctx,results=results,item=item)
        elif isinstance(rule,dict) and "source" in rule: out[name]=_resolve_source(rule["source"],ctx=ctx,results=results,item=item)
        elif isinstance(rule,dict) and "literal" in rule: out[name]=rule["literal"]
        else: raise ValueError(f"invalid input declaration {name!r}: {rule!r}")
    return out


def _foreach_values(token:str,*,ctx:prim.SchedulerContext,results:dict)->list[Any]:
    if token == "domains": return list(prim.DOMAINS)
    if token == "variants": return list(ctx.case.get("variants") or [])
    if token.startswith("steps."):
        value=_resolve_source(token,ctx=ctx,results=results)
        if isinstance(value,dict): return list(value.values())
        if isinstance(value,list): return value
    raise ValueError(f"unsupported foreach source {token!r}")


def _render_prompt_spec(base:Path,pspec:dict,inputs:dict,item:Any)->str:
    template=(base/pspec["template"]).read_text(encoding="utf-8"); values={}
    for slot,rule in (pspec.get("inject") or {}).items():
        if "prompt" in rule: values[slot]=(base/rule["prompt"]).read_text(encoding="utf-8").rstrip()
        elif "contract" in rule: values[slot]=contract_registry.load(rule["contract"],base=base).model_text
        elif "contract_select" in rule:
            key=item if isinstance(item,str) else rule.get("key"); ref=rule["contract_select"].get(key)
            if ref is None: raise ValueError(f"no contract_select value for {slot!r} key {key!r}")
            values[slot]=contract_registry.load(ref,base=base).model_text
        elif "prompt_select" in rule:
            key=item if isinstance(item,str) else rule.get("key"); rel=rule["prompt_select"].get(key)
            if rel is None: raise ValueError(f"no prompt_select value for {slot!r} key {key!r}")
            values[slot]=(base/rel).read_text(encoding="utf-8").rstrip()
        elif "input" in rule:
            if rule["input"] not in inputs: raise ValueError(f"prompt slot {slot!r} references undeclared input {rule['input']!r}")
            values[slot]=prim.dump(inputs[rule["input"]],rule.get("render"))
        elif "literal" in rule: values[slot]=str(rule["literal"])
        else: raise ValueError(f"prompt slot {slot!r} has no prompt/input/literal source")
    return _SLOT_RE.sub(lambda m:values[m.group(1)],template)


def _validator(name:str,*,ctx:prim.SchedulerContext,inputs:dict,item:Any):
    if name == "domain":
        domain=item; evidence=inputs.get("evidence")
        permitted=evidence.permitted_tags if isinstance(evidence,prim.EvidenceView) else prim.normalized_tags(inputs.get("normalized_evidence") or {})
        return lambda text:runtime.validate_domain_text(text,domain=domain,spec=ctx.specs[domain],permitted_tags=permitted)
    if name == "normalized_evidence": return lambda text:prim.validate_normalized(text,evidence=inputs["evidence"],diagnosis_ids=set(d["diagnosis_id"] for d in ctx.diagnoses))
    if name == "variant_cross_domain":
        owners=prim.treatment_owner_map(ctx.case); include=owners[item["gene"]]==item["variant_id"]
        return lambda text:prim.validate_variant(text,item=item,ctx=ctx,evidence=inputs["evidence"],include_treatment=include)
    if name == "germline_clinical_picture": return lambda text:prim.validate_clinical_picture(text,ctx=ctx,evidence=inputs["evidence"])
    if name == "global_ledger": return lambda text:prim.validate_global(text,ctx=ctx,evidence=inputs["evidence"])
    if name == "global_patch": return lambda text:prim.validate_global_patch(text,ctx=ctx,evidence=inputs["evidence"])
    if name == "adaptive_cell_review": return lambda text:prim.validate_cell_review(text,item=item,ctx=ctx,evidence=inputs["evidence"])
    if name == "icc":
        evidence=inputs["evidence"]; return lambda text:runtime.validate_icc_text(text,evidence.permitted_tags)
    if name == "who5":
        evidence=inputs["evidence"]; return lambda text:runtime.validate_who5_text(text,evidence.permitted_tags)
    if name == "summary_text": return runtime.validate_summary_text
    if name == "sentence_alignment":
        sentences=runtime.sentence_manifest(inputs["draft"]); facts=inputs["facts"]
        return lambda text:runtime.validate_sentence_alignment_text(text,sentences,facts)
    if name == "summary_pairs":
        facts=inputs["facts"]
        def validate(text:str)->str:
            prim.validate_summary_pairs_doc(runtime.parse_yaml_mapping(text,"summary sentence pairs"),facts)
            return "summary sentence pairs validated"
        return validate
    raise ValueError(f"unknown scheduler validator {name!r}")


def _artifact_path(root:Path,step:dict,item:Any,index:int)->Path:
    key=_item_key(item,index); suffix=step.get("output",{}).get("suffix")
    if not suffix: suffix="md" if step.get("output",{}).get("format")=="text" else "yaml"
    return root/step["id"]/f"{key}.{suffix}"


def _role_for(plan:SchedulerPlan,step:dict,secondary:bool=False)->str:
    explicit=step.get("role")
    if explicit: return explicit
    if plan.phase == "diagnosis": return "diagnosis"
    if plan.phase == "ptbg": return "ptbg"
    if plan.phase == "summarization": return "summarization_review" if secondary else "summarization"
    raise ValueError(plan.phase)


def _run_model(plan:SchedulerPlan,ctx:prim.SchedulerContext,base:Path,root:Path,step:dict,results:dict)->Any:
    items=_foreach_values(step["foreach"],ctx=ctx,results=results) if step.get("foreach") else [None]; collection={}
    for index,item in enumerate(items,1):
        inputs=_resolve_inputs(step.get("inputs") or {},ctx=ctx,results=results,item=item)
        output=_artifact_path(root,step,item,index); output.parent.mkdir(parents=True,exist_ok=True)
        prompt=_render_prompt_spec(base,step["prompt"],inputs,item); validator=_validator(step["output"]["validator"],ctx=ctx,inputs=inputs,item=item)
        fmt=step["output"]["format"]
        if output.is_file(): validator(ctx.read_text(output))
        else: ctx.call_model(call_id=f"scheduler-{plan.phase}-{plan.scheduler_id}-{step['id']}-{_item_key(item,index)}",role=_role_for(plan,step),prompt=prompt,output=output,validator=validator,format_name=fmt)
        value=runtime.parse_yaml_mapping(ctx.read_text(output),f"scheduler {step['id']} output") if fmt=="yaml" else ctx.read_text(output)
        if step.get("foreach"):
            if step.get("retain_item_metadata"): collection[_item_key(item,index)]={"__item__":item,"__payload__":value}
            else: collection[_item_key(item,index)]=value
        else: collection=value
    return collection


def _run_diagnosis_loop(plan:SchedulerPlan,ctx:prim.SchedulerContext,base:Path,root:Path,step:dict,results:dict)->dict:
    if ctx.ensure_diagnosis_evidence is None: raise ValueError("diagnosis scheduler context lacks diagnosis evidence provider")
    static=_resolve_inputs(step.get("inputs") or {},ctx=ctx,results=results); history=[]
    for cmc in ctx.case.get("bootstrap_cmcs") or []:
        if cmc not in history: history.append(cmc)
    loop=step.get("loop") or {}; max_value=loop.get("max_passes",7)
    max_passes=int(_resolve_source(max_value,ctx=ctx,results=results) if isinstance(max_value,str) and max_value.startswith("core.") else max_value)
    instructions=loop.get("instructions") or {}; required={"main","reconsider","review"}
    if set(instructions)!=required: raise ValueError(f"diagnosis loop instructions must map exactly {sorted(required)}")
    previous=None; phase="main"; transitions=0; audit=[]; final=None
    for pass_index in range(1,max_passes+1):
        evidence=ctx.ensure_diagnosis_evidence(history)
        inputs=dict(static,evidence=evidence,prior_state=previous,phase_instruction=instructions[phase])
        prompt=_render_prompt_spec(base,step["prompt"],inputs,None)
        output=root/step["id"]/f"pass-{pass_index:02d}-{phase}.yaml"; output.parent.mkdir(parents=True,exist_ok=True)
        validator=lambda text,e=evidence:runtime.validate_who5_text(text,e.permitted_tags)
        ctx.status(f"WHO5 scheduler pass {pass_index}: {phase}; {len(evidence.cards)} cards; cumulative CMC evidence {' | '.join(history)}")
        if output.is_file(): validator(ctx.read_text(output))
        else: ctx.call_model(call_id=f"scheduler-diagnosis-{plan.scheduler_id}-who5-{pass_index:02d}-{phase}",role="diagnosis",prompt=prompt,output=output,validator=validator,format_name="yaml")
        state=runtime.parse_yaml_mapping(ctx.read_text(output),"WHO5 diagnosis"); cmcs=runtime.derive_cmcs(state); sig=runtime.who5_signature(state)
        prev_cmcs=runtime.derive_cmcs(previous) if previous is not None else None; prev_sig=runtime.who5_signature(previous) if previous is not None else None
        if prev_cmcs is not None and cmcs!=prev_cmcs: transitions+=1
        new=[]
        for cmc in cmcs:
            if cmc not in history: history.append(cmc); new.append(cmc)
        audit.append({"pass":pass_index,"phase":phase,"who5_signature":sig,"derived_cmcs":cmcs,"new_cmc_evidence_added":new,"cumulative_cmc_history":list(history),"card_count":len(evidence.cards)})
        if transitions>4: raise ValueError("WHO5/CMC routing oscillated through more than four CMC transitions")
        if previous is None: previous=state; phase="reconsider"; continue
        unchanged=sig==prev_sig; previous=state
        if phase=="review" and unchanged: final=state; break
        if phase=="review" and not unchanged: phase="reconsider"; continue
        if phase=="reconsider" and unchanged: phase="review"; continue
        phase="reconsider"
    if final is None: raise ValueError(f"WHO5 diagnosis did not stabilise within {max_passes} passes")
    routing={"schema_version":1,"final_cmcs":runtime.derive_cmcs(final),"diagnostic_cmc_history":history,"passes":audit}
    return {"who5":final,"routing":routing}


def _run_summarization_loop(plan:SchedulerPlan,ctx:prim.SchedulerContext,base:Path,root:Path,step:dict,results:dict)->dict:
    inputs=_resolve_inputs(step.get("inputs") or {},ctx=ctx,results=results); facts=inputs["facts"]
    max_cycles=int((step.get("loop") or {}).get("max_cycles",2)); correction=""
    for cycle in range(1,max_cycles+1):
        draft_inputs=dict(inputs,correction=correction)
        draft_prompt=_render_prompt_spec(base,step["prompts"]["draft"],draft_inputs,None)
        draft=root/step["id"]/f"draft-{cycle}.md"; draft.parent.mkdir(parents=True,exist_ok=True)
        if draft.is_file(): runtime.validate_summary_text(ctx.read_text(draft))
        else: ctx.call_model(call_id=f"scheduler-summarization-{plan.scheduler_id}-draft-{cycle}",role="summarization",prompt=draft_prompt,output=draft,validator=runtime.validate_summary_text,format_name="text")
        draft_text=ctx.read_text(draft); sentence_manifest=runtime.sentence_manifest(draft_text)
        align_inputs=dict(inputs,draft=draft_text,sentence_manifest=sentence_manifest)
        align_prompt=_render_prompt_spec(base,step["prompts"]["align"],align_inputs,None)
        alignment=root/step["id"]/f"alignment-{cycle}.yaml"
        validator=_validator("sentence_alignment",ctx=ctx,inputs=align_inputs,item=None)
        if alignment.is_file(): validator(ctx.read_text(alignment))
        else: ctx.call_model(call_id=f"scheduler-summarization-{plan.scheduler_id}-align-{cycle}",role="summarization_review",prompt=align_prompt,output=alignment,validator=validator,format_name="yaml")
        align_doc=runtime.parse_yaml_mapping(ctx.read_text(alignment),"sentence-to-fact alignment"); uncovered=runtime.uncovered_fact_ids(align_doc,facts)
        if not uncovered:
            rows=prim._summary_rows_from_alignment(draft_text,align_doc,facts)
            return {"summary":{"sentences":rows}}
        omitted=[next(f for f in facts if f["fact_id"]==fid) for fid in uncovered]
        correction="# Required correction from prior semantic alignment\nThe prior draft omitted these locked facts. Rewrite the complete report so all are represented:\n```yaml\n"+yaml.safe_dump({"omitted_facts":omitted},sort_keys=False,allow_unicode=True,width=110)+"```"
    raise ValueError(f"final prose remained semantically incomplete after {max_cycles} synthesis cycles")


def execute(plan:SchedulerPlan,ctx:prim.SchedulerContext)->dict[str,Any]:
    root=layout.scheduler_dir(ctx.work,f"{plan.phase}-{plan.scheduler_id}",existing=False); results:dict[str,Any]={}; base=plan.path.parent
    for step in plan.doc["steps"]:
        kind=step["kind"]
        if kind=="model": results[step["id"]]=_run_model(plan,ctx,base,root,step,results)
        elif kind=="diagnosis_loop": results[step["id"]]=_run_diagnosis_loop(plan,ctx,base,root,step,results)
        elif kind=="summarization_loop": results[step["id"]]=_run_summarization_loop(plan,ctx,base,root,step,results)
        else:
            inputs=_resolve_inputs(step.get("inputs") or {},ctx=ctx,results=results); op=prim.OPERATIONS[step["operation"]]
            results[step["id"]]=op(ctx=ctx,inputs=inputs,root=root/step["id"])
    return {key:_resolve_source(ref,ctx=ctx,results=results) for key,ref in plan.doc["outputs"].items()}
