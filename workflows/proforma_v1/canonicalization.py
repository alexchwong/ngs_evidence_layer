"""Safe pre-validation canonicalization for proforma-v1 model artifacts.

Only representation and deterministic identity are changed here.  This module
must never choose between conflicting clinical/evidence meanings, invent a
reason, select evidence, or change a clinical enum.  Every applied transform is
returned for audit logging.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any
import yaml


def _dump(doc: Any) -> str:
    return yaml.safe_dump(doc, sort_keys=False, allow_unicode=True, width=110)


def _parse(text: str):
    try:
        return yaml.safe_load(text)
    except yaml.YAMLError:
        return None



def repair_unquoted_yaml_colon(text: str) -> tuple[str,list[dict]]:
    """Quote a plain scalar when an internal ``: `` is the sole YAML parse defect.

    The repair is deliberately conservative: only the parser-marked line is
    considered; the line must be a simple ``key: plain scalar`` mapping entry;
    the scalar must contain an internal colon-space; and the repaired document
    must parse successfully.  The scalar bytes are preserved exactly by JSON
    quoting, so no clinical or informational content is interpreted.
    """
    import json
    raw=str(text or "")
    try:
        yaml.safe_load(raw)
        return raw,[]
    except yaml.YAMLError as exc:
        mark=getattr(exc,"problem_mark",None)
        if mark is None:
            return raw,[]
        line_no=int(mark.line)
    lines=raw.splitlines()
    if line_no < 0 or line_no >= len(lines):
        return raw,[]
    line=lines[line_no]
    import re
    m=re.match(r'^(\s*(?:-\s+)?[A-Za-z_][A-Za-z0-9_-]*:\s+)(.+)$',line)
    if not m:
        return raw,[]
    prefix,value=m.groups()
    if ': ' not in value or value[:1] in {'"',"'",'[','{','|','>'}:
        return raw,[]
    # Comments and YAML anchors/tags can carry structure rather than scalar text.
    if ' #' in value or value.startswith(('&','*','!')):
        return raw,[]
    repaired=list(lines)
    repaired[line_no]=prefix+json.dumps(value,ensure_ascii=False)
    candidate='\n'.join(repaired)+( '\n' if raw.endswith('\n') else '')
    try:
        yaml.safe_load(candidate)
    except yaml.YAMLError:
        return raw,[]
    return candidate,[{
        'transform':'quote_plain_yaml_scalar_with_internal_colon',
        'path':f'line[{line_no+1}]',
        'from':value,
        'to':value,
    }]

def _record(records, transform, path, before, after):
    records.append({"transform": transform, "path": path, "from": deepcopy(before), "to": deepcopy(after)})


def _stable_unique(values):
    out=[]
    for value in values:
        if value not in out:
            out.append(value)
    return out


def _dedupe_identical_rows(rows, records, path):
    if not isinstance(rows, list):
        return rows
    out=[]
    for i,row in enumerate(rows):
        if any(row == prior for prior in out):
            _record(records,"remove_exact_duplicate_row",f"{path}[{i}]",row,"<removed>")
            continue
        out.append(row)
    return out


def _reorder_rows(rows, expected_ids, id_field, records, path):
    if not isinstance(rows,list):
        return rows
    if not all(isinstance(r,dict) for r in rows):
        return rows
    ids=[r.get(id_field) for r in rows]
    expected=list(expected_ids)
    if len(ids) != len(expected) or set(ids) != set(expected) or len(set(ids)) != len(ids):
        return rows
    if ids == expected:
        return rows
    by_id={r[id_field]:r for r in rows}
    out=[by_id[x] for x in expected]
    _record(records,"reorder_rows_to_supplied_identity",path,ids,expected)
    return out


def canonicalize_diagnosis(text: str, *, valid_variants) -> tuple[str,list[dict]]:
    doc=_parse(text); records=[]
    if not isinstance(doc,dict):
        return text,records
    variants=doc.get("variants")
    if isinstance(variants,str) and variants in valid_variants:
        _record(records,"wrap_single_variant_id","variants",variants,[variants]); doc["variants"]=[variants]
    elif isinstance(variants,list):
        unique=_stable_unique(variants)
        if unique != variants:
            _record(records,"dedupe_variant_ids","variants",variants,unique); doc["variants"]=unique
    rows=doc.get("variant_assessments")
    if isinstance(rows,list):
        rows=_dedupe_identical_rows(rows,records,"variant_assessments")
        rows=_reorder_rows(rows,sorted(valid_variants),"variant_id",records,"variant_assessments")
        for i,row in enumerate(rows):
            if not isinstance(row,dict):
                continue
            other=row.get("other_pathology")
            if isinstance(other,str) and not other.strip():
                _record(records,"blank_optional_text_to_null",f"variant_assessments[{i}].other_pathology",other,None)
                row["other_pathology"]=None
        doc["variant_assessments"]=rows
    return (_dump(doc),records) if records else (text,records)


def canonicalize_evidence_match(text: str, items: list[dict]) -> tuple[str,list[dict]]:
    doc=_parse(text); records=[]
    if not isinstance(doc,dict): return text,records
    rows=doc.get("matches")
    if isinstance(rows,dict):
        _record(records,"wrap_single_row","matches",rows,[rows]); rows=[rows]
    if isinstance(rows,list):
        rows=_dedupe_identical_rows(rows,records,"matches")
        rows=_reorder_rows(rows,[x["evidence_id"] for x in items],"evidence_id",records,"matches")
        candidates={x["evidence_id"]:list(x.get("candidate_card_tags") or []) for x in items}
        for i,row in enumerate(rows):
            if not isinstance(row,dict): continue
            tags=row.get("card_tags")
            eid=row.get("evidence_id")
            if tags == "":
                _record(records,"empty_card_tag_scalar_to_empty_list",f"matches[{i}].card_tags",tags,[]); row["card_tags"]=[]
            elif isinstance(tags,str) and tags in candidates.get(eid,[]):
                _record(records,"wrap_single_exact_card_tag",f"matches[{i}].card_tags",tags,[tags]); row["card_tags"]=[tags]
            elif isinstance(tags,list):
                unique=_stable_unique(tags)
                if unique != tags:
                    _record(records,"dedupe_exact_card_tags",f"matches[{i}].card_tags",tags,unique); row["card_tags"]=unique
        doc["matches"]=rows
    return (_dump(doc),records) if records else (text,records)


def canonicalize_evidence_audit(text: str, items: list[dict]) -> tuple[str,list[dict]]:
    doc=_parse(text); records=[]
    if not isinstance(doc,dict): return text,records
    rows=doc.get("audits")
    if isinstance(rows,dict):
        _record(records,"wrap_single_row","audits",rows,[rows]); rows=[rows]
    if isinstance(rows,list):
        rows=_dedupe_identical_rows(rows,records,"audits")
        rows=_reorder_rows(rows,[x["evidence_id"] for x in items],"evidence_id",records,"audits")
        selected={x["evidence_id"]:list(x.get("selected_card_tags") or []) for x in items}
        for i,row in enumerate(rows):
            if not isinstance(row,dict): continue
            audits=row.get("card_audits")
            if isinstance(audits,dict):
                _record(records,"wrap_single_card_audit",f"audits[{i}].card_audits",audits,[audits]); audits=[audits]
            if isinstance(audits,list):
                audits=_dedupe_identical_rows(audits,records,f"audits[{i}].card_audits")
                audits=_reorder_rows(audits,selected.get(row.get("evidence_id"),[]),"card_tag",records,f"audits[{i}].card_audits")
                for j,audit in enumerate(audits):
                    if not isinstance(audit,dict): continue
                    comments=audit.get("comments")
                    if isinstance(comments,str):
                        new=[] if not comments.strip() else [comments]
                        _record(records,"comments_scalar_to_list",f"audits[{i}].card_audits[{j}].comments",comments,new); audit["comments"]=new
                    elif comments is None and audit.get("card_is_element_of_reason") is True and audit.get("risk") == "none":
                        _record(records,"null_comments_to_empty_list",f"audits[{i}].card_audits[{j}].comments",None,[]); audit["comments"]=[]
                    elif isinstance(comments,list):
                        unique=_stable_unique(comments)
                        if unique != comments:
                            _record(records,"dedupe_comments",f"audits[{i}].card_audits[{j}].comments",comments,unique); audit["comments"]=unique
                row["card_audits"]=audits
        doc["audits"]=rows
    return (_dump(doc),records) if records else (text,records)


def canonicalize_report_write(text: str, blocks: list[dict]) -> tuple[str,list[dict]]:
    return _canonicalize_block_rows(text,"blocks",blocks,issue_field=None)


def canonicalize_preservation(text: str, blocks: list[dict]) -> tuple[str,list[dict]]:
    return _canonicalize_block_rows(text,"audits",blocks,issue_field="issue")


def _canonicalize_block_rows(text,key,blocks,issue_field):
    doc=_parse(text); records=[]
    if not isinstance(doc,dict): return text,records
    rows=doc.get(key)
    if isinstance(rows,dict):
        _record(records,"wrap_single_row",key,rows,[rows]); rows=[rows]
    if isinstance(rows,list):
        rows=_dedupe_identical_rows(rows,records,key)
        rows=_reorder_rows(rows,[x["block_id"] for x in blocks],"block_id",records,key)
        if issue_field:
            for i,row in enumerate(rows):
                if not isinstance(row,dict): continue
                issue=row.get(issue_field)
                if row.get("preserved") is True and isinstance(issue,str) and not issue.strip():
                    _record(records,"blank_optional_text_to_null",f"{key}[{i}].{issue_field}",issue,None); row[issue_field]=None
        doc[key]=rows
    return (_dump(doc),records) if records else (text,records)


def canonicalize_adjudication_nulls(text: str) -> tuple[str,list[dict]]:
    """Fill only null fields whose value is fixed by the existing upheld verdict.

    Python never chooses or changes ``upheld``.  For an upheld row the unused
    ``rejection_reason`` is necessarily null; for a rejected row the unused
    ``basis`` and ``restated_criticism`` are necessarily null.  Adding an omitted
    null is therefore representation-only canonicalization.
    """
    doc=_parse(text); records=[]
    if not isinstance(doc,dict): return text,records
    rows=doc.get('adjudications')
    if not isinstance(rows,list): return text,records
    for i,row in enumerate(rows):
        if not isinstance(row,dict): continue
        if row.get('upheld') is True and 'rejection_reason' not in row:
            _record(records,'inject_adjudication_null',f'adjudications[{i}].rejection_reason','<missing>',None)
            row['rejection_reason']=None
        elif row.get('upheld') is False:
            for field in ('basis','restated_criticism'):
                if field not in row:
                    _record(records,'inject_adjudication_null',f'adjudications[{i}].{field}','<missing>',None)
                    row[field]=None
    return (_dump(doc),records) if records else (text,records)


_NAMED = {
    'adjudication_nulls': canonicalize_adjudication_nulls,
}


def named(name: str):
    """Return a registered representation-only model-output canonicalizer."""
    try:
        return _NAMED[str(name)]
    except KeyError:
        raise ValueError(f'unknown model-output canonicalizer {name!r}; registered: {sorted(_NAMED)}') from None
