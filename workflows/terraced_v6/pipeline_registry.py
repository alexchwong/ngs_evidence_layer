"""Small provider/model pipeline registry for terraced-v6; YAML filename stem is pipeline identity."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from workflows.terraced_v6.model_binding import Binding
HERE=Path(__file__).resolve().parent; ROOT=HERE/'pipelines'
ROLES=('structure','diagnosis','ptbg','evidence_match','evidence_audit','report_write','preservation_check','syntax_repair')
def configure(root:Path|str|None=None):
    global ROOT
    ROOT=Path(root).expanduser().resolve() if root is not None else HERE/'pipelines'
    return ROOT
@dataclass(frozen=True)
class PipelinePlan:
    pipeline_id:str; description:str; path:Path; doc:dict[str,Any]
def load_yaml(path:Path)->PipelinePlan:
    path=Path(path); doc=yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(doc,dict) or not isinstance(doc.get('pipeline'),dict): raise ValueError(f'invalid pipeline YAML: {path}')
    meta=doc['pipeline']
    if 'id' in meta: raise ValueError(f'pipeline.id is obsolete; rename the YAML file instead: {path}')
    if meta.get('version')!=1: raise ValueError('pipeline.version must be 1')
    provider=doc.get('provider'); models=doc.get('models')
    if not isinstance(provider,dict) or provider.get('type') not in {'self','openai-compatible'}: raise ValueError('provider.type must be self or openai-compatible')
    if not isinstance(models,dict) or set(models)!=set(ROLES): raise ValueError(f'pipeline.models must map exactly {list(ROLES)}')
    for role,row in models.items():
        if not isinstance(row,dict) or not isinstance(row.get('model'),str) or not row['model']: raise ValueError(f'pipeline.models.{role}.model must be non-empty')
        if not isinstance(row.get('max_tokens'),int) or row['max_tokens']<=0: raise ValueError(f'pipeline.models.{role}.max_tokens must be positive')
    return PipelinePlan(path.stem,str(meta.get('description') or ''),path,doc)
def _paths():
    out={}
    for p in sorted(ROOT.glob('*.yaml')):
        plan=load_yaml(p); out[plan.pipeline_id]=p
    return out
def names(): return tuple(_paths())
def load(name:str):
    paths=_paths()
    if name not in paths: raise ValueError(f'unknown terraced-v6 pipeline {name!r}; choose one of: {", ".join(paths)}')
    return load_yaml(paths[name])
def descriptions(): return {n:load(n).description for n in names()}
def binding(plan:PipelinePlan,role:str)->Binding:
    if role not in ROLES: raise ValueError(f'unknown model role {role!r}')
    provider=plan.doc['provider']; row=plan.doc['models'][role]; kind=provider['type']
    if kind=='self': return Binding(pipeline=plan.pipeline_id,role=role,kind='self',model='self',temperature=float(row.get('temperature',0)),max_tokens=int(row['max_tokens']))
    base=str(provider.get('base_url') or ''); env=str(provider.get('base_url_env') or '')
    if env and os.environ.get(env,'').strip(): base=os.environ[env].strip()
    if not base: raise ValueError(f'pipeline {plan.pipeline_id!r} has no provider base_url')
    api_env=str(provider.get('api_key_env') or '')
    return Binding(pipeline=plan.pipeline_id,role=role,kind='openai-compatible',model=str(row['model']),temperature=float(row.get('temperature',0)),max_tokens=int(row['max_tokens']),base_url=base.rstrip('/'),base_url_env=env,api_key_env=api_env,api_key=os.environ.get(api_env,'') if api_env else '',timeout_s=float(provider.get('timeout_s',900)))
def describe(plan):
    lines=[f'provider: {plan.doc["provider"]["type"]}','models:']
    for role in ROLES:
        row=plan.doc['models'][role]; lines.append(f'  {role}: {row["model"]} max_tokens={row["max_tokens"]} temperature={row.get("temperature",0)}')
    return lines
