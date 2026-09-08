"""Reusable plain-English deterministic validation issues for proforma-v1."""
from __future__ import annotations
import difflib, json, yaml
from scripts.core.validated_model_task import ValidationIssue

MAX_LISTED_ENUM_VALUES=12
NEAREST_MATCHES=5

def type_name(v):
    if v is None: return 'null'
    if isinstance(v,bool): return 'boolean'
    if isinstance(v,dict): return 'mapping'
    if isinstance(v,list): return 'list'
    if isinstance(v,str): return 'string'
    if isinstance(v,int): return 'integer'
    if isinstance(v,float): return 'number'
    return type(v).__name__

def preview(v,limit=160):
    text=v if isinstance(v,str) else repr(v); text=' '.join(str(text).split())
    return text if len(text)<=limit else text[:limit-3]+'...'

def _issue(path,problem,fix,*,repair_class='content',received=None,expected=None,preserve='Preserve unrelated fields and decisions.'):
    action=fix.rstrip('. ')
    if preserve: action += '. ' + preserve.rstrip('. ')
    return ValidationIssue(path,problem.rstrip('. '),action,repair_class=repair_class,received=received,expected=expected)

def parse(text,*,fmt,context):
    try: doc=yaml.safe_load(text) if fmt=='yaml' else json.loads(text)
    except (yaml.YAMLError,json.JSONDecodeError) as exc:
        return {},[_issue(context,f'The returned {fmt.upper()} cannot be parsed: {preview(exc)}',f'Return one complete, well-formed {fmt.upper()} document and no commentary',repair_class='serialization',preserve='Do not change the intended clinical or evidence content while repairing serialization.')]
    if not isinstance(doc,dict):
        wrapped=isinstance(doc,list) and len(doc)==1 and isinstance(doc[0],dict)
        return {},[_issue(context,f'The top-level artifact must be a mapping/object, but you returned a {type_name(doc)}','Remove the single outer list wrapper and return the contained mapping unchanged' if wrapped else 'Return the complete artifact as one top-level mapping/object',repair_class='serialization' if wrapped else 'content',received=preview(doc),expected='top-level mapping/object')]
    return doc,[]

def exact_keys(doc,expected,path):
    if not isinstance(doc,dict): return [_issue(path,f'This section must be a mapping/object, not {type_name(doc)}',f'Return a mapping with exactly these fields: {sorted(expected)}',received=preview(doc))]
    missing=sorted(set(expected)-set(doc)); extra=sorted(set(doc)-set(expected))
    if not missing and not extra:return []
    parts=[]
    if missing:parts.append(f'missing required field(s) {missing}')
    if extra:parts.append(f'contains unexpected field(s) {extra}')
    fix=[]
    if missing: fix.append(f'add the required field(s) {missing} with the task-required values')
    if extra: fix.append(f'remove only the unexpected field(s) {extra}')
    return [_issue(path,'; '.join(parts),'; '.join(fix),received=str(sorted(doc)),expected=str(sorted(expected)))]

def text_field(value,path,*,nullable=False):
    if nullable and value is None:return []
    if isinstance(value,str) and value.strip():return []
    repairable=isinstance(value,(bool,int,float)) or (isinstance(value,list) and len(value)==1 and isinstance(value[0],str))
    if nullable and isinstance(value,str) and not value.strip():
        return [_issue(path,'This optional text field is blank','Use literal null if there is no value, or provide non-empty text if there is one',repair_class='serialization',received=preview(value),expected='non-empty text or null')]
    return [_issue(path,f'This field requires non-empty text{" or literal null" if nullable else ""}, but you returned {type_name(value)}','Reserialize the existing value as one quoted string without changing its words' if repairable else 'Provide the required non-empty text',repair_class='serialization' if repairable else 'content',received=preview(value),expected='non-empty text'+(' or null' if nullable else ''))]

def enum_field(value,allowed,path,*,label='value'):
    allowed=list(allowed)
    if value in allowed:return []
    received=preview(value)
    if len(allowed)<=MAX_LISTED_ENUM_VALUES:
        choices=sorted(allowed); expected=str(choices); fix=f'Choose exactly one allowed {label}: {choices}'
    else:
        near=difflib.get_close_matches(str(value or ''),[str(x) for x in allowed],n=NEAREST_MATCHES,cutoff=.4)
        if near: expected=f'nearest allowed values: {near}'; fix=f'Replace it with the exact allowed {label} you intended, most likely one of {near}'
        else: expected=f'exact value from supplied {label} vocabulary'; fix=f'Copy one exact {label} verbatim from the allowed vocabulary supplied in the task'
    return [_issue(path,f'{received!r} is not an allowed {label}',fix,received=received,expected=expected,preserve='Do not change other clinical/evidence conclusions just to satisfy this vocabulary field.')]

def id_list(value,path,valid,*,allow_empty=False):
    if not isinstance(value,list):
        return set(),[_issue(path,f'This field must be a YAML/JSON list of supplied IDs, not {type_name(value)}','Wrap the single supplied ID in a list without changing it' if isinstance(value,str) and value in valid else 'Return a list containing only supplied IDs',repair_class='serialization' if isinstance(value,str) and value in valid else 'content',received=preview(value),expected='list of supplied IDs')]
    issues=[]
    if not value and not allow_empty:issues.append(_issue(path,'The ID list is empty','Include at least one supplied ID'))
    unknown=[x for x in value if not isinstance(x,str) or x not in valid]
    if unknown:issues.append(_issue(path,f'The list contains ID(s) that were not supplied: {[preview(x,40) for x in unknown]}',f'Use only these supplied IDs: {sorted(valid)}',received=preview(value)))
    dupes=sorted({x for x in value if isinstance(x,str) and value.count(x)>1})
    if dupes:issues.append(_issue(path,f'The same ID is repeated: {dupes}',f'List each ID once; remove only the repeated copies of {dupes}',repair_class='serialization',received=preview(value)))
    return {x for x in value if isinstance(x,str) and x in valid},issues

def one_row_per_id(rows,expected_ids,*,id_field,path):
    expected_ids=list(expected_ids)
    if not isinstance(rows,list):
        return [_issue(path,f'This section must be a list with one row for each supplied {id_field}, but you returned {type_name(rows)}',f'Return exactly one row for each of {expected_ids}',received=preview(rows),expected=f'{len(expected_ids)} rows')]
    got=[r.get(id_field) if isinstance(r,dict) else None for r in rows]; scalar=[x for x in got if isinstance(x,str)]
    missing=[x for x in expected_ids if x not in scalar]; unexpected=sorted({x for x in scalar if x not in expected_ids}); duplicates=sorted({x for x in scalar if scalar.count(x)>1})
    issues=[]
    if missing or unexpected or duplicates:
        parts=[]; actions=[]
        if missing: parts.append(f'missing {missing}'); actions.append(f'add a complete row for {missing}')
        if duplicates: parts.append(f'duplicated {duplicates}'); actions.append(f'return one intended row for each duplicated ID {duplicates}; if the rows disagree, reassess rather than letting Python choose')
        if unexpected: parts.append(f'unexpected {unexpected}'); actions.append(f'remove rows whose {id_field} was not supplied: {unexpected}')
        issues.append(_issue(path,'; '.join(parts),'; '.join(actions),received=f'{len(rows)} row(s): {preview(scalar)}',expected=f'{len(expected_ids)} row(s): {expected_ids}',preserve='Keep valid rows for unrelated IDs unchanged.'))
    elif scalar!=expected_ids:
        issues.append(_issue(path,'All required rows are present, but they are not in the supplied order',f'Reorder the rows to {expected_ids} without changing any row content',repair_class='serialization',received=preview(scalar),expected=str(expected_ids)))
    for i,row in enumerate(rows):
        if not isinstance(row,dict): issues.append(_issue(f'{path}[{i}]',f'Each row must be a mapping/object, not {type_name(row)}','Return this row as one mapping/object with the required fields',received=preview(row)))
    return issues

def bool_field(value,path):
    if isinstance(value,bool):return []
    repairable=isinstance(value,str) and value.strip().lower() in {'true','false','yes','no'}
    return [_issue(path,f'This field must be true or false, not {type_name(value)}','Reserialize the same decision as an unquoted YAML/JSON boolean' if repairable else 'Choose true or false according to your intended decision',repair_class='serialization' if repairable else 'content',received=preview(value),expected='true | false')]
