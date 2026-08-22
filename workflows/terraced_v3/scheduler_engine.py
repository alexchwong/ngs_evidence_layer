"""Declarative scheduler engine for terraced-v3."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import re
import yaml

from workflows.terraced_v3 import layout, runtime
from workflows.terraced_v3 import scheduler_primitives as prim

_SLOT_RE = re.compile(r"\{\{([A-Za-z0-9_.-]+)\}\}")


@dataclass
class SchedulerPlan:
    scheduler_id: str
    description: str
    path: Path
    doc: dict


def load_yaml(path: Path) -> SchedulerPlan:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict): raise ValueError(f"scheduler YAML must be a mapping: {path}")
    meta = doc.get("scheduler")
    if not isinstance(meta, dict): raise ValueError("scheduler.yaml requires scheduler mapping")
    sid = meta.get("id"); version = meta.get("version")
    if not isinstance(sid, str) or not sid: raise ValueError("scheduler.id must be non-empty")
    if version != 1: raise ValueError(f"unsupported scheduler schema version {version!r}")
    steps = doc.get("steps")
    if not isinstance(steps, list) or not steps: raise ValueError("scheduler.steps must be a non-empty list")
    ids=[]
    for i, step in enumerate(steps):
        if not isinstance(step, dict): raise ValueError(f"steps[{i}] must be a mapping")
        if not isinstance(step.get("id"), str): raise ValueError(f"steps[{i}].id missing")
        if step["id"] in ids: raise ValueError(f"duplicate scheduler step id {step['id']!r}")
        previous=set(ids)
        kind=step.get("kind")
        if kind not in {"model","operation"}: raise ValueError(f"step {step['id']!r} kind must be model or operation")
        for dep in step.get("depends_on") or []:
            if dep not in previous: raise ValueError(f"step {step['id']!r} depends on unknown or later step {dep!r}")
        foreach=step.get("foreach")
        if isinstance(foreach,str) and foreach.startswith("steps."):
            ref=foreach[len("steps."):].split(".")[0]
            if ref not in previous: raise ValueError(f"step {step['id']!r} foreach references unknown or later step {ref!r}")
        for name, rule in (step.get("inputs") or {}).items():
            source=rule if isinstance(rule,str) else rule.get("source") if isinstance(rule,dict) else None
            if isinstance(source,str) and source.startswith("steps."):
                rest=source[len("steps."):].split("[$item]",1)[0]
                ref=rest.split(".")[0]
                if ref not in previous: raise ValueError(f"step {step['id']!r} input {name!r} references unknown or later step {ref!r}")
        if kind == "operation" and step.get("operation") not in prim.OPERATIONS:
            raise ValueError(f"step {step['id']!r} uses unknown operation {step.get('operation')!r}")
        if kind == "model":
            output=step.get("output") or {}
            if output.get("format") != "yaml": raise ValueError(f"scheduler model step {step['id']!r} currently requires output.format: yaml")
            if output.get("validator") not in {"domain","normalized_evidence","variant_cross_domain","germline_clinical_picture","global_ledger","global_patch","adaptive_cell_review"}:
                raise ValueError(f"step {step['id']!r} uses unknown validator {output.get('validator')!r}")
        ids.append(step["id"])
    outputs = doc.get("outputs")
    if not isinstance(outputs, dict) or set(outputs) != set(prim.DOMAINS):
        raise ValueError(f"scheduler.outputs must map exactly {list(prim.DOMAINS)}")
    for d, ref in outputs.items():
        if not isinstance(ref, str) or not ref.startswith("steps."):
            raise ValueError(f"scheduler output {d!r} must reference steps.<id>.<domain>")
        target=ref[len("steps."):].split(".")[0]
        if target not in ids: raise ValueError(f"scheduler output {d!r} references unknown step {target!r}")
    _validate_prompt_assets(path.parent, doc)
    return SchedulerPlan(sid, str(meta.get("description") or ""), path, doc)


def _validate_prompt_assets(base: Path, doc: dict) -> None:
    for step in doc.get("steps") or []:
        if step.get("kind") != "model": continue
        prompt = step.get("prompt")
        if not isinstance(prompt, dict) or not isinstance(prompt.get("template"), str):
            raise ValueError(f"model step {step['id']!r} requires prompt.template")
        template = (base / prompt["template"]).resolve()
        if not template.is_file(): raise ValueError(f"missing prompt template for {step['id']}: {template}")
        slots = set(_SLOT_RE.findall(template.read_text(encoding="utf-8")))
        inject = prompt.get("inject") or {}
        if not isinstance(inject, dict): raise ValueError(f"step {step['id']!r} prompt.inject must be mapping")
        declared = set(inject)
        if slots != declared:
            missing=slots-declared; extra=declared-slots
            raise ValueError(f"step {step['id']!r} prompt slots mismatch; missing declarations={sorted(missing)}, unused declarations={sorted(extra)}")
        for name, rule in inject.items():
            if not isinstance(rule, dict): raise ValueError(f"step {step['id']!r} inject {name!r} must be mapping")
            if "prompt" in rule:
                p=(base/rule["prompt"]).resolve()
                if not p.is_file(): raise ValueError(f"missing injected prompt {name!r}: {p}")
            if "prompt_select" in rule:
                mapping=rule["prompt_select"]
                if not isinstance(mapping, dict): raise ValueError(f"prompt_select for {name!r} must be mapping")
                for rel in mapping.values():
                    p=(base/rel).resolve()
                    if not p.is_file(): raise ValueError(f"missing selected prompt {name!r}: {p}")


def describe(plan: SchedulerPlan) -> list[str]:
    lines=[]
    for step in plan.doc["steps"]:
        suffix=f" foreach={step['foreach']}" if step.get("foreach") else ""
        if step["kind"] == "model": lines.append(f"{step['id']}: model{suffix} -> {step.get('output',{}).get('contract','untyped')}")
        else: lines.append(f"{step['id']}: {step['operation']}{suffix}")
    return lines


def _item_key(item: Any, index: int) -> str:
    if isinstance(item, str): return item
    if isinstance(item, dict):
        return str(item.get("variant_id") or item.get("domain") and f"{item.get('domain')}-{item.get('key')}" or item.get("key") or index)
    return str(index)


def _get_path(value: Any, parts: list[str]) -> Any:
    for part in parts:
        if isinstance(value, dict): value=value[part]
        else: raise ValueError(f"cannot resolve .{part} from non-mapping")
    return value


def _resolve_source(source: str, *, ctx: prim.SchedulerContext, results: dict, item: Any=None, domain: str|None=None) -> Any:
    if source == "$item": return item
    if source.startswith("$item."):
        return _get_path(item, source[len("$item."):].split("."))
    if source == "core.case": return ctx.case
    if source == "core.diagnoses": return ctx.diagnoses
    if source == "core.final_cmcs": return ctx.final_cmcs
    if source == "core.specs": return ctx.specs
    if source == "core.specs[$item]": return ctx.specs[item]
    if source == "core.variants": return ctx.case.get("variants") or []
    if source == "core.domains": return list(prim.DOMAINS)
    if source == "core.diagnosis_ids": return [d["diagnosis_id"] for d in ctx.diagnoses]
    if source == "core.diagnosis_context": return {"diagnoses": ctx.diagnoses, "final_cmcs": ctx.final_cmcs}
    if source == "core.treatment_owner_map": return prim.treatment_owner_map(ctx.case)
    if source == "core.treatment_owner[$item]": return prim.treatment_owner_map(ctx.case)[item["gene"]] == item["variant_id"]
    if source == "evidence[$item]": return ctx.ensure_evidence(item)
    if source == "evidence[$item.domain]": return ctx.ensure_evidence(item["domain"])
    if source == "evidence.all": return {d: ctx.ensure_evidence(d) for d in prim.DOMAINS}
    if source.startswith("evidence.") and source[len("evidence."):] in prim.DOMAINS: return ctx.ensure_evidence(source[len("evidence."):])
    if source.startswith("steps."):
        rest=source[len("steps."):]
        if "[$item]" in rest:
            step_id, tail_text = rest.split("[$item]", 1)
            if step_id not in results: raise ValueError(f"unresolved step source {source!r}")
            key=_item_key(item,1)
            value=results[step_id][key]
            if tail_text.startswith(".") and tail_text[1:]: value=_get_path(value,tail_text[1:].split("."))
            return value
        step_id, *tail = rest.split(".")
        if step_id not in results: raise ValueError(f"unresolved step source {source!r}")
        value=results[step_id]
        if tail: value=_get_path(value,tail)
        return value
    raise ValueError(f"unknown scheduler source {source!r}")


def _resolve_inputs(spec: dict, *, ctx: prim.SchedulerContext, results: dict, item: Any=None) -> dict:
    out={}
    for name, rule in (spec or {}).items():
        if isinstance(rule,str): out[name]=_resolve_source(rule,ctx=ctx,results=results,item=item)
        elif isinstance(rule,dict) and "source" in rule: out[name]=_resolve_source(rule["source"],ctx=ctx,results=results,item=item)
        elif isinstance(rule,dict) and "literal" in rule: out[name]=rule["literal"]
        else: raise ValueError(f"invalid input declaration {name!r}: {rule!r}")
    return out


def _foreach_values(token: str, *, ctx: prim.SchedulerContext, results: dict) -> list[Any]:
    if token == "domains": return list(prim.DOMAINS)
    if token == "variants": return list(ctx.case.get("variants") or [])
    if token.startswith("steps."):
        value=_resolve_source(token,ctx=ctx,results=results)
        if isinstance(value,dict): return list(value.values())
        if isinstance(value,list): return value
    raise ValueError(f"unsupported foreach source {token!r}")


def _render_prompt(base: Path, step: dict, inputs: dict, item: Any) -> str:
    pspec=step["prompt"]; template=(base/pspec["template"]).read_text(encoding="utf-8")
    values={}
    for slot, rule in (pspec.get("inject") or {}).items():
        if "prompt" in rule:
            values[slot]=(base/rule["prompt"]).read_text(encoding="utf-8").rstrip()
        elif "prompt_select" in rule:
            key=item if isinstance(item,str) else rule.get("key")
            rel=rule["prompt_select"].get(key)
            if rel is None: raise ValueError(f"no prompt_select value for {slot!r} key {key!r}")
            values[slot]=(base/rel).read_text(encoding="utf-8").rstrip()
        elif "input" in rule:
            if rule["input"] not in inputs: raise ValueError(f"prompt slot {slot!r} references undeclared input {rule['input']!r}")
            values[slot]=prim.dump(inputs[rule["input"]],rule.get("render"))
        elif "literal" in rule: values[slot]=str(rule["literal"])
        else: raise ValueError(f"prompt slot {slot!r} has no prompt/input/literal source")
    return _SLOT_RE.sub(lambda m: values[m.group(1)],template)


def _validator(name: str, *, ctx: prim.SchedulerContext, inputs: dict, item: Any):
    if name == "domain":
        domain=item
        evidence=inputs.get("evidence")
        permitted=evidence.permitted_tags if isinstance(evidence,prim.EvidenceView) else prim.normalized_tags(inputs.get("normalized_evidence") or {})
        spec=ctx.specs[domain]
        return lambda text: runtime.validate_domain_text(text,domain=domain,spec=spec,permitted_tags=permitted)
    if name == "normalized_evidence": return lambda text: prim.validate_normalized(text,evidence=inputs["evidence"],diagnosis_ids=set(d["diagnosis_id"] for d in ctx.diagnoses))
    if name == "variant_cross_domain":
        owners=prim.treatment_owner_map(ctx.case); include=owners[item["gene"]] == item["variant_id"]
        return lambda text: prim.validate_variant(text,item=item,ctx=ctx,evidence=inputs["evidence"],include_treatment=include)
    if name == "germline_clinical_picture": return lambda text: prim.validate_clinical_picture(text,ctx=ctx,evidence=inputs["evidence"])
    if name == "global_ledger": return lambda text: prim.validate_global(text,ctx=ctx,evidence=inputs["evidence"])
    if name == "global_patch": return lambda text: prim.validate_global_patch(text,ctx=ctx,evidence=inputs["evidence"])
    if name == "adaptive_cell_review": return lambda text: prim.validate_cell_review(text,item=item,ctx=ctx,evidence=inputs["evidence"])
    raise ValueError(f"unknown scheduler validator {name!r}")


def _artifact_path(root: Path, step: dict, item: Any, index: int) -> Path:
    key=_item_key(item,index)
    suffix=step.get("output",{}).get("suffix","yaml")
    return root/step["id"]/f"{key}.{suffix}"


def execute(plan: SchedulerPlan, ctx: prim.SchedulerContext) -> dict[str,dict]:
    root=layout.scheduler_dir(ctx.work,plan.scheduler_id,existing=False); results: dict[str,Any]={}; base=plan.path.parent
    for step in plan.doc["steps"]:
        kind=step["kind"]
        if kind == "model":
            items=_foreach_values(step["foreach"],ctx=ctx,results=results) if step.get("foreach") else [None]
            collection={}
            for index,item in enumerate(items,1):
                inputs=_resolve_inputs(step.get("inputs") or {},ctx=ctx,results=results,item=item)
                output=_artifact_path(root,step,item,index); output.parent.mkdir(parents=True,exist_ok=True)
                prompt=_render_prompt(base,step,inputs,item)
                validator=_validator(step.get("output",{}).get("validator"),ctx=ctx,inputs=inputs,item=item)
                if output.is_file(): validator(ctx.read_text(output))
                else: ctx.call_yaml(call_id=f"scheduler-{plan.scheduler_id}-{step['id']}-{_item_key(item,index)}",prompt=prompt,output=output,validator=validator)
                doc=runtime.parse_yaml_mapping(ctx.read_text(output),f"scheduler {step['id']} output")
                if step.get("foreach"):
                    if step.get("retain_item_metadata"):
                        collection[_item_key(item,index)]={"__item__":item,"__payload__":doc}
                    else: collection[_item_key(item,index)]=doc
                else: collection=doc
            results[step["id"]]=collection
        else:
            inputs=_resolve_inputs(step.get("inputs") or {},ctx=ctx,results=results)
            op=prim.OPERATIONS[step["operation"]]
            results[step["id"]]=op(ctx=ctx,inputs=inputs,root=root/step["id"])
    outputs={}
    for domain,ref in plan.doc["outputs"].items():
        value=_resolve_source(ref,ctx=ctx,results=results)
        outputs[domain]=value
    return outputs
