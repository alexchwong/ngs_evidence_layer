"""Generic parse/schema/check/assembly validation with actionable feedback."""
from __future__ import annotations
import json
from pathlib import Path
from typing import Any
import yaml
from jsonschema import Draft202012Validator
from workflows.proforma_v1.engine import assemblers, checks

class StructuredValidationError(ValueError): pass
class _UniqueKeyLoader(yaml.SafeLoader): pass

def _construct_mapping(loader,node,deep=False):
    mapping={}
    for key_node,value_node in node.value:
        key=loader.construct_object(key_node,deep=deep)
        if key in mapping:
            line=key_node.start_mark.line+1
            raise StructuredValidationError(f"Duplicate YAML field {key!r} at line {line}. Keep one intended value for this field and remove the duplicate; if the two values disagree, reassess rather than letting Python choose.")
        mapping[key]=loader.construct_object(value_node,deep=deep)
    return mapping
_UniqueKeyLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,_construct_mapping)

def parse(raw,fmt):
    try:
        if fmt=='json': return json.loads(raw)
        if fmt=='yaml': return yaml.load(raw,Loader=_UniqueKeyLoader)
        if fmt=='text': return raw
    except StructuredValidationError: raise
    except (json.JSONDecodeError,yaml.YAMLError) as exc:
        raise StructuredValidationError(f"The returned {fmt.upper()} cannot be parsed: {exc}. Return one complete, well-formed {fmt.upper()} artifact with the same intended content and no commentary.") from exc
    raise StructuredValidationError(f"The workflow requested unsupported structured-output format {fmt!r}. This is a workflow configuration error, not a model repair.")

def load_schema(path):
    try:
        doc=json.loads(Path(path).read_text(encoding='utf-8')); Draft202012Validator.check_schema(doc); return doc
    except Exception as exc:
        raise StructuredValidationError(f"Workflow schema {path} could not be loaded or is invalid: {exc}. This is a workflow configuration error, not a model repair.") from exc

def _path(parts):
    out=''
    for p in parts: out += f'[{p}]' if isinstance(p,int) else (f'.{p}' if out else str(p))
    return out or '<root>'

def _plain(err,label):
    where=_path(err.absolute_path); kind=err.validator; value=err.instance
    if kind=='required':
        required=list(err.validator_value or []); missing=[x for x in required if isinstance(value,dict) and x not in value]
        return f"{label} field {where}: missing required field(s) {missing or required}. Add those field(s) with the task-required values and preserve fields that are already valid."
    if kind=='additionalProperties':
        allowed=set((err.schema.get('properties') or {}).keys()); extra=sorted(set(value)-allowed) if isinstance(value,dict) else []
        return f"{label} field {where}: unexpected field(s) {extra}. Remove only those fields; preserve allowed fields and their values."
    if kind=='enum':
        allowed=list(err.validator_value or [])
        return f"{label} field {where}: {value!r} is not an allowed value. Choose exactly one of {allowed}; do not change unrelated decisions."
    if kind=='type':
        wanted=err.validator_value if isinstance(err.validator_value,str) else ' or '.join(err.validator_value)
        return f"{label} field {where}: expected {wanted}, but received {type(value).__name__}. Return this field using the required representation without changing its intended meaning."
    if kind in {'oneOf','anyOf'}:
        branches=[]
        for sub in err.validator_value or []:
            if sub.get('type')=='null': branches.append('literal null')
            elif '$ref' in sub: branches.append(str(sub['$ref']).rsplit('/',1)[-1])
            else: branches.append(str(sub.get('type','allowed form')))
        return f"{label} field {where}: the current value does not match any allowed form. Return {' or '.join(branches)}. If the field is not applicable, use literal null rather than a partially empty object. Preserve unrelated content."
    if kind=='minItems':
        return f"{label} field {where}: this list needs at least {err.validator_value} item(s). Add the missing required item(s); do not duplicate existing items merely to satisfy the count."
    return f"{label} field {where}: this value violates the declared {kind} requirement. Correct this field according to the output contract in the task and preserve unrelated content."

def validate_doc(doc,schema,*,label='artifact'):
    errors=sorted(Draft202012Validator(schema).iter_errors(doc),key=lambda e:list(map(str,e.absolute_path)))
    if errors:
        messages=[]
        for err in errors[:8]: messages.append(_plain(err,label))
        if len(errors)>8: messages.append(f"{len(errors)-8} additional issue(s) were omitted; apply the same corrections throughout the artifact.")
        raise StructuredValidationError('\n'.join(messages))
    return doc

def validate(raw,*,fmt,schema=None,check_specs=(),context=None,assembly=None,final_schema=None):
    doc=parse(raw,fmt)
    if schema is not None: validate_doc(doc,schema,label='Model output')
    checks.apply(doc,check_specs,context=context or {})
    if assembly:
        name=assembly.get('type','passthrough')
        try: doc=assemblers.assemble(name,doc,spec=assembly,context=context or {})
        except assemblers.AssemblyError as exc: raise StructuredValidationError(str(exc)) from exc
    if final_schema is not None: validate_doc(doc,final_schema,label='Assembled artifact')
    return doc
