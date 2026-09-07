"""Minimal explicit reasoning layer for the default-reviewed proforma-v1 workflow.

Clinical owners decide medicine.  This module owns deterministic source packets,
Secretary compilation, stable IDs/dependencies, evidence-loss detection and the
human-readable reasoning trace.  It does not contain disease/framework rules.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any
import json

import yaml

OWNERS = ("who1", "who2", "icc", "prognosis", "treatment", "biomarker", "germline")
PTBG = ("prognosis", "treatment", "biomarker", "germline")


def _ctx(context: dict):
    ctx = context.get("__workflow_context__") if isinstance(context, dict) else None
    if ctx is None:
        raise ValueError("default-reviewed reasoning transform requires workflow context")
    return ctx


def _work(context: dict) -> Path:
    value = context.get("__work__") if isinstance(context, dict) else None
    if value is None:
        value = getattr(_ctx(context), "work", None)
    if value is None:
        raise ValueError("default-reviewed reasoning transform requires work directory")
    return Path(value)


def _owner(params: dict) -> str:
    value = str(params.get("owner") or "").strip()
    if value in OWNERS:
        return value
    step_id = str(params.get("step_id") or "")
    for owner in OWNERS:
        if step_id == owner or step_id.startswith(owner + ".") or step_id.endswith("." + owner) or ("." + owner + ".") in step_id:
            return owner
    raise ValueError(f"cannot infer reviewed reasoning owner from step {step_id!r}")


def _raw_ptbg(work: Path, owner: str) -> dict:
    from workflows.proforma_v1 import self_runtime as sr
    path = sr.output_path(work, f"{owner}_state", "model-classification.yaml")
    if not path.is_file():
        raise ValueError(f"reviewed {owner} clinical model artifact missing: {path}")
    doc = sr.read_yaml(path)
    if not isinstance(doc, dict):
        raise ValueError(f"reviewed {owner} clinical artifact must be a mapping")
    return doc


def _canonical_ptbg(work: Path, owner: str) -> dict:
    from workflows.proforma_v1 import self_runtime as sr
    path = sr.output_path(work, f"{owner}_state", "proforma.yaml")
    if not path.is_file():
        raise ValueError(f"reviewed {owner} canonical proforma missing: {path}")
    doc = sr.read_yaml(path)
    if not isinstance(doc, dict):
        raise ValueError(f"reviewed {owner} canonical proforma must be a mapping")
    return doc


def _generic_artifact(ctx, step_id: str, artifact_name: str):
    value = ctx.get(artifact_name)
    if value is not None:
        return value
    workflow = ctx.get("workflow")
    if workflow is None:
        return None
    try:
        step = workflow.step(step_id)
    except KeyError:
        return None
    from workflows.proforma_v1.engine import artifacts as workflow_artifacts
    path = workflow_artifacts.generic_output_path(ctx.work, step, create=False)
    if not path.is_file():
        return None
    fmt = str((step.output or {}).get("format") or "yaml").lower()
    raw = path.read_text(encoding="utf-8")
    value = json.loads(raw) if fmt == "json" else yaml.safe_load(raw) if fmt == "yaml" else raw
    ctx.put(artifact_name, value)
    return value


def _diagnostic_source(ctx, work: Path, owner: str) -> dict:
    candidates = {
        "who1": ("diagnosis_who1", "who1"),
        "who2": ("diagnosis_who2", "who2"),
        "icc": ("diagnosis_icc", "icc"),
    }[owner]
    for key in candidates:
        value = ctx.get(key)
        if isinstance(value, dict):
            return value
    from workflows.proforma_v1 import self_runtime as sr
    if owner == "who1":
        return sr.accept_who(work, pass_number=1)
    if owner == "who2":
        return sr.accept_who(work, pass_number=2)
    return sr.accept_icc(work)


def _fragment(path: str, value: Any, *, role: str = "supporting") -> dict | None:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        text = str(value).strip()
        return {"path": path, "value": text, "role": role} if text else None
    return None


def _diag_packet(owner: str, clinical: dict) -> dict:
    fragments = []
    row = _fragment("reason", clinical.get("reason"))
    if row: fragments.append(row)
    for i, assessment in enumerate(clinical.get("variant_assessments") or []):
        if not isinstance(assessment, dict):
            continue
        row = _fragment(f"variant_assessments[{i}].reason", assessment.get("reason"), role="context")
        if row: fragments.append(row)
    conclusions = [{
        "conclusion_id": "C001",
        "conclusion_path": "diagnosis",
        "conclusion": str(clinical.get("diagnosis") or "").strip(),
        "synthesis_path": "reason",
        "synthesis": str(clinical.get("reason") or "").strip(),
        "evidence_schema_id": "DX-WHO5" if owner in {"who1", "who2"} else "DX-ICC",
        "source_fragments": [dict(fragment_id=f"S{i:03d}", **row) for i, row in enumerate(fragments, 1)],
    }]
    # WHO variant assessments may independently signal a concurrent pathology.
    # Keep that conclusion explicit rather than hiding it inside main-diagnosis context.
    concurrent_no = 0
    if owner in {"who1", "who2"}:
        for i, assessment in enumerate(clinical.get("variant_assessments") or []):
            if not isinstance(assessment, dict) or assessment.get("classification") != "diagnostic_for_other_pathology" or not assessment.get("other_pathology"):
                continue
            concurrent_no += 1
            frag = _fragment(f"variant_assessments[{i}].reason", assessment.get("reason"))
            conclusions.append({
                "conclusion_id": f"C{len(conclusions)+1:03d}",
                "conclusion_path": f"variant_assessments[{i}].other_pathology",
                "conclusion": f"Concurrent pathology signal: {assessment.get('other_pathology')}",
                "synthesis_path": f"variant_assessments[{i}].reason",
                "synthesis": str(assessment.get("reason") or "").strip(),
                "evidence_schema_id": f"DX-CONCURRENT-{concurrent_no:02d}",
                "source_fragments": [dict(fragment_id="S001", **frag)] if frag else [],
            })
    return {"owner": owner, "clinical": clinical, "conclusions": conclusions}


def _raw_row_by_variant(raw: dict, variant: str) -> dict | None:
    for row in raw.get("classification") or []:
        if isinstance(row, dict) and row.get("variant") == variant:
            return row
    return None


def _add_conclusion(out: list[dict], *, conclusion: str, synthesis: str, schema_id: str | None, fragments: list[tuple[str, Any]]):
    source = []
    for fragment in fragments:
        path, value, *rest = fragment
        row = _fragment(path, value, role=(rest[0] if rest else "supporting"))
        if row:
            source.append(row)
    out.append({
        "conclusion_id": f"C{len(out)+1:03d}",
        "conclusion": str(conclusion or "").strip(),
        "synthesis": str(synthesis or "").strip(),
        "evidence_schema_id": schema_id,
        # Fragment IDs are conclusion-local. Python owns them; the Secretary only copies them.
        "source_fragments": [dict(fragment_id=f"S{i:03d}", **row) for i, row in enumerate(source, 1)],
    })


def _ptbg_packet(owner: str, raw: dict, canonical: dict) -> dict:
    conclusions: list[dict] = []
    if owner == "prognosis":
        for i, fw in enumerate(canonical.get("prognostic_frameworks") or [], 1):
            if not isinstance(fw, dict): continue
            tier = fw.get("tier")
            label = f"{fw.get('name')}" + (f" risk tier: {tier}" if tier is not None else " is an applicable prognostic framework")
            _add_conclusion(conclusions, conclusion=label, synthesis=fw.get("reason"), schema_id=f"PX-FRAMEWORK-{i:02d}", fragments=[(f"prognostic_frameworks[{i-1}].reason", fw.get("reason"))])
        for bucket in ("framework_favorable","framework_adverse","framework_neutral","other_evidence_favorable","other_evidence_adverse","other_evidence_neutral","no_prognostic_evidence"):
            for i, row in enumerate(canonical.get(bucket) or [], 1):
                if not isinstance(row, dict): continue
                schema = None if bucket == "no_prognostic_evidence" else f"PX-{bucket.upper()}-{i:02d}"
                variant = (row.get("variants") or [None])[0]
                raw_row = _raw_row_by_variant(raw, variant) or {}
                fragments=[(f"canonical.{bucket}[{i-1}].reason", row.get("reason"))]
                # Preserve the raw CEO source wording when available.
                if bucket.startswith("other_evidence_"):
                    fragments.append(("raw.other_evidence_reason", raw_row.get("other_evidence_reason"), "context"))
                _add_conclusion(conclusions, conclusion=row.get("reason"), synthesis=row.get("reason"), schema_id=schema, fragments=fragments)
    elif owner in {"treatment", "biomarker", "germline"}:
        prefixes={"treatment":"TX","biomarker":"MRD","germline":"GL"}
        for bucket, rows in canonical.items():
            if bucket in {"applicable_disease"} or not isinstance(rows, list):
                continue
            for i, row in enumerate(rows, 1):
                if not isinstance(row, dict): continue
                reportable = bucket not in {"no_drug_implication","not_mrd_marker","germline_against","germline_uncertain"}
                schema = f"{prefixes[owner]}-{bucket.upper()}-{i:02d}" if reportable else None
                variant = (row.get("variants") or [None])[0]
                raw_row = _raw_row_by_variant(raw, variant) or {}
                fragments=[(f"canonical.{bucket}[{i-1}].reason", row.get("reason"))]
                if owner == "germline":
                    pred = raw_row.get("predisposition_evidence")
                    if isinstance(pred, dict):
                        fragments.append(("raw.predisposition_evidence.mechanism", pred.get("mechanism")))
                    for factor in ("event_compatibility","age","vaf","personal_history","family_history","phenotype"):
                        frow=raw_row.get(factor)
                        if isinstance(frow,dict): fragments.append((f"raw.{factor}.reason", frow.get("reason")))
                    fragments.append(("raw.reason", raw_row.get("reason"), "context"))
                _add_conclusion(conclusions, conclusion=row.get("reason"), synthesis=row.get("reason"), schema_id=schema, fragments=fragments)
    return {"owner": owner, "clinical": raw, "canonical": canonical, "conclusions": conclusions}


def owner_packet(context: dict, params: dict) -> dict:
    owner = _owner(params); ctx = _ctx(context); work = _work(context)
    if owner in {"who1","who2","icc"}:
        return _diag_packet(owner, _diagnostic_source(ctx, work, owner))
    return _ptbg_packet(owner, _raw_ptbg(work, owner), _canonical_ptbg(work, owner))


def _secretary_key(owner: str) -> str:
    return f"default_reviewed_{owner}_secretary"


def _packet_key(owner: str) -> str:
    return f"default_reviewed_{owner}_packet"


def _compiled_key(owner: str) -> str:
    return f"default_reviewed_{owner}_reasoning"


def compile_secretary(context: dict, params: dict) -> dict:
    owner = _owner(params); ctx = _ctx(context)
    packet = _generic_artifact(ctx, f"{owner}.packet", _packet_key(owner)) or {}
    secretary = _generic_artifact(ctx, f"{owner}.secretary", _secretary_key(owner)) or {}
    expected = {c.get("conclusion_id"): c for c in packet.get("conclusions") or [] if isinstance(c, dict)}
    returned = {c.get("conclusion_id"): c for c in secretary.get("conclusions") or [] if isinstance(c, dict)}
    issues=[]
    if secretary.get("owner") != owner:
        issues.append(f"Secretary returned owner {secretary.get('owner')!r}; expected {owner!r}.")
    missing=sorted(set(expected)-set(returned)); extra=sorted(set(returned)-set(expected))
    if missing: issues.append("Missing conclusion(s): "+", ".join(missing)+".")
    if extra: issues.append("Unknown conclusion(s): "+", ".join(extra)+".")
    graph={"owner":owner,"conclusions":[]}
    fact_no=0
    for cid, source in expected.items():
        row=returned.get(cid) or {}; allowed={x.get("fragment_id"):x for x in source.get("source_fragments") or []}
        atoms=[]; used_fragments=set()
        for atom in row.get("atoms") or []:
            if not isinstance(atom,dict): continue
            sid=atom.get("source_fragment_id")
            if sid not in allowed:
                issues.append(f"{cid} atom references unknown source fragment {sid!r}."); continue
            text=str(atom.get("text") or "").strip()
            if not text:
                issues.append(f"{cid} contains an empty atom for {sid}."); continue
            evidence_class=atom.get("evidence_class")
            if evidence_class not in {"case_fact","clinical_application","literature_rule"}:
                issues.append(f"{cid} atom for {sid} has invalid evidence_class {evidence_class!r}."); continue
            used_fragments.add(sid); fact_no += 1
            atoms.append({
                "fact_id":f"F{fact_no:03d}",
                "source_fragment_id":sid,
                "source_path":allowed[sid].get("path"),
                "source_value":allowed[sid].get("value"),
                "dependency_role":allowed[sid].get("role") or "supporting",
                "text":text,
                "evidence_class":evidence_class,
            })
        missing_fragments=sorted(set(allowed)-used_fragments)
        if missing_fragments:
            issues.append(f"{cid} omitted source fragment(s): {', '.join(missing_fragments)}.")
        graph["conclusions"].append({
            "conclusion_id":cid,
            "conclusion":source.get("conclusion"),
            "synthesis":source.get("synthesis"),
            "evidence_schema_id":source.get("evidence_schema_id"),
            "facts":atoms,
            "fact_ids":[x["fact_id"] for x in atoms if x.get("dependency_role")=="supporting"],
            "context_fact_ids":[x["fact_id"] for x in atoms if x.get("dependency_role")!="supporting"],
        })
    return {
        "status":"pass" if not issues else "fail",
        "feedback":"" if not issues else "Secretary representation is structurally inconsistent with the supplied owner packet:\n- "+"\n- ".join(issues)+"\n",
        "issues":issues,
        "graph":graph,
    }



def validate_precheck(context: dict, params: dict) -> dict:
    """Validate the generic R1 artifact itself before routing its judgement.

    Malformed/missing R1 output belongs to the R1 model, not to the Secretary or
    clinical owner.  Keep this check deliberately structural and knowledge-free.
    """
    owner=_owner(params); ctx=_ctx(context)
    pre=_generic_artifact(ctx, f"{owner}.precheck", f"default_reviewed_{owner}_precheck")
    issues=[]
    if not isinstance(pre,dict):
        issues.append("Reasoning-1 output is not a mapping.")
    else:
        representation=pre.get("representation")
        coherence=pre.get("coherence")
        if not isinstance(representation,dict) or representation.get("status") not in {"faithful","not_faithful"}:
            issues.append("representation.status must be faithful or not_faithful.")
        if not isinstance(coherence,dict) or coherence.get("status") not in {"coherent","incoherent","indeterminate"}:
            issues.append("coherence.status must be coherent, incoherent or indeterminate.")
        for label,row in (("representation",representation),("coherence",coherence)):
            if isinstance(row,dict) and not isinstance(row.get("comments"),list):
                issues.append(f"{label}.comments must be a list.")
    return {
        "status":"pass" if not issues else "fail",
        "feedback":"" if not issues else "Reasoning-1 artifact is structurally invalid:\n- "+"\n- ".join(issues)+"\n",
        "issues":issues,
    }


def _validate_postcheck_doc(items: list[dict], result: Any) -> dict:
    issues=[]
    if not isinstance(result,dict):
        issues.append("Reasoning-2 output is not a mapping.")
        rows=[]
    else:
        rows=result.get("verdicts")
        if not isinstance(rows,list):
            issues.append("verdicts must be a list.")
            rows=[]
    expected={(str(x.get("owner")),str(x.get("conclusion_id"))) for x in items if isinstance(x,dict)}
    seen=set()
    for i,row in enumerate(rows):
        if not isinstance(row,dict):
            issues.append(f"verdicts[{i}] must be a mapping."); continue
        key=(str(row.get("owner")),str(row.get("conclusion_id")))
        if key not in expected:
            issues.append(f"verdicts[{i}] references an unaffected/unknown conclusion {key!r}.")
        if key in seen:
            issues.append(f"verdicts[{i}] duplicates conclusion {key!r}.")
        seen.add(key)
        if row.get("verdict") not in {"survives","survives_with_qualification","revise"}:
            issues.append(f"verdicts[{i}].verdict is invalid.")
        if not isinstance(row.get("comments"),list):
            issues.append(f"verdicts[{i}].comments must be a list.")
    for key in sorted(expected-seen):
        issues.append(f"No Reasoning-2 verdict was returned for {key!r}.")
    return {
        "status":"pass" if not issues else "fail",
        "feedback":"" if not issues else "Reasoning-2 artifact is structurally invalid:\n- "+"\n- ".join(issues)+"\n",
        "issues":issues,
    }


def validate_postcheck(context: dict, params: dict) -> dict:
    ctx=_ctx(context)
    items=_generic_artifact(ctx,"postcheck.prepare","default_reviewed_postcheck_items") or []
    result=_generic_artifact(ctx,"postcheck.reasoning","default_reviewed_postcheck")
    return _validate_postcheck_doc(items,result)


def validate_who1_postcheck(context: dict, params: dict) -> dict:
    ctx=_ctx(context)
    items=_generic_artifact(ctx,"who1.postcheck.prepare","default_reviewed_who1_postcheck_items") or []
    result=_generic_artifact(ctx,"who1.postcheck","default_reviewed_who1_postcheck")
    return _validate_postcheck_doc(items,result)

def precheck_representation_review(context: dict, params: dict) -> dict:
    owner=_owner(params); ctx=_ctx(context); pre=_generic_artifact(ctx, f"{owner}.precheck", f"default_reviewed_{owner}_precheck") or {}
    row=pre.get("representation") or {}; ok=row.get("status")=="faithful"
    comments=" ".join(str(x).strip() for x in row.get("comments") or [] if str(x).strip())
    return {"status":"pass" if ok else "fail","feedback":comments or ("" if ok else "Secretary representation did not faithfully preserve the CEO artifact."),"issues":[] if ok else ["representation_not_faithful"]}


def precheck_coherence_review(context: dict, params: dict) -> dict:
    owner=_owner(params); ctx=_ctx(context); pre=_generic_artifact(ctx, f"{owner}.precheck", f"default_reviewed_{owner}_precheck") or {}
    row=pre.get("coherence") or {}; ok=row.get("status")=="coherent"
    comments=" ".join(str(x).strip() for x in row.get("comments") or [] if str(x).strip())
    return {"status":"pass" if ok else "fail","feedback":comments or ("" if ok else "The clinical conclusion does not follow from its own stated premises/synthesis."),"issues":[] if ok else ["clinical_reasoning_incoherent"]}


def _who1_supported(work: Path) -> bool:
    from workflows.proforma_v1 import self_runtime as sr
    change=sr.assess_who1_routing_change(work)
    if not change.get("changed"):
        return True
    agreed, disputes = sr.who1_evidence_disputes(work)
    accepted=list(agreed)
    if disputes:
        path=sr._who1_gate_adjudication_path(work)
        if path.is_file():
            doc=sr.read_yaml(path)
            sr.evidence_engine.validate_adjudication(doc,disputes)
            accepted.extend([x.get("card_tag") for x in doc.get("adjudications") or [] if x.get("decision")=="include"])
    return bool([x for x in accepted if x])


def who1_postcheck_prepare(context: dict, params: dict) -> list[dict]:
    ctx=_ctx(context); work=_work(context)
    if _who1_supported(work):
        return []
    compiled=_generic_artifact(ctx, "who1.secretary.compile", _compiled_key("who1")) or {}; graph=compiled.get("graph") or {}
    out=[]
    for conclusion in graph.get("conclusions") or []:
        evidence_facts=[x for x in conclusion.get("facts") or [] if x.get("dependency_role")=="supporting" and x.get("evidence_class")=="literature_rule"]
        if evidence_facts:
            out.append({"owner":"who1","conclusion_id":conclusion.get("conclusion_id"),"conclusion":conclusion.get("conclusion"),"original_synthesis":conclusion.get("synthesis"),"surviving_facts":[x.get("text") for x in conclusion.get("facts") or [] if x.get("dependency_role")=="supporting" and x.get("evidence_class")!="literature_rule"],"removed_facts":[x.get("text") for x in evidence_facts]})
    return out


def _supported_schema_ids(work: Path) -> set[str]:
    from workflows.proforma_v1 import self_runtime as sr
    path=sr.output_path(work,"evidence_enriched","reportable-elements.yaml")
    if not path.is_file(): return set()
    doc=sr.read_yaml(path) or {}
    return {str(x.get("schema_id")) for x in doc.get("elements") or [] if isinstance(x,dict) and x.get("schema_id")}


def postcheck_prepare(context: dict, params: dict) -> list[dict]:
    ctx=_ctx(context); work=_work(context); supported=_supported_schema_ids(work); items=[]
    who2_packet=_generic_artifact(ctx, "who2.packet", _packet_key("who2"))
    owners=["who2" if isinstance(who2_packet,dict) else "who1","icc",*PTBG]
    for owner in owners:
        compiled=_generic_artifact(ctx, f"{owner}.secretary.compile", _compiled_key(owner)) or {}; graph=compiled.get("graph") or {}
        for conclusion in graph.get("conclusions") or []:
            schema=conclusion.get("evidence_schema_id")
            evidence_facts=[x for x in conclusion.get("facts") or [] if x.get("dependency_role")=="supporting" and x.get("evidence_class")=="literature_rule"]
            if not schema or not evidence_facts or schema in supported:
                continue
            items.append({"owner":owner,"conclusion_id":conclusion.get("conclusion_id"),"conclusion":conclusion.get("conclusion"),"original_synthesis":conclusion.get("synthesis"),"surviving_facts":[x.get("text") for x in conclusion.get("facts") or [] if x.get("dependency_role")=="supporting" and x.get("evidence_class")!="literature_rule"],"removed_facts":[x.get("text") for x in evidence_facts]})
    return items


def postcheck_review(context: dict, params: dict) -> dict:
    owner=_owner(params); ctx=_ctx(context); all_items=_generic_artifact(ctx, "postcheck.prepare", "default_reviewed_postcheck_items") or []; items=[x for x in all_items if x.get("owner")==owner]
    if not items:
        return {"status":"pass","feedback":"","issues":[]}
    result=_generic_artifact(ctx, "postcheck.reasoning", "default_reviewed_postcheck") or {}; verdicts={(x.get("owner"),x.get("conclusion_id")):x for x in result.get("verdicts") or [] if isinstance(x,dict)}
    bad=[]
    for item in items:
        row=verdicts.get((owner,item.get("conclusion_id"))) or {}
        if row.get("verdict") != "survives":
            bad.append(row or {"comments":["Post-evidence reasoning did not preserve the affected conclusion."]})
    comments=[]
    for row in bad:
        comments.extend(str(x).strip() for x in row.get("comments") or [] if str(x).strip())
    return {"status":"pass" if not bad else "fail","feedback":" ".join(comments) or ("" if not bad else "Evidence processing removed a conclusion-contributing premise; revise the affected clinical conclusion."),"issues":[] if not bad else ["post_evidence_revision_required"]}


def who1_postcheck_review(context: dict, params: dict) -> dict:
    ctx=_ctx(context); items=_generic_artifact(ctx, "who1.postcheck.prepare", "default_reviewed_who1_postcheck_items") or []
    if not items: return {"status":"pass","feedback":"","issues":[]}
    result=_generic_artifact(ctx, "who1.postcheck", "default_reviewed_who1_postcheck") or {}; verdicts={x.get("conclusion_id"):x for x in result.get("verdicts") or [] if isinstance(x,dict)}
    bad=[verdicts.get(x.get("conclusion_id")) or {} for x in items if (verdicts.get(x.get("conclusion_id")) or {}).get("verdict")!="survives"]
    comments=[str(c).strip() for row in bad for c in row.get("comments") or [] if str(c).strip()]
    return {"status":"pass" if not bad else "fail","feedback":" ".join(comments) or ("" if not bad else "Blocking evidence removed a WHO1 conclusion-contributing premise; revise the WHO5 clinical conclusion."),"issues":[] if not bad else ["post_evidence_revision_required"]}


def render_trace(context: dict, params: dict) -> dict:
    ctx=_ctx(context); work=_work(context)
    lines=["# Reasoning trace","","This trace is rendered from explicit workflow artifacts; it is not model chain-of-thought.",""]
    global_items=_generic_artifact(ctx, "postcheck.prepare", "default_reviewed_postcheck_items") or []
    global_doc=_generic_artifact(ctx, "postcheck.reasoning", "default_reviewed_postcheck") or {}
    global_verdicts={(x.get("owner"),x.get("conclusion_id")):x for x in global_doc.get("verdicts") or [] if isinstance(x,dict)}
    who1_items=_generic_artifact(ctx, "who1.postcheck.prepare", "default_reviewed_who1_postcheck_items") or []
    who1_doc=_generic_artifact(ctx, "who1.postcheck", "default_reviewed_who1_postcheck") or {}
    who1_verdicts={x.get("conclusion_id"):x for x in who1_doc.get("verdicts") or [] if isinstance(x,dict)}
    for owner in OWNERS:
        packet=_generic_artifact(ctx, f"{owner}.packet", _packet_key(owner)); compiled=_generic_artifact(ctx, f"{owner}.secretary.compile", _compiled_key(owner)); pre=_generic_artifact(ctx, f"{owner}.precheck", f"default_reviewed_{owner}_precheck")
        if not isinstance(packet,dict) or not isinstance(compiled,dict): continue
        lines += [f"## {owner}",""]
        pre=pre or {}; lines.append(f"**Representation:** {(pre.get('representation') or {}).get('status','not recorded')}")
        lines.append(f"**Reasoning-1:** {(pre.get('coherence') or {}).get('status','not recorded')}")
        for conclusion in (compiled.get("graph") or {}).get("conclusions") or []:
            lines += ["",f"### {conclusion.get('conclusion_id')}: {conclusion.get('conclusion')}",f"Synthesis: {conclusion.get('synthesis')}","Facts:"]
            for fact in conclusion.get("facts") or []:
                lines.append(f"- {fact.get('fact_id')}: {fact.get('text')} [{fact.get('evidence_class')}] <- {fact.get('source_path')}")
            item=next((x for x in [*who1_items,*global_items] if x.get("owner")==owner and x.get("conclusion_id")==conclusion.get("conclusion_id")),None)
            if item is None:
                lines.append("Reasoning-2: skipped — no contributing evidence-required fact was removed.")
            else:
                if owner=="who1" and item in who1_items:
                    row=who1_verdicts.get(conclusion.get("conclusion_id")) or {}
                else:
                    row=global_verdicts.get((owner, conclusion.get("conclusion_id"))) or {}
                lines.append(f"Reasoning-2: {row.get('verdict','missing')} — removed: {', '.join(item.get('removed_facts') or [])}")
        lines.append("")
    path=work/"reasoning-trace.md"; path.write_text("\n".join(lines).rstrip()+"\n",encoding="utf-8")
    return {"written":True,"path":str(path)}


def run(name: str, context: dict, params: dict) -> Any:
    dispatch={
        "default_reviewed_owner_packet":owner_packet,
        "default_reviewed_compile_secretary":compile_secretary,
        "default_reviewed_validate_precheck":validate_precheck,
        "default_reviewed_precheck_representation_review":precheck_representation_review,
        "default_reviewed_precheck_coherence_review":precheck_coherence_review,
        "default_reviewed_who1_postcheck_prepare":who1_postcheck_prepare,
        "default_reviewed_validate_who1_postcheck":validate_who1_postcheck,
        "default_reviewed_who1_postcheck_review":who1_postcheck_review,
        "default_reviewed_postcheck_prepare":postcheck_prepare,
        "default_reviewed_validate_postcheck":validate_postcheck,
        "default_reviewed_postcheck_review":postcheck_review,
        "default_reviewed_render_reasoning_trace":render_trace,
    }
    try: fn=dispatch[name]
    except KeyError as exc: raise ValueError(f"unknown default-reviewed reasoning transform {name!r}") from exc
    return fn(context,params)
