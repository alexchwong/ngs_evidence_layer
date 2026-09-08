"""Generic deterministic checks with plain-English model-facing failures."""
from __future__ import annotations
from typing import Any, Callable

class CheckFailure(ValueError):
    def __init__(self,rule,path,problem,required_action=None):
        self.rule=rule; self.path=path; self.problem=problem; self.required_action=required_action or 'Correct this field while preserving unrelated fields and decisions.'
        super().__init__(f"{path}: {problem}. Required action: {self.required_action}")

def _path(value,path):
    cur=value
    if not path:return cur
    for part in path.split('.'):
        if part.endswith('[]'):
            key=part[:-2]; cur=cur.get(key,[]) if isinstance(cur,dict) else []; continue
        if isinstance(cur,dict): cur=cur.get(part)
        else:return None
    return cur

def _source(context,ref):
    if ref in context:return context[ref]
    cur=context
    for part in ref.split('.'):
        if isinstance(cur,dict) and part in cur:cur=cur[part]
        else:return None
    return cur

def _values(doc,path):
    if '[]' not in path:
        v=_path(doc,path); return v if isinstance(v,list) else [v]
    left,right=path.split('[]',1); rows=_path(doc,left.rstrip('.')) or []; suffix=right.lstrip('.')
    return [_path(r,suffix) if suffix else r for r in rows]

def equals(doc,context,spec):
    path=spec.get('path',''); actual=_path(doc,path); expected=spec.get('value')
    if actual!=expected: raise CheckFailure('equals',path,f'This field must be exactly {expected!r}, but you returned {actual!r}',f'Return exactly {expected!r} in this field; do not change unrelated content')

def equals_source(doc,context,spec):
    path=spec.get('path',''); actual=_path(doc,path); expected=_source(context,spec['source'])
    if actual!=expected: raise CheckFailure('equals_source',path,f'This field is supplied by the workflow and must match {spec["source"]!r}; current value is {actual!r}',f'Return exactly the supplied value {expected!r}; this is not a model decision')

def subset(doc,context,spec):
    path=spec.get('path',''); actual=set(_values(doc,path) if '[]' in path else (_path(doc,path) or [])); allowed=set(_source(context,spec['source']) or []); unknown=actual-allowed
    if unknown: raise CheckFailure('subset',path,f'This field contains value(s) that were not supplied: {sorted(map(str,unknown))}',f'Remove only the unsupplied value(s) and use values from the supplied {spec["source"]!r} set')

def member_of(doc,context,spec):
    path=spec.get('path',''); actual=_path(doc,path); allowed=set(_source(context,spec['source']) or [])
    if actual not in allowed: raise CheckFailure('member_of',path,f'{actual!r} was not one of the supplied allowed values',f'Choose one exact value from the supplied {spec["source"]!r} set')

def unique(doc,context,spec):
    path=spec.get('path',''); values=_values(doc,path); seen=set(); dup=[]
    for v in values:
        marker=repr(v)
        if marker in seen:dup.append(v)
        seen.add(marker)
    if dup: raise CheckFailure('unique',path,f'The same value is repeated: {dup}',f'Return each value once. If duplicate rows differ in meaning, reassess them rather than letting Python choose')

def sequential_ids(doc,context,spec):
    path=spec.get('path',''); rows=_path(doc,path) or []; field=spec.get('field','id'); prefix=spec.get('prefix',''); width=spec.get('width')
    if width is None: expected=[f'{prefix}{i}' for i in range(1,len(rows)+1)]
    else:
        width=int(width)
        if width<0: raise CheckFailure('sequential_ids',path,'The workflow configuration has an invalid negative ID width','This is a workflow configuration error, not a model repair')
        expected=[f'{prefix}{i:0{width}d}' for i in range(1,len(rows)+1)]
    actual=[r.get(field) if isinstance(r,dict) else None for r in rows]
    if actual!=expected: raise CheckFailure('sequential_ids',path,f'Row IDs must be sequential {expected}, but you returned {actual}',f'Use exactly these IDs in this order: {expected}; keep the row content attached to its intended row')

def one_row_per(doc,context,spec):
    path=spec.get('path',''); rows=_path(doc,path) or []; key=spec.get('key','id'); actual=[r.get(key) if isinstance(r,dict) else None for r in rows]; expected=list(_source(context,spec['source']) or [])
    if actual!=expected:
        missing=[x for x in expected if x not in actual]; extra=[x for x in actual if x not in expected]; dup=sorted({x for x in actual if x is not None and actual.count(x)>1})
        parts=[]
        if missing:parts.append(f'missing {missing}')
        if extra:parts.append(f'unexpected {extra}')
        if dup:parts.append(f'duplicated {dup}')
        if not parts:parts.append('rows are in the wrong order')
        raise CheckFailure('one_row_per',path,'; '.join(parts),f'Return exactly one row for each supplied key in this order: {expected}. Preserve valid unrelated row content')


def rows_match_source_keys(doc,context,spec):
    path=spec.get('path',''); rows=_path(doc,path); source=_source(context,spec['source']); fields=list(spec.get('fields') or [])
    if not fields: raise CheckFailure('rows_match_source_keys',path,'The workflow check is missing its key-field definition','This is a workflow configuration error, not a model repair')
    if not isinstance(rows,list): raise CheckFailure('rows_match_source_keys',path,f'This output must be a list with one row for every supplied {fields} identity',f'Return a list with exactly one row per supplied dispute identity and preserve the decisions already made inside valid rows')
    if not isinstance(source,list): raise CheckFailure('rows_match_source_keys',path,f'The workflow source {spec["source"]!r} is unavailable','This is a workflow-state error, not something the model should repair')
    def keys(values): return [tuple(row.get(field) for field in fields) if isinstance(row,dict) else None for row in values]
    actual=keys(rows); expected=keys(source)
    if actual!=expected:
        missing=[x for x in expected if x not in actual]; extra=[x for x in actual if x not in expected]; dup=sorted({x for x in actual if x is not None and actual.count(x)>1},key=repr); parts=[]
        if missing: parts.append(f'missing {missing}')
        if extra: parts.append(f'unexpected {extra}')
        if dup: parts.append(f'duplicated {dup}')
        if not parts: parts.append('rows are in a different order from the supplied disputes')
        raise CheckFailure('rows_match_source_keys',path,'; '.join(parts),f'Adjudicate every supplied dispute exactly once and in this order: {expected}. Preserve the adjudication decisions in rows whose identity is already correct')

def _when(row,when):
    value=_path(row,when.get('path',''))
    if 'equals' in when:return value==when['equals']
    if 'in' in when:return value in when['in']
    if 'not_in' in when:return value not in when['not_in']
    return bool(value)

def required_when(doc,context,spec):
    path=spec.get('path','')
    if '[].' in path:
        rows_path,field=path.split('[].',1)
        for i,row in enumerate(_path(doc,rows_path) or []):
            if isinstance(row,dict) and _when(row,spec.get('when') or {}) and row.get(field) in (None,''):
                raise CheckFailure('required_when',f'{rows_path}[{i}].{field}','This field is required because the condition in the task is met',f'Provide the required value for {field}; keep the triggering decision and unrelated fields unchanged unless you conclude that triggering decision itself was wrong')
    elif _when(doc,spec.get('when') or {}) and _path(doc,path) in (None,''):
        raise CheckFailure('required_when',path,'This field is required because the condition in the task is met',f'Provide the required value for {path}; preserve unrelated content')

def null_when(doc,context,spec):
    path=spec.get('path','')
    if '[].' in path:
        rows_path,field=path.split('[].',1)
        for i,row in enumerate(_path(doc,rows_path) or []):
            if isinstance(row,dict) and _when(row,spec.get('when') or {}) and row.get(field) is not None:
                raise CheckFailure('null_when',f'{rows_path}[{i}].{field}','This field must be literal null under the condition you selected',f'Set only {field} to literal null if the triggering decision is intended. If the non-null content is substantive, reassess the triggering decision instead; Python will not choose between them')
    elif _when(doc,spec.get('when') or {}) and _path(doc,path) is not None:
        raise CheckFailure('null_when',path,'This field must be literal null under the selected condition',f'Set {path} to literal null if the triggering decision is intended; otherwise reassess the triggering decision')

def ordered_by_source(doc,context,spec):
    path=spec.get('path',''); actual=_values(doc,path); expected=list(_source(context,spec['source']) or [])
    if actual!=expected: raise CheckFailure('ordered_by_source',path,f'All required identities must appear in supplied order {expected}, but you returned {actual}',f'Reorder only; do not change the values or their associated content')

def field_matches_source(doc,context,spec):
    rows=_path(doc,spec.get('rows','')) or []; source=_source(context,spec['source']) or []; source_rows=list(source.values()) if isinstance(source,dict) else list(source); source_map={str(r[spec['source_key']]):r for r in source_rows}
    for i,row in enumerate(rows):
        key=str(row.get(spec['row_key']))
        if key not in source_map: raise CheckFailure('field_matches_source',f"{spec.get('rows')}[{i}].{spec.get('row_key')}",f'{key!r} was not a supplied source identity',f'Use the exact supplied identity; do not invent or substitute an ID')
        expected=_path(source_map[key],spec['source_path']); actual=_path(row,spec.get('path',''))
        if actual!=expected: raise CheckFailure('field_matches_source',f"{spec.get('rows')}[{i}].{spec.get('path')}",f'This source-owned field must be {expected!r}, but you returned {actual!r}',f'Return exactly the supplied value {expected!r}; this field is not a clinical/model decision')

CUSTOM_REGISTRY={}
def register_custom(name,fn):
    if not name or not callable(fn): raise ValueError('custom check registration requires a name and callable')
    CUSTOM_REGISTRY[name]=fn

def custom(doc,context,spec):
    handler=spec.get('handler'); fn=CUSTOM_REGISTRY.get(handler)
    if fn is None: raise CheckFailure('custom',spec.get('path','<workflow>'),f'The workflow references unknown deterministic check handler {handler!r}','This is a workflow configuration error, not a model repair')
    result=fn(doc,context,spec.get('params') or {})
    if result: raise CheckFailure('custom',spec.get('path','<workflow>'),str(result),'Correct the stated deterministic inconsistency while preserving unrelated fields and decisions')

REGISTRY={'custom':custom,'equals':equals,'equals_source':equals_source,'subset':subset,'member_of':member_of,'unique':unique,'sequential_ids':sequential_ids,'one_row_per':one_row_per,'rows_match_source_keys':rows_match_source_keys,'required_when':required_when,'null_when':null_when,'ordered_by_source':ordered_by_source,'field_matches_source':field_matches_source}
from workflows.proforma_v1 import rules as _stage_rules
for _name in _stage_rules.REGISTRY: REGISTRY.setdefault(_name,None)

def apply(doc,checks,*,context=None):
    context=context or {}
    for spec in checks or ():
        name=spec.get('rule'); fn=REGISTRY.get(name)
        if name not in REGISTRY: raise CheckFailure(str(name),spec.get('path','<workflow>'),'The workflow declares an unknown deterministic check','This is a workflow configuration error, not something the model should repair')
        if fn is not None: fn(doc,context,spec)
    return doc
