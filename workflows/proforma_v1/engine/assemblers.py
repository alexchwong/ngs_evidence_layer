"""Small deterministic form-assembly registry with actionable failures."""
from __future__ import annotations
from copy import deepcopy
from typing import Any

class AssemblyError(ValueError): pass

def passthrough(model_output,*,spec,context): return deepcopy(model_output)

def object_merge(model_output,*,spec,context):
    base=deepcopy(context.get(spec.get('source',''),{})) if spec.get('source') else {}
    if not isinstance(base,dict) or not isinstance(model_output,dict):
        raise AssemblyError('The workflow expected mapping/object source data and a mapping/object model output for assembly. Return the requested top-level mapping; this is a representation requirement, not a clinical decision.')
    allowed=spec.get('model_fields')
    if allowed is None: incoming=model_output; unknown=set()
    else: incoming={k:model_output[k] for k in allowed if k in model_output}; unknown=set(model_output)-set(allowed)
    if unknown: raise AssemblyError(f'The model output contains workflow-owned field(s) {sorted(unknown)}. Remove only those fields; preserve model-owned fields and decisions.')
    base.update(deepcopy(incoming)); return base

def keyed_rows(model_output,*,spec,context):
    source=context.get(spec.get('source')); source_rows=list(source.values()) if isinstance(source,dict) else source if isinstance(source,list) else None
    if source_rows is None: raise AssemblyError('The workflow source for keyed-row assembly is missing or malformed. This is a workflow configuration/state error, not a model repair.')
    answers_path=spec.get('answers_path','answers'); answers=model_output.get(answers_path) if isinstance(model_output,dict) else None
    if not isinstance(answers,dict): raise AssemblyError(f'Return {answers_path!r} as a mapping keyed by the supplied IDs. Do not change answer content merely to repair the wrapper.')
    source_key=spec.get('source_key','id'); known={str(r[source_key]) for r in source_rows}; extra=sorted(set(map(str,answers))-known)
    if extra: raise AssemblyError(f'Answer ID(s) {extra} were not supplied. Remove only those unsupplied answers and preserve answers for valid IDs.')
    if not spec.get('allow_missing',False):
        missing=sorted(known-set(map(str,answers)))
        if missing: raise AssemblyError(f'Answer(s) are missing for supplied ID(s) {missing}. Add complete answers for those IDs and preserve existing valid answers.')
    deterministic=spec.get('deterministic_fields') or {}; model_field_spec=spec.get('model_fields'); model_fields=tuple(model_field_spec or ()); rows=[]
    for row in source_rows:
        key=str(row[source_key]); answer=answers.get(key,{})
        if not isinstance(answer,dict): raise AssemblyError(f'Answer {key!r} must be one mapping/object. Return the same intended answer fields inside a mapping.')
        unknown=sorted(set(answer)-set(model_fields)) if model_field_spec is not None else []
        if unknown: raise AssemblyError(f'Answer {key!r} contains field(s) the model does not own: {unknown}. Remove only those fields; preserve the intended answer.')
        built={dest:deepcopy(row[rule['from_row']]) for dest,rule in deterministic.items()}
        for field in model_fields:
            if field in answer: built[field]=deepcopy(answer[field])
        rows.append(built)
    return {spec.get('output_path','classification'):rows}

def list_rows(model_output,*,spec,context):
    if not isinstance(model_output,list): raise AssemblyError('Return the requested model output as a list. Preserve the intended item content while repairing the outer representation.')
    return deepcopy(model_output)

REGISTRY={'passthrough':passthrough,'object_merge':object_merge,'keyed_rows':keyed_rows,'list_rows':list_rows}
def assemble(name,model_output,*,spec=None,context=None):
    if name not in REGISTRY: raise AssemblyError(f'The workflow requested unknown assembler {name!r}. This is a workflow configuration error, not a model repair.')
    return REGISTRY[name](model_output,spec=spec or {},context=context or {})
