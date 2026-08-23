"""Small provider/model pipeline registry for terraced-v4."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from workflows.terraced_v4.model_binding import Binding

HERE=Path(__file__).resolve().parent
ROOT=HERE/'pipelines'
ROLES=(
    'structure','diagnosis','ptbg','evidence_match','evidence_audit',
    'reportable_sentences','summarization','paraphrasing',
    'semantic_preservation_check','syntax_repair',
)
@dataclass(frozen=True)
class PipelinePlan:
    pipeline_id:str; description:str; path:Path; doc:dict[str,Any]

def load_yaml(path:Path)->PipelinePlan:
    doc=yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(doc,dict) or not isinstance(doc.get('pipeline'),dict): raise ValueError(f'invalid pipeline YAML: {path}')
    meta=doc['pipeline']; pid=meta.get('id')
    if not isinstance(pid,str) or not pid: raise ValueError('pipeline.id must be non-empty')
    if meta.get('version')!=1: raise ValueError(f'unsupported terraced-v4 pipeline version {meta.get("version")!r}; expected 1')
    provider=doc.get('provider')
    if not isinstance(provider,dict) or provider.get('type') not in {'self','openai-compatible'}: raise ValueError('provider.type must be self or openai-compatible')
    models=doc.get('models')
    if not isinstance(models,dict) or set(models)!=set(ROLES): raise ValueError(f'pipeline.models must map exactly {list(ROLES)}')
    for role,row in models.items():
        if not isinstance(row,dict) or not isinstance(row.get('model'),str) or not row['model']: raise ValueError(f'pipeline.models.{role}.model must be non-empty')
        if not isinstance(row.get('max_tokens'),int) or row['max_tokens']<=0: raise ValueError(f'pipeline.models.{role}.max_tokens must be positive')
    return PipelinePlan(pid,str(meta.get('description') or ''),path,doc)

def _paths():
    out={}
    for p in sorted(ROOT.glob('*.yaml')):
        plan=load_yaml(p)
        if plan.pipeline_id in out: raise ValueError(f'duplicate pipeline id {plan.pipeline_id!r}')
        out[plan.pipeline_id]=p
    return out

def names(): return tuple(_paths())
def load(name:str):
    paths=_paths()
    if name not in paths: raise ValueError(f'unknown terraced-v4 pipeline {name!r}; choose one of: {", ".join(paths)}')
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
