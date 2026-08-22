"""Declarative DAG pipeline discovery, compatibility validation, and model bindings."""
from __future__ import annotations

import copy
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml

from workflows.terraced_v3.model_binding import Binding
from workflows.terraced_v3 import contract_registry, module_registry, scheduler_engine, scheduler_registry

HERE = Path(__file__).resolve().parent
ROOT = HERE / "pipelines"
ROLES = (
    "structure", "diagnosis", "ptbg", "evidence_alignment",
    "summarization", "summarization_review", "syntax_repair",
)
PHASES = ("diagnosis", "ptbg", "summarization")


@dataclass(frozen=True)
class PipelineModule:
    module_id: str
    uses: str
    inputs: dict[str, str]


@dataclass(frozen=True)
class PipelinePlan:
    pipeline_id: str
    description: str
    path: Path
    doc: dict[str, Any]
    modules: tuple[PipelineModule, ...]

    @property
    def schedulers(self) -> dict[str, str]:
        found: dict[str, str] = {}
        for module in self.modules:
            if module.uses.startswith("scheduler."):
                _prefix, phase, name = module.uses.split(".", 2)
                found[phase] = name
        return found


def _paths() -> dict[str, Path]:
    rows=[]
    if ROOT.is_dir():
        for path in ROOT.glob("*.yaml"):
            plan=load_yaml(path, validate_graph=False)
            rows.append((int((plan.doc.get("pipeline") or {}).get("order",999)),plan.pipeline_id,path))
    out={}
    for _,pid,path in sorted(rows,key=lambda row:(row[0],row[1])):
        if pid in out: raise ValueError(f"duplicate pipeline id {pid!r}")
        out[pid]=path
    return out


def _module_spec(uses: str):
    if uses.startswith("core."):
        return module_registry.load_core(uses)
    if uses.startswith("adapter."):
        return module_registry.load_adapter(uses)
    if uses.startswith("scheduler."):
        parts=uses.split(".",2)
        if len(parts)!=3 or parts[1] not in PHASES:
            raise ValueError(f"invalid scheduler module reference {uses!r}; expected scheduler.<phase>.<id>")
        phase,name=parts[1],parts[2]
        plan=scheduler_registry.load(name,phase)
        interface=plan.doc["interface"]
        class Spec: pass
        spec=Spec(); spec.module_id=uses; spec.kind="scheduler"; spec.handler=f"{phase}_scheduler"; spec.description=plan.description; spec.path=plan.path
        spec.inputs={name:rule["contract"] for name,rule in interface["inputs"].items()}
        spec.outputs={name:rule["contract"] for name,rule in interface["outputs"].items()}
        spec.base=plan.path.parent
        return spec
    raise ValueError(f"unsupported pipeline module reference {uses!r}")


def _contract_for(ref: str, *, base: Path | None = None):
    return contract_registry.load(ref,base=base)


def _spec_contract(spec, side: str, name: str):
    refs=getattr(spec,side)
    if name not in refs: raise ValueError(f"module {spec.module_id!r} has no declared {side[:-1]} {name!r}")
    base=getattr(spec,"base",None) or spec.path.parent
    return _contract_for(refs[name],base=base)


def validate(plan: PipelinePlan) -> PipelinePlan:
    external=plan.doc.get("inputs") or {}
    if not isinstance(external,dict): raise ValueError("pipeline.inputs must be a mapping")
    external_contracts={}
    for name,rule in external.items():
        if not isinstance(rule,dict) or not isinstance(rule.get("contract"),str):
            raise ValueError(f"pipeline.inputs.{name} must declare contract")
        external_contracts[name]=contract_registry.load(rule["contract"],base=plan.path.parent)

    produced: dict[tuple[str,str], Any] = {}
    seen=set()
    for module in plan.modules:
        if module.module_id in seen: raise ValueError(f"duplicate pipeline module id {module.module_id!r}")
        spec=_module_spec(module.uses)
        expected=set(spec.inputs)
        if set(module.inputs)!=expected:
            raise ValueError(
                f"pipeline module {module.module_id!r} ({module.uses}) inputs must map exactly {sorted(expected)}; "
                f"received {sorted(module.inputs)}"
            )
        for input_name,source in module.inputs.items():
            consumer=_spec_contract(spec,"inputs",input_name)
            if source.startswith("inputs."):
                ext=source[len("inputs."):]
                if ext not in external_contracts:
                    raise ValueError(f"module {module.module_id!r} input {input_name!r} references unknown pipeline input {source!r}")
                producer=external_contracts[ext]
                producer_label=source
            else:
                if "." not in source:
                    raise ValueError(f"module {module.module_id!r} input {input_name!r} source must be inputs.<name> or <upstream>.<output>")
                upstream,output=source.split(".",1)
                if upstream not in seen:
                    raise ValueError(f"module {module.module_id!r} input {input_name!r} references non-upstream module {upstream!r}")
                key=(upstream,output)
                if key not in produced:
                    choices=sorted(o for (m,o) in produced if m==upstream)
                    raise ValueError(f"module {module.module_id!r} input {input_name!r} references missing output {source!r}; upstream outputs={choices}")
                producer=produced[key]; producer_label=source
            issues=contract_registry.compatibility(producer,consumer)
            if issues:
                detail="; ".join(issues)
                raise ValueError(
                    f"pipeline contract mismatch at module {module.module_id!r} input {input_name!r}: {detail}. "
                    f"Source {producer_label} uses {producer.path}; expected contract is {consumer.path}. "
                    "Connect an explicit adapter module or change the producer/consumer contract."
                )
        for output_name in spec.outputs:
            produced[(module.module_id,output_name)] = _spec_contract(spec,"outputs",output_name)
        seen.add(module.module_id)

    # Provider/model-role validation is part of setup validation too.
    for role in ROLES: binding(plan,role)
    return plan


def load_yaml(path: Path, *, validate_graph: bool = True) -> PipelinePlan:
    try: doc=yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError,yaml.YAMLError) as exc: raise ValueError(f"cannot read pipeline YAML {path}: {exc}") from exc
    if not isinstance(doc,dict): raise ValueError(f"pipeline YAML must be a mapping: {path}")
    meta=doc.get("pipeline")
    if not isinstance(meta,dict): raise ValueError("pipeline YAML requires pipeline mapping")
    pid=meta.get("id")
    if not isinstance(pid,str) or not pid: raise ValueError("pipeline.id must be non-empty")
    if meta.get("version") != 2: raise ValueError(f"unsupported pipeline version {meta.get('version')!r}; expected 2")
    provider=doc.get("provider")
    if not isinstance(provider,dict): raise ValueError("pipeline.provider must be a mapping")
    if provider.get("type") not in {"self","openai-compatible"}: raise ValueError(f"pipeline {pid!r} uses unsupported provider type {provider.get('type')!r}")
    rows=doc.get("modules")
    if not isinstance(rows,list) or not rows: raise ValueError("pipeline.modules must be a non-empty ordered DAG module list")
    modules=[]
    for i,row in enumerate(rows):
        if not isinstance(row,dict): raise ValueError(f"pipeline.modules[{i}] must be a mapping")
        mid=row.get("id"); uses=row.get("uses"); inputs=row.get("inputs") or {}
        if not isinstance(mid,str) or not mid: raise ValueError(f"pipeline.modules[{i}].id must be non-empty")
        if not isinstance(uses,str) or not uses: raise ValueError(f"pipeline module {mid!r} requires uses")
        if not isinstance(inputs,dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in inputs.items()):
            raise ValueError(f"pipeline module {mid!r} inputs must map names to source strings")
        _module_spec(uses)
        modules.append(PipelineModule(mid,uses,dict(inputs)))
    models=doc.get("models")
    if not isinstance(models,dict) or set(models)!=set(ROLES): raise ValueError(f"pipeline.models must map exactly {list(ROLES)}")
    for role in ROLES:
        row=models[role]
        if not isinstance(row,dict): raise ValueError(f"pipeline.models.{role} must be a mapping")
        if not isinstance(row.get("model"),str) or not row["model"]: raise ValueError(f"pipeline.models.{role}.model must be non-empty")
        if not isinstance(row.get("max_tokens"),int) or row["max_tokens"]<=0: raise ValueError(f"pipeline.models.{role}.max_tokens must be a positive integer")
        if not isinstance(row.get("temperature",0.0),(int,float)): raise ValueError(f"pipeline.models.{role}.temperature must be numeric")
    plan=PipelinePlan(pid,str(meta.get("description") or ""),path,doc,tuple(modules))
    return validate(plan) if validate_graph else plan


def names()->tuple[str,...]: return tuple(_paths())
def load(name:str)->PipelinePlan:
    paths=_paths()
    if name not in paths: raise ValueError(f"unknown terraced-v3 pipeline {name!r}; choose one of: {', '.join(paths)}")
    return load_yaml(paths[name])
def descriptions()->dict[str,str]: return {name:load(name).description for name in names()}


def with_scheduler_overrides(plan: PipelinePlan, overrides: dict[str,str]) -> PipelinePlan:
    doc=copy.deepcopy(plan.doc)
    for phase,name in overrides.items():
        if not name: continue
        scheduler_registry.load(name,phase)
        indices=[i for i,row in enumerate(doc["modules"]) if str(row.get("uses","")).startswith(f"scheduler.{phase}.")]
        if len(indices)!=1:
            raise ValueError(f"pipeline {plan.pipeline_id!r} must contain exactly one scheduler.{phase} module for CLI override; found {len(indices)}")
        doc["modules"][indices[0]]["uses"]=f"scheduler.{phase}.{name}"
    # Overrides may change interface names.  The standard shipped schedulers use the same named edges;
    # if a custom override differs, graph validation explains exactly which mapping must change.
    temp=PipelinePlan(plan.pipeline_id,plan.description,plan.path,doc,tuple(
        PipelineModule(row["id"],row["uses"],dict(row.get("inputs") or {})) for row in doc["modules"]
    ))
    return validate(temp)


def binding(plan:PipelinePlan,role:str)->Binding:
    if role not in ROLES: raise ValueError(f"unknown pipeline model role {role!r}; choose one of: {', '.join(ROLES)}")
    provider=plan.doc["provider"]; row=plan.doc["models"][role]; kind=provider["type"]
    if kind=="self":
        return Binding(pipeline=plan.pipeline_id,role=role,kind="self",model="self",temperature=float(row.get("temperature",0.0)),max_tokens=int(row["max_tokens"]))
    base_url=str(provider.get("base_url") or ""); env=str(provider.get("base_url_env") or "")
    if env and os.environ.get(env,"").strip(): base_url=os.environ[env].strip()
    if not base_url: raise ValueError(f"pipeline {plan.pipeline_id!r} has no provider base_url")
    api_key_env=str(provider.get("api_key_env") or "")
    return Binding(pipeline=plan.pipeline_id,role=role,kind="openai-compatible",model=str(row["model"]),temperature=float(row.get("temperature",0.0)),max_tokens=int(row["max_tokens"]),base_url=base_url.rstrip("/"),base_url_env=env,api_key_env=api_key_env,api_key=os.environ.get(api_key_env,"") if api_key_env else "",timeout_s=float(provider.get("timeout_s",900.0)))


def describe(plan:PipelinePlan)->list[str]:
    lines=[f"provider: {plan.doc['provider']['type']}","modules:"]
    for i,module in enumerate(plan.modules,1):
        lines.append(f"  {i:02d} {module.module_id}: {module.uses}")
        for name,source in module.inputs.items(): lines.append(f"       {name} <- {source}")
    lines.append("models:")
    for role in ROLES:
        row=plan.doc["models"][role]; lines.append(f"  {role}: {row['model']} max_tokens={row['max_tokens']} temperature={row.get('temperature',0.0)}")
    return lines


def compiled_markdown(plan: PipelinePlan) -> str:
    """Render the validated module graph with every contract file made explicit."""
    validate(plan)
    external={name:contract_registry.load(rule["contract"],base=plan.path.parent) for name,rule in (plan.doc.get("inputs") or {}).items()}
    produced: dict[tuple[str,str], Any]={}
    lines=[f"# Compiled pipeline — `{plan.pipeline_id}`","",plan.description,"","## External inputs",""]
    for name,contract in external.items():
        lines.extend([f"### `inputs.{name}`",f"- semantic type: `{contract.semantic_type}`",f"- contract: `{contract.path}`",""])
    lines.extend(["## Modules",""])
    for index,node in enumerate(plan.modules,1):
        spec=_module_spec(node.uses)
        lines.extend([f"### {index:02d}. `{node.module_id}` → `{node.uses}`",""])
        if node.inputs:
            lines.append("Inputs:")
            for input_name,source in node.inputs.items():
                expected=_spec_contract(spec,"inputs",input_name)
                if source.startswith("inputs."):
                    producer=external[source[len("inputs."):]]
                else:
                    upstream,out=source.split(".",1); producer=produced[(upstream,out)]
                lines.extend([
                    f"- `{input_name}` ← `{source}`",
                    f"  - upstream: `{producer.semantic_type}` — `{producer.path}`",
                    f"  - expected: `{expected.semantic_type}` — `{expected.path}`",
                    "  - compatibility: PASS",
                ])
        else:
            lines.append("Inputs: none")
        lines.append("")
        lines.append("Outputs:")
        for output_name in spec.outputs:
            contract=_spec_contract(spec,"outputs",output_name)
            produced[(node.module_id,output_name)]=contract
            lines.extend([
                f"- `{node.module_id}.{output_name}`",
                f"  - semantic type: `{contract.semantic_type}`",
                f"  - contract: `{contract.path}`",
            ])
        lines.append("")
    lines.extend(["## Model roles",""])
    for role in ROLES:
        row=plan.doc["models"][role]
        lines.append(f"- `{role}`: `{row['model']}`, max_tokens={row['max_tokens']}, temperature={row.get('temperature',0.0)}")
    lines.append("")
    return "\n".join(lines)
