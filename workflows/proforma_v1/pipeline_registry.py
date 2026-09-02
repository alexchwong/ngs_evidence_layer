"""Small provider/model pipeline registry for proforma-v1; YAML filename stem is pipeline identity."""
from __future__ import annotations
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
import yaml
from workflows.proforma_v1.model_binding import Binding
HERE=Path(__file__).resolve().parent; ROOT=HERE/'pipelines'
ROLES=('structure','diagnosis','ptbg','evidence_match','evidence_audit','evidence_adjudication','report_write','preservation_check','syntax_repair')
REASONING_LEVELS=('default','none','minimal','low','medium','high','xhigh')
_PROVIDER_ROUTING_LIST_FIELDS=('order','only','ignore')
_PROVIDER_ROUTING_BOOL_FIELDS=('allow_fallbacks','require_parameters')
_PROVIDER_ROUTING_FIELDS=set(_PROVIDER_ROUTING_LIST_FIELDS+_PROVIDER_ROUTING_BOOL_FIELDS)
_EXECUTION_FIELDS={'max_parallel_cases'}
def configure(root:Path|str|None=None):
    global ROOT
    ROOT=Path(root).expanduser().resolve() if root is not None else HERE/'pipelines'
    return ROOT
@dataclass(frozen=True)
class PipelinePlan:
    pipeline_id:str; description:str; path:Path; doc:dict[str,Any]
def _validate_role_rows(rows:Any,label:str)->None:
    if not isinstance(rows,dict) or set(rows)!=set(ROLES): raise ValueError(f'{label} must map exactly {list(ROLES)}')
    for role,row in rows.items():
        if not isinstance(row,dict) or not isinstance(row.get('model'),str) or not row['model'].strip(): raise ValueError(f'{label}.{role}.model must be non-empty')
        if not isinstance(row.get('max_tokens'),int) or isinstance(row.get('max_tokens'),bool) or row['max_tokens']<=0: raise ValueError(f'{label}.{role}.max_tokens must be positive')
        reasoning=row.get('reasoning','default')
        if not isinstance(reasoning,str) or reasoning not in REASONING_LEVELS: raise ValueError(f'{label}.{role}.reasoning must be one of {list(REASONING_LEVELS)}')
def _validate_provider_routing(value:Any,label:str)->None:
    if not isinstance(value,dict): raise ValueError(f'{label} must be a mapping')
    unknown=set(value)-_PROVIDER_ROUTING_FIELDS
    if unknown: raise ValueError(f'{label} has unsupported field(s): {", ".join(sorted(unknown))}')
    for field in _PROVIDER_ROUTING_LIST_FIELDS:
        if field not in value: continue
        items=value[field]
        if not isinstance(items,list) or not items or any(not isinstance(item,str) or not item.strip() for item in items): raise ValueError(f'{label}.{field} must be a non-empty list of strings')
    for field in _PROVIDER_ROUTING_BOOL_FIELDS:
        if field in value and not isinstance(value[field],bool): raise ValueError(f'{label}.{field} must be boolean')
def _validate_execution(value:Any)->None:
    if value is None: return
    if not isinstance(value,dict): raise ValueError('execution must be a mapping')
    unknown=set(value)-_EXECUTION_FIELDS
    if unknown: raise ValueError(f'execution has unsupported field(s): {", ".join(sorted(unknown))}')
    if 'max_parallel_cases' in value:
        limit=value['max_parallel_cases']
        if not isinstance(limit,int) or isinstance(limit,bool) or limit<=0:
            raise ValueError('execution.max_parallel_cases must be a positive integer')
def _validate_aliases(doc:dict[str,Any])->None:
    aliases=doc.get('model_aliases'); roles=doc.get('model_roles')
    if not isinstance(aliases,dict) or not aliases: raise ValueError('model_aliases must be a non-empty mapping')
    for alias,value in aliases.items():
        if not isinstance(alias,str) or not alias.strip(): raise ValueError('model_aliases keys must be non-empty strings')
        label=f'model_aliases.{alias}'
        if isinstance(value,str):
            if not value.strip(): raise ValueError(f'{label} must be a non-empty model id')
            continue
        if not isinstance(value,dict): raise ValueError(f'{label} must be a model id string or mapping')
        unknown=set(value)-{'model','provider'}
        if unknown: raise ValueError(f'{label} has unsupported field(s): {", ".join(sorted(unknown))}')
        if not isinstance(value.get('model'),str) or not value['model'].strip(): raise ValueError(f'{label}.model must be non-empty')
        if 'provider' in value: _validate_provider_routing(value['provider'],f'{label}.provider')
    _validate_role_rows(roles,'model_roles')
    for role,row in roles.items():
        alias=row['model']
        if alias not in aliases: raise ValueError(f'model_roles.{role}.model references unknown alias {alias!r}')
def load_yaml(path:Path)->PipelinePlan:
    path=Path(path); doc=yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(doc,dict) or not isinstance(doc.get('pipeline'),dict): raise ValueError(f'invalid pipeline YAML: {path}')
    meta=doc['pipeline']
    if 'id' in meta: raise ValueError(f'pipeline.id is obsolete; rename the YAML file instead: {path}')
    if meta.get('version')!=1: raise ValueError('pipeline.version must be 1')
    _validate_execution(doc.get('execution'))
    provider=doc.get('provider'); models=doc.get('models')
    if not isinstance(provider,dict) or provider.get('type') not in {'self','openai-compatible'}: raise ValueError('provider.type must be self or openai-compatible')
    if provider['type']=='self':
        _validate_role_rows(models,'pipeline.models')
    elif 'model_aliases' in doc or 'model_roles' in doc:
        if models is not None: raise ValueError('non-self pipeline must use either legacy models or model_aliases/model_roles, not both')
        _validate_aliases(doc)
    else:
        _validate_role_rows(models,'pipeline.models')
    return PipelinePlan(path.stem,str(meta.get('description') or ''),path,doc)
def _paths():
    # Discovery is filename-only. Validation belongs to load(name), so an
    # unrelated invalid/custom YAML cannot block a selected pipeline.
    return {p.stem:p for p in sorted(ROOT.glob('*.yaml'))}
def names(): return tuple(_paths())
def load(name:str):
    paths=_paths()
    if name not in paths: raise ValueError(f'unknown proforma-v1 pipeline {name!r}; choose one of: {", ".join(paths)}')
    return load_yaml(paths[name])
def descriptions(): return {n:load(n).description for n in names()}
def _resolved_row(plan:PipelinePlan,role:str)->tuple[dict[str,Any],dict[str,Any]|None]:
    if 'model_roles' not in plan.doc: return plan.doc['models'][role],None
    row=plan.doc['model_roles'][role]; alias=row['model']; entry=plan.doc['model_aliases'][alias]
    if isinstance(entry,str): model=entry; routing=None
    else: model=entry['model']; routing=entry.get('provider')
    resolved=dict(row); resolved['model']=model
    return resolved,dict(routing) if routing is not None else None
def binding(plan:PipelinePlan,role:str)->Binding:
    if role not in ROLES: raise ValueError(f'unknown model role {role!r}')
    provider=plan.doc['provider']; row,provider_routing=_resolved_row(plan,role); kind=provider['type']
    reasoning=str(row.get('reasoning','default'))
    if kind=='self': return Binding(pipeline=plan.pipeline_id,role=role,kind='self',model='self',temperature=float(row.get('temperature',0)),max_tokens=int(row['max_tokens']),reasoning=reasoning)
    base=str(provider.get('base_url') or ''); env=str(provider.get('base_url_env') or '')
    if env and os.environ.get(env,'').strip(): base=os.environ[env].strip()
    if not base: raise ValueError(f'pipeline {plan.pipeline_id!r} has no provider base_url')
    api_env=str(provider.get('api_key_env') or '')
    return Binding(pipeline=plan.pipeline_id,role=role,kind='openai-compatible',model=str(row['model']),temperature=float(row.get('temperature',0)),max_tokens=int(row['max_tokens']),base_url=base.rstrip('/'),base_url_env=env,api_key_env=api_env,api_key=os.environ.get(api_env,'') if api_env else '',timeout_s=float(provider.get('timeout_s',900)),provider_routing=provider_routing,reasoning=reasoning)
def describe(plan):
    lines=[f'provider: {plan.doc["provider"]["type"]}','models:']
    for role in ROLES:
        row,routing=_resolved_row(plan,role)
        suffix=f' provider={routing}' if routing else ''
        lines.append(f'  {role}: {row["model"]} max_tokens={row["max_tokens"]} temperature={row.get("temperature",0)} reasoning={row.get("reasoning","default")}{suffix}')
    return lines
