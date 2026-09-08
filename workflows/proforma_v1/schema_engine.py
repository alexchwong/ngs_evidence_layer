"""Translate JSON-Schema failures into task-level plain-English repair feedback."""
from __future__ import annotations
import json
from functools import lru_cache
from pathlib import Path
from jsonschema import Draft202012Validator
from scripts.core.validated_model_task import ValidationIssue
from workflows.proforma_v1 import issues as iss

SCHEMA_ROOT=Path(__file__).resolve().parent/'schemas'

@lru_cache(maxsize=None)
def load(name:str)->dict:
    path=name if Path(name).is_absolute() else SCHEMA_ROOT/Path(name).name
    with open(path,encoding='utf-8') as f:schema=json.load(f)
    Draft202012Validator.check_schema(schema); return schema

def json_path(parts):
    out=''
    for p in parts: out += f'[{p}]' if isinstance(p,int) else (f'.{p}' if out else str(p))
    return out

def _issue(path,problem,fix,*,repair_class='content',received=None,expected=None):
    return ValidationIssue(path,problem.rstrip('. '),fix.rstrip('. ')+'. Preserve unrelated fields and decisions.',repair_class=repair_class,received=received,expected=expected)

def _required_issue(err,path):
    required=list(err.validator_value or [])
    missing=[k for k in required if isinstance(err.instance,dict) and k not in err.instance]
    return [_issue(path,f'This object is missing required field(s) {missing or required}',f'Add the missing required field(s) {missing or required} using the values required by the task; do not remove fields that are already valid',received=iss.preview(err.instance),expected=f'required fields: {required}')]

def _type_issue(err,path):
    wanted=err.validator_value; choices=[wanted] if isinstance(wanted,str) else list(wanted)
    if choices==['string']: return iss.text_field(err.instance,path)
    if choices==['boolean']: return iss.bool_field(err.instance,path)
    if 'array' in choices and not isinstance(err.instance,(list,type(None))):
        return [_issue(path,f'This field must be a list, but you returned {iss.type_name(err.instance)}','Return the same intended item(s) inside a YAML/JSON list; do not change their meaning',repair_class='serialization',received=iss.preview(err.instance),expected='list/array')]
    if 'object' in choices and isinstance(err.instance,list) and len(err.instance)==1 and isinstance(err.instance[0],dict):
        return [_issue(path,'This field must be one mapping/object, but it has an extra one-item list wrapper','Remove only the outer list wrapper and keep the contained fields/values unchanged',repair_class='serialization',received=iss.preview(err.instance),expected='mapping/object')]
    if 'null' in choices:
        readable=' or '.join('mapping/object' if x=='object' else 'list' if x=='array' else x for x in choices)
        return [_issue(path,f'This field must use one of the allowed forms: {readable}; the current {iss.type_name(err.instance)} value does not match them',f'Return either literal null or the complete non-null form required by this field; do not use a partially empty object as a substitute for null',received=iss.preview(err.instance),expected=readable)]
    readable=' or '.join(choices)
    return [_issue(path,f'This field has the wrong representation: expected {readable}, received {iss.type_name(err.instance)}',f'Return the value using the required {readable} representation',received=iss.preview(err.instance),expected=readable)]

def _combinator_issue(err,path):
    branches=[]
    for sub in err.validator_value or []:
        if sub.get('type')=='null': branches.append('literal null')
        elif '$ref' in sub: branches.append(str(sub['$ref']).rsplit('/',1)[-1])
        elif sub.get('type')=='object': branches.append('the complete worksheet object')
        else: branches.append(str(sub.get('type','allowed form')))
    forms=' or '.join(branches) or 'one of the allowed forms'
    return [_issue(path,f'The current value does not match any permitted form for this field',f'Return {forms}. If the task says this field is not applicable, use literal null rather than an object containing only null members',received=iss.preview(err.instance),expected=forms)]

def issues_from_schema(doc,schema,*,context):
    out=[]; seen=set(); validator=Draft202012Validator(schema)
    for err in sorted(validator.iter_errors(doc),key=lambda e:(list(map(str,e.absolute_path)),e.validator)):
        path=json_path(err.absolute_path) or context; key=(path,err.validator)
        if key in seen: continue
        seen.add(key); kind=err.validator
        if kind=='required': out += _required_issue(err,path)
        elif kind=='additionalProperties':
            allowed=sorted((err.schema.get('properties') or {}).keys()); extra=sorted(set(err.instance)-set(allowed)) if isinstance(err.instance,dict) else []
            out += [_issue(path,f'This object contains field(s) that are not part of the output contract: {extra}',f'Remove only these unexpected field(s): {extra}',received=iss.preview(err.instance),expected=f'allowed fields: {allowed}')]
        elif kind=='enum': out += iss.enum_field(err.instance,err.validator_value,path,label='value')
        elif kind=='type': out += _type_issue(err,path)
        elif kind in {'oneOf','anyOf'}: out += _combinator_issue(err,path)
        elif kind=='minItems': out += [_issue(path,f'This list has too few items: received {len(err.instance or [])}, minimum is {err.validator_value}',f'Add the required missing item(s) so the list has at least {err.validator_value}; do not duplicate existing rows to satisfy the count',received=iss.preview(err.instance))]
        elif kind in {'minLength','pattern'}: out += iss.text_field(err.instance,path)
        else: out += [_issue(path,f'This field violates the declared {kind} requirement',f'Correct this field to satisfy the output contract described in the task; do not change unrelated clinical/evidence content',received=iss.preview(err.instance),expected=iss.preview(err.validator_value))]
    return out
