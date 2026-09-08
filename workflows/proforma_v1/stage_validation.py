"""Validate a stage artifact using schema plus deterministic relational rules."""
from __future__ import annotations
import re
from scripts.core.validated_model_task import fail
from workflows.proforma_v1 import issues as iss
from workflows.proforma_v1 import rules as rule_registry
from workflows.proforma_v1 import schema_engine, stage_spec

def _path_key(issue):
    parts=[]
    for chunk in re.split(r'[.\[\]]+',issue.path or ''):
        if chunk: parts.append((0,int(chunk),'') if chunk.isdigit() else (1,0,chunk))
    return parts

def validate_spec(spec,text,context=None,*,structural=True):
    label=spec.label; doc,problems=iss.parse(text,fmt=spec.output_format,context=label)
    if problems: fail(label,problems)
    problems=[]
    if structural: problems += schema_engine.issues_from_schema(doc,schema_engine.load(spec.schema_name),context=label)
    problems += rule_registry.apply(spec,doc,context or {})
    fail(label,sorted(problems,key=_path_key)); return f'{label} valid'

def validate(stage,text,context=None):
    return validate_spec(stage_spec.load(stage),text,context,structural=True)
