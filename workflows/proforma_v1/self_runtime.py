"""Native-self compatibility helpers for the declarative proforma-v1 engine.

Logical ordering is owned by ``workflow.yaml`` and the shared workflow runner.
This module retains deterministic artifact preparation/acceptance mechanics used
by the self execution adapter.
"""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from typing import Any

import yaml

from workflows.proforma_v1 import card_identity, domain_contract, layout, model_context, runtime, schema_validation
from workflows.proforma_v1 import step as staged
from workflows.proforma_v1.engine import evidence as evidence_engine

HERE = Path(__file__).resolve().parent
ADJUDICATION_PROMPT = HERE / "prompts" / "evidence_adjudicate.md"
ADJUDICATION_SCHEMA = HERE / "schemas" / "evidence_adjudicate.json"


def read_yaml(path: Path) -> dict:
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"expected YAML mapping: {path}")
    return data


def write_yaml(path: Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    return path


def write_json(path: Path, data: Any) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def artifact(work: Path, group: str, name: str, *, new: bool = False) -> Path:
    return staged._artifact(Path(work), group, name, new=new)


def contract_path(name: str) -> Path:
    spec = staged.stage_spec.load(name)
    return HERE / "prompts" / spec.prompt


def output_path(work: Path, group: str, name: str) -> Path:
    return staged._existing_or_new(Path(work), group, name)


def case_path(work: Path) -> Path:
    return staged._case_json(Path(work))


def variants_path(work: Path) -> Path:
    return staged._variants_path(Path(work))


def accept_structured_case(work: Path) -> tuple[dict, dict]:
    """Validate only the machine-critical case contract and create canonical vNN IDs."""
    work = Path(work)
    path = case_path(work)
    if not path.is_file():
        raise ValueError(f"structured case output missing: {path}")
    text = path.read_text(encoding="utf-8")
    runtime.validate_case_text(text)
    case = runtime.normalize_case_variant_descriptions(runtime.read_json(path))
    case = runtime.materialize_ngs_no_variants_detected(
        case, layout.setup(work, "ngs-panel-scope.md").read_text(encoding="utf-8")
    )
    path.write_text(json.dumps(case, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    runtime.validate_case_text(path.read_text(encoding="utf-8"), require_gene_prefixed_description=True)
    reg = {
        f"v{i:02d}": {
            "variant_id": row["variant_id"],
            "gene": row["gene"],
            "description": row["description"],
        }
        for i, row in enumerate(case.get("variants") or [], 1)
    }
    write_yaml(variants_path(work), {"variants": reg})
    return case, reg


def load_case_registry(work: Path) -> tuple[dict, dict]:
    case, _ = accept_structured_case(work)
    reg_doc = read_yaml(variants_path(work))
    reg = reg_doc.get("variants") or {}
    if not isinstance(reg, dict):
        raise ValueError("variant registry must contain a variants mapping")
    return case, reg


def corpus_state(work: Path):
    all_cards, eligible, digest, manifest = staged.stage_corpus(Path(work))
    return all_cards, eligible, digest, manifest


def _write_pool(
    work: Path,
    group: str,
    cards: list[dict],
    manifest: dict,
    *,
    diagnosis_authority: str | None = None,
) -> tuple[Path, Path]:
    tag_by_id = card_identity.tag_by_id(manifest)
    md = output_path(work, group, "cards.md")
    rendered = (
        staged._render_diagnostic_cards(cards, tag_by_id, diagnosis_authority)
        if diagnosis_authority
        else staged._render_cards(cards, tag_by_id)
    )
    md.write_text(rendered, encoding="utf-8")
    js = output_path(work, group, "cards.json")
    write_json(js, {"card_ids": [c["card_id"] for c in cards], "runtime_tags": {c["card_id"]: tag_by_id[c["card_id"]] for c in cards}})
    return md, js


def prepare_who(work: Path, *, pass_number: int, prompt: Path | None = None) -> dict:
    """Prepare WHO1 or authoritative WHO2 using the shared WHO5 contract."""
    work = Path(work)
    case, reg = load_case_registry(work)
    _all_cards, eligible, _digest, manifest = corpus_state(work)
    allowed = staged._allowed_diseases(work)
    genes = runtime.case_genes(case)
    bootstrap = list(case.get("bootstrap_cmcs") or [])
    if pass_number == 1:
        history = bootstrap
        group = "self_who1_input"
        out = output_path(work, "diagnosis_who5_pass_1", "who5.yaml")
    elif pass_number == 2:
        who1 = committed_who1(work, required=False) or read_yaml(output_path(work, "diagnosis_who5_pass_1", "who5.yaml"))
        schema_validation.validate_who5_diagnosis(
            yaml.safe_dump(who1), allowed_diseases=allowed, valid_variants=set(reg)
        )
        history = list(bootstrap)
        for cmc in runtime.derive_cmcs(who1):
            if cmc not in history:
                history.append(cmc)
        group = "self_who2_input"
        out = output_path(work, "diagnosis_who5_pass_2", "who5.yaml")
    else:
        raise ValueError("WHO pass_number must be 1 or 2")
    cards = staged._diagnostic_cards(eligible, genes, history, "who5")
    cards_md, _ = _write_pool(work, group, cards, manifest, diagnosis_authority="who5")
    finite = output_path(work, group, "finite-membership.yaml")
    write_yaml(finite, staged._finite_membership_context(reg, cards, card_identity.tag_by_id(manifest)))
    context = output_path(work, group, "context.yaml")
    write_yaml(context, {
        "starting_morphologic_diagnosis": case.get("provisional_disease"),
        "morphologic_diagnosis_origin": case.get("morphologic_diagnosis_origin"),
        "structured_case": case,
        "variant_registry": reg,
        "allowed_schema_diseases": sorted(allowed),
        "retrieval_cmcs": history,
        "authoritative": pass_number == 2,
    })
    return {
        "pass": f"who{pass_number}",
        "contract": contract_path("diagnosis_who5"),
        "prompt": prompt,
        "context": context,
        "finite_membership": finite,
        "cards": cards_md,
        "output": out,
    }


def accept_who(work: Path, *, pass_number: int) -> dict:
    case, reg = load_case_registry(work)
    allowed = staged._allowed_diseases(work)
    path = output_path(work, f"diagnosis_who5_pass_{pass_number}", "who5.yaml")
    if not path.is_file():
        raise ValueError(f"WHO output missing: {path}")
    cleaned = staged._sanitize_proforma_text(work, f"self-who{pass_number}", path.read_text(encoding="utf-8"))
    path.write_text(cleaned, encoding="utf-8")
    schema_validation.validate_who5_diagnosis(cleaned, allowed_diseases=allowed, valid_variants=set(reg))
    return read_yaml(path)


def prepare_icc(work: Path, *, prompt: Path | None = None) -> dict:
    """Prepare isolated ICC. WHO1 is validated for routing only and never exposed."""
    work = Path(work)
    case, reg = load_case_registry(work)
    who1 = committed_who1(work, required=False) or accept_who(work, pass_number=1)
    who2_path = output_path(work, "diagnosis_who5_pass_2", "who5.yaml")
    who = accept_who(work, pass_number=2) if who2_path.is_file() else who1
    _all_cards, eligible, _digest, manifest = corpus_state(work)
    history = list(case.get("bootstrap_cmcs") or [])
    for cmc in runtime.derive_cmcs(who1):
        if cmc not in history:
            history.append(cmc)
    cards = staged._diagnostic_cards(eligible, runtime.case_genes(case), history, "icc")
    group = "self_icc_input"
    cards_md, _ = _write_pool(work, group, cards, manifest, diagnosis_authority="icc")
    finite = output_path(work, group, "finite-membership.yaml")
    write_yaml(finite, staged._finite_membership_context(reg, cards, card_identity.tag_by_id(manifest)))
    context = output_path(work, group, "context.yaml")
    write_yaml(context, {
        "starting_morphologic_diagnosis": case.get("provisional_disease"),
        "morphologic_diagnosis_origin": case.get("morphologic_diagnosis_origin"),
        "structured_case": case,
        "variant_registry": reg,
        "retrieval_cmcs": history,
        "who5_context": who,
    })
    return {
        "pass": "icc",
        "contract": contract_path("diagnosis_icc"),
        "prompt": prompt,
        "context": context,
        "finite_membership": finite,
        "cards": cards_md,
        "output": output_path(work, "diagnosis_icc", "icc.yaml"),
    }


def accept_icc(work: Path) -> dict:
    _case, reg = load_case_registry(work)
    path = output_path(work, "diagnosis_icc", "icc.yaml")
    if not path.is_file():
        raise ValueError(f"ICC output missing: {path}")
    cleaned = staged._sanitize_proforma_text(work, "self-icc", path.read_text(encoding="utf-8"))
    path.write_text(cleaned, encoding="utf-8")
    schema_validation.validate_icc_diagnosis(cleaned, valid_variants=set(reg))
    return read_yaml(path)


def prepare_diagnosis_other(work: Path, *, prompt: Path | None = None) -> dict:
    work=Path(work); case,reg=load_case_registry(work)
    who1=committed_who1(work,required=False) or accept_who(work,pass_number=1)
    who2_path=output_path(work,'diagnosis_who5_pass_2','who5.yaml')
    who=accept_who(work,pass_number=2) if who2_path.is_file() else who1
    icc=accept_icc(work)
    _all,eligible,_digest,manifest=corpus_state(work)
    history=list(case.get('bootstrap_cmcs') or [])
    for result in (who1,who):
        for cmc in runtime.derive_cmcs(result):
            if cmc not in history: history.append(cmc)
    cards=staged._draw_diagnosis_cards(eligible,runtime.case_genes(case),history)
    group='self_diagnosis_other_input'; cards_md,_=_write_pool(work,group,cards,manifest)
    context=output_path(work,group,'context.yaml')
    write_yaml(context,{
        'structured_case':case,'variant_registry':reg,
        'primary_framework_diagnoses':{'who5':who,'icc':icc},
        'retrieval_cmcs':history,
    })
    return {
        'pass':'diagnosis_other','contract':contract_path('diagnosis_other'),'prompt':prompt,
        'context':context,'cards':cards_md,
        'output':output_path(work,'diagnosis_other','other.yaml'),
    }


def accept_diagnosis_other(work: Path) -> dict:
    _case,reg=load_case_registry(work); path=output_path(work,'diagnosis_other','other.yaml')
    if not path.is_file():
        return {'diagnosis':None,'variants':[],'reason':None}
    cleaned=staged._sanitize_proforma_text(work,'self-diagnosis-other',path.read_text(encoding='utf-8'))
    path.write_text(cleaned,encoding='utf-8')
    schema_validation.validate_second_diagnosis(cleaned,valid_variants=set(reg))
    return read_yaml(path)


def finalize_diagnosis(work: Path) -> dict:
    who1=committed_who1(work,required=False) or accept_who(work,pass_number=1); icc=accept_icc(work)
    who2_path=output_path(work,'diagnosis_who5_pass_2','who5.yaml')
    who2=accept_who(work,pass_number=2) if who2_path.is_file() else None
    who=who2 or who1; other=accept_diagnosis_other(work)
    relationship='same' if runtime.normalize_dx(who['diagnosis'])==runtime.normalize_dx(icc['diagnosis']) else 'different'
    authoritative=2 if who2 is not None else 1
    diagnosis={
        'who5':who,'icc':icc,'second_diagnosis':other,'relationship':relationship,
        'self_execution':{'who5_first_pass':who1,'who5_authoritative_pass':authoritative},
    }
    write_yaml(output_path(work,'diagnosis','diagnosis-final.yaml'),diagnosis)
    history=list(load_case_registry(work)[0].get('bootstrap_cmcs') or [])
    for result in (who1,who):
        for cmc in runtime.derive_cmcs(result):
            if cmc not in history: history.append(cmc)
    route={
        'bootstrap_cmcs':load_case_registry(work)[0].get('bootstrap_cmcs') or [],
        'who5_authoritative_pass':authoritative,
        'final_cmcs':runtime.derive_cmcs(who),'diagnostic_cmc_history':history,
    }
    write_json(output_path(work,'diagnosis','routing.json'),route)
    return diagnosis


def prepare_ptbg(work: Path, *, domains: tuple[str, ...] | list[str] | None = None, prompts: dict[str, Path] | None = None, contracts: dict | None = None) -> dict:
    """Prepare the YAML-selected ready PTBG operations for one self handoff."""
    work = Path(work)
    case, reg = load_case_registry(work)
    diagnosis = finalize_diagnosis(work)
    _all_cards, eligible, _digest, manifest = corpus_state(work)
    disease = diagnosis["who5"]["schema_disease"]
    tag_by_id = card_identity.tag_by_id(manifest)
    outputs = {}
    genes = runtime.case_genes(case)
    domains = tuple(domains or ("prognosis", "treatment", "biomarker", "germline"))
    prompts = prompts or {}
    contracts = contracts or {}
    for domain in domains:
        cards = staged._draw_domain_cards(eligible, domain, genes, [disease])
        staged._log_ptbg_retrieval(work, eligible, domain, genes, disease, cards)
        group = f"self_ptbg_{domain}_input"
        cards_md, _ = _write_pool(work, group, cards, manifest)
        skeleton = output_path(work, group, "output-contract.md")
        skeleton.write_text(
            domain_contract.skeleton(
                contracts.get(domain,domain_contract.contract(domain)), sorted(reg), registry=reg, applicable_disease=disease
            ),
            encoding="utf-8",
        )
        context = output_path(work, group, "context.yaml")
        write_yaml(context, {
            "structured_case": {k: case.get(k) for k in model_context.DOMAIN_CASE_FIELDS},
            "variant_registry": reg,
            "authoritative_framework_diagnoses": {
                "who5": {k: diagnosis["who5"].get(k) for k in ("schema_disease", "diagnosis", "variants", "diagnostic_effect", "reason")},
                "icc": {k: diagnosis["icc"].get(k) for k in ("diagnosis", "variants", "diagnostic_effect", "reason")},
            },
        })
        outputs[domain] = {
            "contract": contract_path(domain),
            "prompt": prompts.get(domain),
            "context": context,
            "cards": cards_md,
            "output_contract": skeleton,
            "output": output_path(work, f"{domain}_state", "model-classification.yaml"),
        }
    return {"pass": "ptbg", "domains": outputs}


def accept_ptbg(work: Path, *, domains_to_accept: tuple[str, ...] | list[str] | None = None, contracts: dict | None = None, specs: dict | None = None) -> dict[str, dict]:
    _case, reg = load_case_registry(work)
    domains = {}
    contracts=contracts or {}; specs=specs or {}
    for domain in tuple(domains_to_accept or ("prognosis", "treatment", "biomarker", "germline")):
        model_path = output_path(work, f"{domain}_state", "model-classification.yaml")
        if not model_path.is_file():
            raise ValueError(f"{domain} model output missing: {model_path}")
        cleaned = staged._sanitize_proforma_text(work, f"self-{domain}", model_path.read_text(encoding="utf-8"), preserve_card_assignments=True)
        disease = finalize_diagnosis(work)["who5"]["schema_disease"]
        contract=contracts.get(domain,domain_contract.contract(domain))
        normalized, identity_records = domain_contract.normalize_model_output(
            cleaned, contract, reg, disease
        )
        if identity_records:
            staged._log_transforms(work, [dict(record, stage=f"self-{domain}") for record in identity_records])
        model_path.write_text(normalized, encoding="utf-8")
        _all, eligible, _digest, manifest = corpus_state(work)
        cards = staged._draw_domain_cards(eligible, domain, runtime.case_genes(load_case_registry(work)[0]), [disease])
        tag_by_id = card_identity.tag_by_id(manifest)
        owner_card_tags=[f"[card:{tag_by_id[c['card_id']]}]" for c in cards]
        domain_contract.validate(normalized,contract,{"variants":sorted(reg),"registry":reg,"authoritative_disease":disease,"owner_card_tags":owner_card_tags},spec=specs.get(domain))
        flat = read_yaml(model_path)
        doc = domain_contract.pivot(flat, contract)
        doc, merges = staged._consolidate_rows(domain, doc, reg, contract)
        staged._log_transforms(work, merges)
        write_yaml(output_path(work, f"{domain}_state", "proforma.yaml"), doc)
        domains[domain] = doc
    return domains


def load_domains(work: Path) -> dict[str, dict]:
    return {d: read_yaml(output_path(work, f"{d}_state", "proforma.yaml")) for d in ("prognosis", "treatment", "biomarker", "germline")}



def _who1_artifact_path(work: Path, group: str, name: str, *, create: bool = False) -> Path:
    # Completion/hydration checks must be read-only.  Creating numbered
    # intermediate directories while merely probing downstream state corrupts
    # chronological artifact numbering and resume provenance.
    return staged.artifact_path(Path(work), group, name, create=create)


def _who1_routing_change_path(work: Path, *, create: bool = False) -> Path:
    return _who1_artifact_path(work, "diagnosis_who1_routing", "routing-change.yaml", create=create)


def _who1_gate_state_path(work: Path, *, create: bool = False) -> Path:
    return _who1_artifact_path(work, "diagnosis_who1_evidence", "state.yaml", create=create)


def _who1_gate_match_pass_path(work: Path, pass_number: int, *, create: bool = False) -> Path:
    return _who1_artifact_path(work, "diagnosis_who1_evidence", f"match-pass-{int(pass_number):02d}.yaml", create=create)


def _who1_gate_match_final_path(work: Path, *, create: bool = False) -> Path:
    return _who1_artifact_path(work, "diagnosis_who1_evidence", "assignment.yaml", create=create)


def _who1_gate_audit_path(work: Path, *, create: bool = False) -> Path:
    return _who1_artifact_path(work, "diagnosis_who1_evidence", "audit.yaml", create=create)


def _who1_gate_adjudication_path(work: Path, *, create: bool = False) -> Path:
    return _who1_artifact_path(work, "diagnosis_who1_evidence", "adjudication.yaml", create=create)


def _who1_commit_path(work: Path, *, create: bool = False) -> Path:
    return _who1_artifact_path(work, "diagnosis_who1_commit", "accepted-routing.yaml", create=create)


def assess_who1_routing_change(work: Path) -> dict:
    case, _reg = load_case_registry(work)
    who1 = accept_who(work, pass_number=1)
    previous_schema = runtime.vocab.canonical_case_disease(case.get("provisional_disease"))
    previous_cmcs = list(case.get("bootstrap_cmcs") or [])
    proposed_cmcs = runtime.derive_cmcs(who1)
    proposed_schema = who1.get("schema_disease")
    # The blocking gate protects downstream routing, not diagnostic wording.
    # A refinement such as AML -> AML-MR is not a routing change when the
    # schema disease/CMC route remains AML.  If the provisional free text is
    # not deterministically canonicalisable, rely on the bootstrap CMC change
    # rather than treating ``None -> proposed_schema`` as a change.
    schema_changed = previous_schema is not None and proposed_schema != previous_schema
    changed = schema_changed or proposed_cmcs != previous_cmcs
    doc = {
        "changed": bool(changed),
        "previous": {
            "diagnosis": case.get("provisional_disease"),
            "schema_disease": previous_schema,
            "cmcs": previous_cmcs,
            "origin": case.get("morphologic_diagnosis_origin"),
        },
        "proposed": {
            "diagnosis": who1.get("diagnosis"),
            "schema_disease": who1.get("schema_disease"),
            "cmcs": proposed_cmcs,
            "diagnostic_effect": who1.get("diagnostic_effect"),
        },
    }
    write_yaml(_who1_routing_change_path(work, create=True), doc)
    return doc


def _who1_gate_state(work: Path, *, max_match_passes: int) -> dict:
    path = _who1_gate_state_path(work)
    if path.is_file():
        state = read_yaml(path)
        recorded = int(state.get("max_match_passes", max_match_passes))
        if recorded != int(max_match_passes):
            raise ValueError(f"WHO1 evidence match pass count changed within run: state={recorded}, workflow={max_match_passes}")
        return state
    change = assess_who1_routing_change(work)
    who1 = accept_who(work, pass_number=1)
    case, _reg = load_case_registry(work)
    _all, eligible, digest, manifest = corpus_state(work)
    cards = staged._diagnostic_cards(eligible, runtime.case_genes(case), list(case.get("bootstrap_cmcs") or []), "who5")
    tag_by_id = card_identity.tag_by_id(manifest)
    item = {
        "evidence_id": "EWHO1",
        "schema_id": "DX-WHO1-ROUTING",
        "reason": who1.get("reason"),
        "statement": f"WHO5 proposed routing diagnosis: {who1.get('diagnosis')}.",
        "candidate_card_ids": [c["card_id"] for c in cards],
        "candidate_card_tags": [f"[card:{tag_by_id[c['card_id']]}]" for c in cards],
    }
    state = {
        "routing_change": change,
        "item": item,
        "catalog_card_ids": item["candidate_card_ids"],
        "corpus_sha256": digest,
        "max_match_passes": int(max_match_passes),
    }
    write_yaml(_who1_gate_state_path(work, create=True), state)
    return state


def prepare_who1_evidence_resolution(work: Path, *, max_match_passes: int = 2, prompt: Path | None = None) -> dict:
    state = _who1_gate_state(work, max_match_passes=max_match_passes)
    if not (state.get("routing_change") or {}).get("changed"):
        return {"complete": True, "required": False, "output": _who1_gate_match_final_path(work)}
    item = state["item"]
    final = _who1_gate_match_final_path(work)
    pass_docs = []
    for n in range(1, int(max_match_passes) + 1):
        path = _who1_gate_match_pass_path(work, n)
        if not path.is_file():
            break
        schema_validation.validate_evidence_match_batch(path.read_text(encoding="utf-8"), [{"evidence_id": item["evidence_id"], "candidate_card_tags": item["candidate_card_tags"]}])
        pass_docs.append(read_yaml(path))
        tags = list((pass_docs[-1].get("matches") or [{}])[0].get("card_tags") or [])
        if tags:
            write_yaml(_who1_gate_match_final_path(work, create=True), {"matches": [{"evidence_id": item["evidence_id"], "card_tags": tags}]})
            return {"complete": True, "required": True, "output": final}
    if len(pass_docs) >= int(max_match_passes):
        write_yaml(_who1_gate_match_final_path(work, create=True), {"matches": [{"evidence_id": item["evidence_id"], "card_tags": []}]})
        return {"complete": True, "required": True, "output": final}
    _all, _eligible, _digest, manifest = corpus_state(work)
    by_id = {c["card_id"]: c for c in _all}
    catalog = {cid: by_id[cid] for cid in state.get("catalog_card_ids") or [] if cid in by_id}
    tag_by_id = card_identity.tag_by_id(manifest)
    group = f"diagnosis_who1_evidence_match_{len(pass_docs)+1:02d}"
    facts = output_path(work, group, "facts.md")
    facts.write_text(_fact_blocks([item], catalog, tag_by_id, card_tags_field="candidate_card_tags"), encoding="utf-8")
    return {
        "complete": False, "required": True, "match_pass": len(pass_docs)+1,
        "contract": contract_path("evidence_match"), "prompt": prompt, "facts": facts, "items": facts,
        "output": _who1_gate_match_pass_path(work, len(pass_docs)+1, create=True),
    }


def accept_who1_evidence_resolution(work: Path) -> dict:
    path = _who1_gate_match_final_path(work)
    if not path.is_file():
        raise ValueError(f"WHO1 evidence assignment missing: {path}")
    state = read_yaml(_who1_gate_state_path(work)); item = state["item"]
    schema_validation.validate_evidence_match_batch(path.read_text(encoding="utf-8"), [{"evidence_id": item["evidence_id"], "candidate_card_tags": item["candidate_card_tags"]}])
    return read_yaml(path)


def prepare_who1_evidence_audit(work: Path, *, prompt: Path | None = None) -> dict:
    state = read_yaml(_who1_gate_state_path(work)); item=state["item"]
    assignment=accept_who1_evidence_resolution(work)
    tags=list((assignment.get("matches") or [{}])[0].get("card_tags") or [])
    out=_who1_gate_audit_path(work, create=True)
    if not tags:
        write_yaml(out,{"audits":[]}); return {"required":False,"output":out}
    _all,_eligible,_digest,manifest=corpus_state(work); by_id={c["card_id"]:c for c in _all}; tag_by_id=card_identity.tag_by_id(manifest); id_by_tag={f"[card:{tag}]":cid for cid,tag in tag_by_id.items()}
    catalog={id_by_tag[tag]:by_id[id_by_tag[tag]] for tag in tags if tag in id_by_tag and id_by_tag[tag] in by_id}
    row={"evidence_id":item["evidence_id"],"schema_id":item["schema_id"],"reason":item["reason"],"selected_card_tags":tags}
    facts=output_path(work,"diagnosis_who1_evidence_audit_input","facts.md"); facts.write_text(_fact_blocks([row],catalog,tag_by_id,card_tags_field="selected_card_tags"),encoding="utf-8")
    return {"required":True,"contract":contract_path("evidence_audit"),"prompt":prompt,"facts":facts,"items":facts,"output":out}


def accept_who1_evidence_audit(work: Path) -> dict:
    assignment=accept_who1_evidence_resolution(work); tags=list((assignment.get("matches") or [{}])[0].get("card_tags") or [])
    path=_who1_gate_audit_path(work)
    if not path.is_file(): raise ValueError(f"WHO1 evidence audit missing: {path}")
    schema_validation.validate_evidence_audit_batch(path.read_text(encoding="utf-8"), [{"evidence_id":"EWHO1","selected_card_tags":tags}] if tags else [])
    return read_yaml(path)


def who1_evidence_disputes(work: Path) -> tuple[list[str], list[dict]]:
    state=read_yaml(_who1_gate_state_path(work)); item=state["item"]
    assignment=accept_who1_evidence_resolution(work); selected=list((assignment.get("matches") or [{}])[0].get("card_tags") or [])
    audit=accept_who1_evidence_audit(work); rows=(audit.get("audits") or []); audits=(rows[0].get("card_audits") or []) if rows else []
    generic=[{"card_tag":r["card_tag"],"decision":"include" if r.get("card_is_element_of_reason") else "exclude","comments":r.get("comments") or []} for r in audits]
    result=evidence_engine.compare(claim={"evidence_id":"EWHO1","claim":item["reason"],"candidate_card_tags":item["candidate_card_tags"]},assigned_card_tags=selected,audit_rows=generic)
    for d in result["disputes"]: d["reason"]=item["reason"]; d["schema_id"]=item["schema_id"]
    return result["agreed_include"], result["disputes"]


def prepare_who1_evidence_adjudication(work: Path, *, prompt: Path | None = None) -> dict:
    agreed,disputes=who1_evidence_disputes(work); crop=output_path(work,"diagnosis_who1_evidence_adjudication_input","disputes.yaml"); blind=[{"evidence_id":d["evidence_id"],"schema_id":d.get("schema_id"),"reason":d["reason"],"card_tag":d["card_tag"]} for d in disputes]; write_yaml(crop,{"disputes":blind})
    if not disputes: return {"required":False,"disputes":crop,"output":_who1_gate_adjudication_path(work)}
    _all,_eligible,_digest,manifest=corpus_state(work); tag_by_id=card_identity.tag_by_id(manifest); id_by_tag={f"[card:{tag}]":cid for cid,tag in tag_by_id.items()}; by_id={c["card_id"]:c for c in _all}; ids=[]
    for row in disputes:
        cid=id_by_tag.get(row["card_tag"])
        if cid and cid not in ids: ids.append(cid)
    cards,_=_write_pool(work,"diagnosis_who1_evidence_adjudication_input",[by_id[cid] for cid in ids if cid in by_id],manifest)
    return {"required":True,"prompt":prompt,"disputes":crop,"cards":cards,"output":_who1_gate_adjudication_path(work, create=True)}


def commit_who1_routing(work: Path) -> dict:
    change=assess_who1_routing_change(work); who1=accept_who(work,pass_number=1); case,_reg=load_case_registry(work)
    accepted_tags=[]; rejected=False
    if change.get("changed"):
        assignment=accept_who1_evidence_resolution(work); selected=list((assignment.get("matches") or [{}])[0].get("card_tags") or [])
        audit=accept_who1_evidence_audit(work); agreed,disputes=who1_evidence_disputes(work); accepted_tags.extend(agreed)
        if disputes:
            apath=_who1_gate_adjudication_path(work)
            if not apath.is_file(): raise ValueError(f"WHO1 routing disagreement requires adjudication: {apath}")
            adjud=read_yaml(apath); evidence_engine.validate_adjudication(adjud,disputes)
            accepted_tags.extend([r["card_tag"] for r in adjud.get("adjudications") or [] if r.get("decision")=="include"])
        rejected=not bool(accepted_tags)
    accepted_who1=who1
    fallback=False
    if rejected:
        if case.get("morphologic_diagnosis_origin") != "supplied":
            raise ValueError("WHO1 routing change failed blocking evidence support and the starting diagnosis was inferred; no deterministic fallback diagnosis is available")
        fallback_schema=runtime.vocab.canonical_case_disease(case.get("provisional_disease"))
        if not fallback_schema:
            raise ValueError("WHO1 routing change failed blocking evidence support and the supplied morphologic diagnosis cannot be deterministically mapped to a schema disease")
        accepted_who1={"schema_disease":fallback_schema,"diagnosis":case.get("provisional_disease"),"diagnostic_effect":"unchanged","variants":[],"reason":"The supplied morphologic diagnosis is retained unchanged because the proposed WHO5 routing change did not pass blocking evidence review."}
        fallback=True
        issue="who1-routing-evidence-rejected"
        staged._semantic_dissent(work,issue_key=issue,stage="WHO1 blocking diagnostic evidence",reviewed_text=f"Proposed WHO5 diagnosis: {who1.get('diagnosis')}",dissent_reason="The routing-changing WHO1 proposal did not retain any card after blocking evidence review.",action_recommended="Retain the supplied morphologic routing state and prevent rejected WHO1 CMC/schema disease from reaching downstream retrieval.")
        staged._semantic_dissent_address(work,issue_key=issue,stage="WHO1 routing commit",action="Reject proposed routing change and retain supplied morphology.",outcome=f"Committed routing diagnosis: {accepted_who1.get('diagnosis')}",status="resolved")
    doc={"accepted":not rejected,"fallback":fallback,"accepted_who1":accepted_who1,"routing_cmcs":runtime.derive_cmcs(accepted_who1),"evidence_card_tags":accepted_tags,"routing_change":change}
    write_yaml(_who1_commit_path(work, create=True),doc); return doc


def committed_who1(work: Path, *, required: bool = True) -> dict | None:
    path=_who1_commit_path(work)
    if not path.is_file():
        if required: raise ValueError(f"committed WHO1 routing missing: {path}")
        return None
    return read_yaml(path).get("accepted_who1")

def _evidence_state_path(work: Path) -> Path:
    return output_path(work, "self_evidence", "state.yaml")


def _evidence_match_pass_path(work: Path, pass_number: int) -> Path:
    return output_path(work, "evidence_matches", f"pass-{int(pass_number):02d}.yaml")


def _evidence_match_final_path(work: Path) -> Path:
    return output_path(work, "evidence_matches", "self-resolution.yaml")


def _fact_blocks(rows: list[dict], catalog: dict[str, dict], tag_by_id: dict[str, str], *, card_tags_field: str) -> str:
    """Render fact-local JSON blocks with no shared card catalogue.

    Each ``<fact-N>`` block is a complete reasoning envelope: one fact and only
    the cards eligible for that fact in this physical model pass.
    """
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in tag_by_id.items()}
    blocks = []
    for index, row in enumerate(rows, 1):
        cards = []
        for tag in row.get(card_tags_field) or []:
            cid = id_by_tag.get(tag)
            card = catalog.get(cid) if cid else None
            if card is None:
                raise ValueError(f"fact {row.get('evidence_id')} references unknown runtime card tag {tag}")
            cards.append({
                "card_id": tag,
                "rendered_card": staged._render_cards([card], tag_by_id),
            })
        payload = {
            "evidence_id": row["evidence_id"],
            "fact": row["reason"],
            "cards": cards,
        }
        blocks.append(
            f"<fact-{index}>\n"
            + json.dumps(payload, indent=2, ensure_ascii=False)
            + f"\n</fact-{index}>"
        )
    return "\n\n".join(blocks).rstrip() + ("\n" if blocks else "")


def _stable_tags(values) -> list[str]:
    out=[]
    for value in values or []:
        if isinstance(value,str) and value not in out:
            out.append(value)
    return out


def _evidence_match_round_path(work: Path, rescue_round: int, pass_number: int) -> Path:
    # Preserve the Phase-2B path for the first rescue round so existing run
    # tooling remains readable. Later semantic rescue rounds are namespaced.
    if int(rescue_round) <= 1:
        return _evidence_match_pass_path(work, pass_number)
    return output_path(work, "evidence_matches", f"rescue-{int(rescue_round):02d}-pass-{int(pass_number):02d}.yaml")


def _remaining_tags(item: dict, state: dict) -> list[str]:
    rejected=set((state.get("rejected_card_tags_by_evidence_id") or {}).get(item["evidence_id"]) or [])
    return [tag for tag in item.get("candidate_card_tags") or [] if tag not in rejected]


def _canonical_assignment_doc(state: dict) -> dict:
    accepted=state.get("accepted_card_tags_by_evidence_id") or {}
    current=state.get("current_assignment_by_evidence_id") or {}
    rows=[]
    for item in state.get("items") or []:
        eid=item["evidence_id"]
        rows.append({"evidence_id":eid,"card_tags":_stable_tags([*(accepted.get(eid) or []),*(current.get(eid) or [])])})
    return {"matches":rows}


def _initial_evidence_state(
    work: Path,
    *,
    contracts: dict | None = None,
    specs: dict | None = None,
    rescue_match_passes: int = 1,
    owner_assignment_domains: set[str] | None = None,
) -> dict:
    work = Path(work)
    case, reg = load_case_registry(work)
    diagnosis = finalize_diagnosis(work)
    contracts = contracts or {}
    specs = specs or {}
    domains = accept_ptbg(work, contracts=contracts, specs=specs)
    all_cards, eligible, digest, manifest = corpus_state(work)
    genes = runtime.case_genes(case)
    cmcs = list(case.get("bootstrap_cmcs") or [])
    for cmc in runtime.derive_cmcs(diagnosis["who5"]):
        if cmc not in cmcs:
            cmcs.append(cmc)
    cards_by_domain = {
        "diagnosis_who5": staged._diagnostic_cards(eligible, genes, cmcs, "who5"),
        "diagnosis_icc": staged._diagnostic_cards(eligible, genes, cmcs, "icc"),
    }
    disease = diagnosis["who5"]["schema_disease"]
    for domain in ("prognosis", "treatment", "biomarker", "germline"):
        cards_by_domain[domain] = staged._draw_domain_cards(eligible, domain, genes, [disease])
        staged._log_ptbg_retrieval(work, eligible, domain, genes, disease, cards_by_domain[domain])
    elements = staged._elements(diagnosis, domains, case, contracts=contracts)
    tag_by_id = card_identity.tag_by_id(manifest)
    owner_assignment_domains = set(owner_assignment_domains or {"prognosis","treatment","biomarker","germline"})
    # A supported routing-changing WHO1 decision already has blocking evidence.
    # Reuse that evidence as owner provenance for the WHO5 reportable element.
    who1_commit_path=_who1_commit_path(work)
    who1_gate_tags=[]
    if who1_commit_path.is_file():
        who1_gate_tags=_stable_tags((read_yaml(who1_commit_path) or {}).get("evidence_card_tags") or [])

    catalog = {}
    items = []
    no_candidates = []
    owner_seed: dict[str,list[str]] = {}
    owner_origin: dict[str,dict[str,dict]] = {}
    for el in elements:
        candidates = staged._candidate_cards(el, cards_by_domain, reg)
        if not candidates:
            no_candidates.append(el["schema_id"])
            continue
        eid = f"E{len(items)+1:04d}"
        for card in candidates:
            catalog[card["card_id"]] = card
        candidate_tags=[f"[card:{tag_by_id[c['card_id']]}]" for c in candidates]
        proposed=[]
        if el.get("domain") in owner_assignment_domains:
            proposed=_stable_tags(el.get("owner_card_tags") or [])
        elif el.get("schema_id")=="DX-WHO5" and who1_gate_tags:
            proposed=list(who1_gate_tags)
        # Only fact-eligible cards can become canonical owner assignments. A
        # tag outside the whole owner envelope was already rejected at the PTBG
        # owner validation boundary and fed back to that owner step.
        selected=[tag for tag in proposed if tag in set(candidate_tags)]
        owner_seed[eid]=selected
        owner_origin[eid]={tag:{"origin":"owner","rescue_round":0,"match_pass":0} for tag in selected}
        items.append({
            "evidence_id": eid,
            "schema_id": el["schema_id"],
            "reason": el["reason"],
            "statement": el["statement"],
            "candidate_card_ids": [c["card_id"] for c in candidates],
            "candidate_card_tags": candidate_tags,
            "owner_card_tags": selected,
        })
    state = {
        "elements": elements,
        "items": items,
        "no_candidate_schema_ids": no_candidates,
        "catalog_card_ids": list(catalog),
        "authoritative_disease": disease,
        "corpus_sha256": digest,
        "rescue_match_passes": int(rescue_match_passes),
        "rescue_round": 1,
        "owner_assignment_domains": sorted(owner_assignment_domains),
        "current_assignment_by_evidence_id": owner_seed,
        "accepted_card_tags_by_evidence_id": {x["evidence_id"]:[] for x in items},
        "rejected_card_tags_by_evidence_id": {x["evidence_id"]:[] for x in items},
        "assignment_meta_by_evidence_id": owner_origin,
        "audit_by_evidence_id": {},
        "unresolved_disputes": [],
        "processed_audit_sha256": None,
        "match_pass_by_evidence_id": {},
    }
    write_yaml(_evidence_state_path(work), state)
    return state


def prepare_evidence_resolution(
    work: Path,
    *,
    prompt: Path | None = None,
    contracts: dict | None = None,
    specs: dict | None = None,
    rescue_match_passes: int = 1,
    owner_assignment_domains: set[str] | None = None,
    # Backward-compatible keyword used by Phase-2B tests/commands. In Phase 3
    # these are rescue passes, because owner proformas are the initial assigner.
    max_match_passes: int | None = None,
) -> dict:
    """Canonicalize owner assignments and rescue only currently uncarded facts.

    Owner PTBG assignments are pass zero. Up to ``rescue_match_passes`` physical
    matcher passes are then used only for facts that still have no accepted or
    current assignment. A later audit rejection may invalidate this logical
    step; persistent state excludes rejected cards and starts a fresh rescue
    round without reusing the bad owner assignment.
    """
    work=Path(work)
    if max_match_passes is not None:
        rescue_match_passes=int(max_match_passes)
    rescue_match_passes=int(rescue_match_passes)
    if rescue_match_passes < 0:
        raise ValueError("rescue_match_passes must be >= 0")
    state_path=_evidence_state_path(work)
    if state_path.is_file():
        state=_load_evidence_state(work)
        recorded=int(state.get("rescue_match_passes",rescue_match_passes))
        if recorded != rescue_match_passes:
            raise ValueError(f"evidence rescue match pass count changed within run: state={recorded}, workflow={rescue_match_passes}")
    else:
        state=_initial_evidence_state(
            work,contracts=contracts,specs=specs,rescue_match_passes=rescue_match_passes,
            owner_assignment_domains=owner_assignment_domains,
        )
    final_path=_evidence_match_final_path(work)
    if final_path.is_file():
        return {"pass":"evidence_resolution","complete":True,"output":final_path,"rescue_round":int(state.get("rescue_round",1))}
    items=list(state.get("items") or [])
    if not items:
        write_yaml(final_path,{"matches":[]})
        return {"pass":"evidence_resolution","complete":True,"output":final_path,"rescue_match_passes_completed":0}

    accepted=state.get("accepted_card_tags_by_evidence_id") or {}
    current=state.get("current_assignment_by_evidence_id") or {}
    # Facts with accepted support or an un-audited owner/rescue assignment need
    # no matcher work. Only genuinely uncarded facts enter rescue.
    active=[item for item in items if not (accepted.get(item["evidence_id"]) or current.get(item["evidence_id"])) and _remaining_tags(item,state)]
    rescue_round=int(state.get("rescue_round",1))
    if not active or rescue_match_passes == 0:
        write_yaml(final_path,_canonical_assignment_doc(state))
        return {"pass":"evidence_resolution","complete":True,"output":final_path,"rescue_round":rescue_round,"zero_card_evidence_ids":[x["evidence_id"] for x in active]}

    unresolved_ids=[x["evidence_id"] for x in active]
    pass_docs=[]
    pass_by_eid=dict(state.get("match_pass_by_evidence_id") or {})
    for pass_number in range(1,rescue_match_passes+1):
        path=_evidence_match_round_path(work,rescue_round,pass_number)
        if not path.is_file():
            break
        active_now=[item for item in active if item["evidence_id"] in unresolved_ids]
        validation_items=[{"evidence_id":i["evidence_id"],"candidate_card_tags":_remaining_tags(i,state)} for i in active_now]
        schema_validation.validate_evidence_match_batch(path.read_text(encoding="utf-8"),validation_items)
        doc=read_yaml(path); pass_docs.append(doc)
        mmap={m["evidence_id"]:m for m in doc.get("matches") or []}
        next_unresolved=[]
        for item in active_now:
            eid=item["evidence_id"]
            tags=_stable_tags((mmap.get(eid) or {}).get("card_tags") or [])
            if tags:
                current[eid]=tags
                meta=(state.setdefault("assignment_meta_by_evidence_id",{})).setdefault(eid,{})
                for tag in tags:
                    meta[tag]={"origin":"rescue","rescue_round":rescue_round,"match_pass":pass_number}
                pass_by_eid[eid]=pass_number
            else:
                next_unresolved.append(eid)
        unresolved_ids=next_unresolved
        state["current_assignment_by_evidence_id"]=current
        state["match_pass_by_evidence_id"]=pass_by_eid
        write_yaml(state_path,state)
        if not unresolved_ids:
            break

    completed_passes=len(pass_docs)
    if not unresolved_ids or completed_passes >= rescue_match_passes:
        write_yaml(final_path,_canonical_assignment_doc(state))
        return {"pass":"evidence_resolution","complete":True,"output":final_path,"rescue_round":rescue_round,"rescue_match_passes_completed":completed_passes,"zero_card_evidence_ids":unresolved_ids}

    next_pass=completed_passes+1
    active_now=[item for item in active if item["evidence_id"] in unresolved_ids]
    all_cards,_eligible,_digest,manifest=corpus_state(work)
    by_id={card["card_id"]:card for card in all_cards}
    tag_by_id=card_identity.tag_by_id(manifest)
    id_by_tag={f"[card:{tag}]":cid for cid,tag in tag_by_id.items()}
    catalog={}
    public_rows=[]
    for item in active_now:
        tags=_remaining_tags(item,state)
        for tag in tags:
            cid=id_by_tag.get(tag)
            if cid in by_id: catalog[cid]=by_id[cid]
        public_rows.append({"evidence_id":item["evidence_id"],"schema_id":item["schema_id"],"reason":item["reason"],"candidate_card_tags":tags})
    group=f"self_evidence_resolution_input_rescue_{rescue_round:02d}_pass_{next_pass:02d}"
    facts_path=output_path(work,group,"facts.md")
    facts_path.write_text(_fact_blocks(public_rows,catalog,tag_by_id,card_tags_field="candidate_card_tags"),encoding="utf-8")
    return {
        "pass":"evidence_resolution","complete":False,"match_pass":next_pass,"rescue_round":rescue_round,
        "max_match_passes":rescue_match_passes,"rescue_match_passes":rescue_match_passes,"fact_count":len(public_rows),
        "contract":contract_path("evidence_match"),"prompt":prompt,"facts":facts_path,"items":facts_path,
        "output":_evidence_match_round_path(work,rescue_round,next_pass),
        "validation_items":[{"evidence_id":r["evidence_id"],"candidate_card_tags":r["candidate_card_tags"]} for r in public_rows],
    }

def _load_evidence_state(work: Path) -> dict:
    return read_yaml(_evidence_state_path(work))


def accept_evidence_resolution(work: Path) -> dict:
    state = _load_evidence_state(work)
    path = _evidence_match_final_path(work)
    if not path.is_file():
        raise ValueError(f"evidence-resolution final output missing: {path}")
    items = [{"evidence_id": x["evidence_id"], "candidate_card_tags": x["candidate_card_tags"]} for x in state["items"]]
    schema_validation.validate_evidence_match_batch(path.read_text(encoding="utf-8"), items)
    return read_yaml(path)


def audit_targets(items: list[dict], matches: dict, state: dict | None = None) -> list[dict]:
    """Audit only positively assigned cards that have not already passed audit."""
    mmap = {m["evidence_id"]: m for m in matches.get("matches") or []}
    accepted=(state or {}).get("accepted_card_tags_by_evidence_id") or {}
    out = []
    for item in items:
        eid=item["evidence_id"]
        selected = list((mmap.get(eid) or {}).get("card_tags") or [])
        selected=[tag for tag in selected if tag not in set(accepted.get(eid) or [])]
        if not selected:
            continue
        out.append({
            "evidence_id": eid,
            "schema_id": item["schema_id"],
            "reason": item["reason"],
            "resolution_card_tags": selected,
            "selected_card_tags": selected,
            "audit_scope": "assigned_only",
        })
    return out


def _assert_audit_targets_applicable(work: Path, state: dict, targets: list[dict]) -> None:
    """Re-check PTBG disease/domain scope immediately before semantic audit."""
    _case, reg = load_case_registry(work)
    disease = state.get("authoritative_disease") or finalize_diagnosis(work)["who5"]["schema_disease"]
    elements = {el["schema_id"]: el for el in state.get("elements") or []}
    all_cards, _eligible, _digest, manifest = corpus_state(work)
    by_id = {c["card_id"]: c for c in all_cards}
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in card_identity.tag_by_id(manifest).items()}
    for target in targets:
        el = elements.get(target["schema_id"])
        if not el or el.get("domain") == "diagnosis":
            continue
        for tag in target.get("selected_card_tags") or []:
            cid = id_by_tag.get(tag)
            card = by_id.get(cid)
            if card is None:
                raise ValueError(f"evidence audit references unknown runtime card tag {tag}")
            staged._assert_ptbg_audit_card_applicable(card, el, reg, disease)


def prepare_evidence_audit(work: Path, *, prompt: Path | None = None) -> dict:
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    targets = audit_targets(state["items"], matches, state)
    _assert_audit_targets_applicable(work, state, targets)
    output = output_path(work, "evidence_audits", "self-audit.yaml")
    if not targets:
        write_yaml(output, {"audits": []})
        return {"pass": "evidence_audit", "required": False, "output": output, "targets": []}

    all_cards, _eligible, _digest, manifest = corpus_state(work)
    by_id = {c["card_id"]: c for c in all_cards}
    tag_by_id = card_identity.tag_by_id(manifest)
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in tag_by_id.items()}
    catalog = {}
    for target in targets:
        for tag in target["selected_card_tags"]:
            cid = id_by_tag.get(tag)
            if cid in by_id:
                catalog[cid] = by_id[cid]
    group = "self_evidence_audit_input"
    facts_path = output_path(work, group, "facts.md")
    facts_path.write_text(
        _fact_blocks(targets, catalog, tag_by_id, card_tags_field="selected_card_tags"),
        encoding="utf-8",
    )
    return {
        "pass": "evidence_audit",
        "required": True,
        "contract": contract_path("evidence_audit"),
        "prompt": prompt,
        "facts": facts_path,
        "items": facts_path,
        "output": output,
        "targets": targets,
    }


def accept_evidence_audit(work: Path) -> tuple[dict, list[dict]]:
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    targets = audit_targets(state["items"], matches, state)
    path = output_path(work, "evidence_audits", "self-audit.yaml")
    if not path.is_file():
        raise ValueError(f"evidence-audit output missing: {path}")
    _assert_audit_targets_applicable(work, state, targets)
    validation_items = [{"evidence_id": x["evidence_id"], "selected_card_tags": x["selected_card_tags"]} for x in targets]
    schema_validation.validate_evidence_audit_batch(path.read_text(encoding="utf-8"), validation_items)
    return read_yaml(path), targets


def _audit_sha256(path: Path) -> str:
    import hashlib
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_evidence_audit(work: Path) -> dict:
    """Commit audit decisions to persistent evidence state exactly once.

    Passed cards become accepted support. Failed cards are excluded from later
    rescue matching. If the fact has no accepted card and eligible alternatives
    remain, the workflow review predicate sends ``evidence.assignment`` back for
    another rescue round. Otherwise the failed pair remains available for final
    cropped adjudication.
    """
    work=Path(work)
    state=_load_evidence_state(work)
    path=output_path(work,"evidence_audits","self-audit.yaml")
    audit,targets=accept_evidence_audit(work)
    digest=_audit_sha256(path)
    if state.get("processed_audit_sha256")==digest:
        return state
    accepted=state.setdefault("accepted_card_tags_by_evidence_id",{})
    rejected=state.setdefault("rejected_card_tags_by_evidence_id",{})
    current=state.setdefault("current_assignment_by_evidence_id",{})
    audit_state=state.setdefault("audit_by_evidence_id",{})
    disputes=list(state.get("unresolved_disputes") or [])
    item_by_eid={x["evidence_id"]:x for x in state.get("items") or []}
    audit_rows={a["evidence_id"]:a.get("card_audits") or [] for a in audit.get("audits") or []}
    rejected_this_audit=set()
    for target in targets:
        eid=target["evidence_id"]
        rows=audit_rows.get(eid,[])
        by_tag=audit_state.setdefault(eid,{})
        for row in rows:
            tag=row["card_tag"]
            by_tag[tag]=row
            if row.get("card_is_element_of_reason"):
                if tag not in accepted.setdefault(eid,[]): accepted[eid].append(tag)
                if tag in rejected.setdefault(eid,[]): rejected[eid].remove(tag)
            else:
                if tag not in rejected.setdefault(eid,[]): rejected[eid].append(tag)
                rejected_this_audit.add(eid)
                key=(eid,tag)
                if not any((d.get("evidence_id"),d.get("card_tag"))==key for d in disputes):
                    item=item_by_eid[eid]
                    disputes.append({
                        "evidence_id":eid,"schema_id":item["schema_id"],"reason":item["reason"],"card_tag":tag,
                        "resolver_decision":"include","auditor_decision":"exclude","audit_comments":row.get("comments") or [],
                    })
        # Every current assignment in this target has now been reviewed.
        current[eid]=[tag for tag in current.get(eid,[]) if tag not in set(target.get("selected_card_tags") or [])]
    # A later accepted rescue card resolves the need to adjudicate earlier bad
    # assignments for that fact; the bad cards remain rejected provenance.
    resolved_eids={eid for eid,tags in accepted.items() if tags}
    disputes=[d for d in disputes if d.get("evidence_id") not in resolved_eids]
    state["unresolved_disputes"]=disputes
    state["processed_audit_sha256"]=digest
    state["current_assignment_by_evidence_id"]=current
    state["accepted_card_tags_by_evidence_id"]=accepted
    state["rejected_card_tags_by_evidence_id"]=rejected
    needs=[]
    for item in state.get("items") or []:
        eid=item["evidence_id"]
        if eid not in rejected_this_audit or accepted.get(eid): continue
        if _remaining_tags(item,state): needs.append(eid)
    state["needs_rescue_evidence_ids"]=needs
    if needs:
        state["rescue_round"]=int(state.get("rescue_round",1))+1
    write_yaml(_evidence_state_path(work),state)
    return state


def evidence_audit_resolved(work: Path) -> bool:
    state=_load_evidence_state(work)
    return not bool(state.get("needs_rescue_evidence_ids") or [])


def compare_evidence(items: list[dict], matches: dict, audits: dict, targets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Compatibility view over the Phase-3 persistent audit state."""
    # This function remains for callers/tests that expect the old tuple shape.
    # Normal Phase-3 finalization uses persistent accepted/dispute state so a
    # rescued citation can resolve an earlier rejected owner assignment.
    mmap = {m["evidence_id"]: m for m in matches.get("matches") or []}
    amap = {a["evidence_id"]: a.get("card_audits") or [] for a in audits.get("audits") or []}
    agreed=[]; disputes=[]
    for item in items:
        eid=item["evidence_id"]
        audit_by={r["card_tag"]:r for r in amap.get(eid,[])}
        for tag in (mmap.get(eid) or {}).get("card_tags") or []:
            row=audit_by.get(tag)
            if not row: continue
            if row.get("card_is_element_of_reason"):
                agreed.append({"evidence_id":eid,"schema_id":item["schema_id"],"card_tag":tag,"audit":row})
            else:
                disputes.append({"evidence_id":eid,"schema_id":item["schema_id"],"reason":item["reason"],"card_tag":tag,"resolver_decision":"include","auditor_decision":"exclude","audit_comments":row.get("comments") or []})
    return agreed,disputes

def prepare_evidence_adjudication(work: Path, *, prompt: Path | None = None) -> dict:
    state=_load_evidence_state(work)
    # If an audit output exists but has not yet been committed (for example a
    # provider resumed after the model call), commit it before constructing the
    # final dispute barrier.
    apath=output_path(work,"evidence_audits","self-audit.yaml")
    if apath.is_file():
        apply_evidence_audit(work); state=_load_evidence_state(work)
    accepted=state.get("accepted_card_tags_by_evidence_id") or {}
    disputes=[d for d in (state.get("unresolved_disputes") or []) if not accepted.get(d["evidence_id"])]
    # Persist a compatibility/agreement view for audit/debug tooling.
    agreed=[]
    audit_by=state.get("audit_by_evidence_id") or {}
    item_by={x["evidence_id"]:x for x in state.get("items") or []}
    for eid,tags in accepted.items():
        for tag in tags or []:
            item=item_by.get(eid) or {}
            agreed.append({"evidence_id":eid,"schema_id":item.get("schema_id"),"card_tag":tag,"audit":(audit_by.get(eid) or {}).get(tag) or {"card_is_element_of_reason":True,"risk":"none","comments":[]}})
    write_yaml(output_path(work,"self_evidence","agreed.yaml"),{"assignments":agreed})
    crop=output_path(work,"self_evidence_adjudication_input","disputes.yaml")
    blind=[{"evidence_id":d["evidence_id"],"schema_id":d.get("schema_id"),"reason":d["reason"],"card_tag":d["card_tag"]} for d in disputes]
    write_yaml(crop,{"disputes":blind})
    if not disputes:
        return {"pass":"evidence_adjudication","required":False,"disputes":crop}
    all_cards,_eligible,_digest,manifest=corpus_state(work)
    tag_by_id=card_identity.tag_by_id(manifest); id_by_tag={f"[card:{tag}]":cid for cid,tag in tag_by_id.items()}; by_id={c["card_id"]:c for c in all_cards}
    ids=[]
    for row in disputes:
        cid=id_by_tag.get(row["card_tag"])
        if cid and cid not in ids: ids.append(cid)
    cards_md,_=_write_pool(work,"self_evidence_adjudication_input",[by_id[cid] for cid in ids if cid in by_id],manifest)
    return {"pass":"evidence_adjudication","required":True,"contract":ADJUDICATION_PROMPT,"prompt":prompt,"disputes":crop,"cards":cards_md,"output":output_path(work,"evidence_adjudication","adjudication.yaml")}

def validate_adjudication(doc: dict, disputes: list[dict]) -> None:
    evidence_engine.validate_adjudication(doc, disputes)

def _record_disputes(work: Path, disputes: list[dict], adjudications: dict | None) -> None:
    amap = {(x["evidence_id"], x["card_tag"]): x for x in (adjudications or {}).get("adjudications") or []}
    for row in disputes:
        issue = f"evidence-dispute:{row['evidence_id']}:{row['card_tag']}"
        staged._semantic_dissent(
            work,
            issue_key=issue,
            stage="evidence audit comparison",
            reviewed_text=f"Reason: {row['reason']}\nCard: {row['card_tag']}",
            dissent_reason=[f"Resolver: {row['resolver_decision']}; auditor: {row['auditor_decision']}." , *(row.get("audit_comments") or [])],
            action_recommended="Adjudicate only this cropped reason/card membership disagreement.",
        )
        decision = amap.get((row["evidence_id"], row["card_tag"]))
        if decision:
            staged._semantic_dissent_address(
                work,
                issue_key=issue,
                stage="evidence adjudication",
                action=f"Adjudicator decided to {decision['decision']} the disputed card.",
                outcome=decision["reason"],
                status="resolved",
            )


def finalize_evidence(work: Path) -> list[dict]:
    """Apply audited owner/rescue support and final adjudication deterministically."""
    work=Path(work)
    state=_load_evidence_state(work)
    audit_path=output_path(work,"evidence_audits","self-audit.yaml")
    if audit_path.is_file():
        apply_evidence_audit(work); state=_load_evidence_state(work)
    accepted={eid:_stable_tags(tags) for eid,tags in (state.get("accepted_card_tags_by_evidence_id") or {}).items()}
    disputes=[d for d in (state.get("unresolved_disputes") or []) if not accepted.get(d["evidence_id"])]
    adjudications=None
    if disputes:
        apath=output_path(work,"evidence_adjudication","adjudication.yaml")
        if not apath.is_file(): raise ValueError(f"evidence disagreements require adjudication output: {apath}")
        adjudications=read_yaml(apath); validate_adjudication(adjudications,disputes)
        for row in adjudications.get("adjudications") or []:
            if row.get("decision")=="include":
                accepted.setdefault(row["evidence_id"],[])
                if row["card_tag"] not in accepted[row["evidence_id"]]: accepted[row["evidence_id"]].append(row["card_tag"])
    _record_disputes(work,disputes,adjudications)

    all_cards,_eligible,_digest,manifest=corpus_state(work)
    by_id={c["card_id"]:c for c in all_cards}; id_by_tag={f"[card:{tag}]":cid for cid,tag in card_identity.tag_by_id(manifest).items()}
    audit_by=state.get("audit_by_evidence_id") or {}; meta_by=state.get("assignment_meta_by_evidence_id") or {}
    adjud_by={(x["evidence_id"],x["card_tag"]):x for x in (adjudications or {}).get("adjudications") or []}
    eid_by_schema={x["schema_id"]:x["evidence_id"] for x in state.get("items") or []}
    keep=[]
    for el in state.get("elements") or []:
        eid=eid_by_schema.get(el["schema_id"])
        tags=list(accepted.get(eid,[]) if eid else [])
        if tags:
            clone=dict(el); clone["evidence"]=[]
            for tag in tags:
                cid=id_by_tag.get(tag)
                if cid not in by_id: raise ValueError(f"accepted evidence references unknown runtime card tag {tag}")
                audit=(audit_by.get(eid) or {}).get(tag)
                adjud=adjud_by.get((eid,tag))
                if audit is None:
                    # Adjudicator may overturn an audit rejection; retain the
                    # original audit if available, otherwise make provenance
                    # explicit rather than pretending an independent pass.
                    audit={"card_is_element_of_reason": bool(adjud and adjud.get("decision")=="include"),"risk":"none","comments":[]}
                meta=(meta_by.get(eid) or {}).get(tag) or {}
                semantic_attempt=0 if meta.get("origin")=="owner" else int(meta.get("match_pass") or 1)
                ev=staged._accepted_evidence(by_id[cid],tag,audit,semantic_attempt)
                ev["assignment_origin"]=meta.get("origin") or ("adjudication" if adjud else "unknown")
                if meta.get("rescue_round") is not None: ev["rescue_round"]=meta.get("rescue_round")
                if adjud: ev["adjudication"]=adjud
                clone["evidence"].append(ev)
                if audit.get("risk")=="warning":
                    issue=f"evidence-warning:{el['schema_id']}:{tag}"
                    staged._semantic_dissent(work,issue_key=issue,stage="evidence audit",reviewed_text=el["reason"],dissent_reason=audit.get("comments") or ["Evidence fidelity/context warning."],action_recommended="Retain this supported card/reason match with dissent visible for review.")
                    staged._semantic_dissent_address(work,issue_key=issue,stage="evidence resolution",action="Retain supported card/reason match.",outcome="Membership passed; warning remains visible.",status="retained_with_dissent")
            keep.append(clone); continue
        reason="No candidate evidence card was available for this reportable proposition." if el["schema_id"] in state.get("no_candidate_schema_ids",[]) else "Owner assignment and configured rescue matching did not establish an audited supporting card for this proposition."
        resolved=staged._resolve_no_citation_support(work,el,attempt=max(1,int(state.get("rescue_round",1))),reason=reason)
        if resolved is not None: keep.append(resolved)
    order={el["schema_id"]:i for i,el in enumerate(state.get("elements") or [])}; keep.sort(key=lambda el:order.get(el["schema_id"],len(order)))
    write_yaml(output_path(work,"evidence_enriched","reportable-elements.yaml"),{"elements":keep}); staged._write_dissent(work)
    _write_evidence_metrics(work,state,accepted)
    return keep


def _write_evidence_metrics(work: Path, state: dict, accepted: dict[str,list[str]]) -> None:
    items=state.get("items") or []; owner=sum(1 for x in items if x.get("owner_card_tags")); rescued=0
    meta=state.get("assignment_meta_by_evidence_id") or {}
    for eid,tags in accepted.items():
        if any(((meta.get(eid) or {}).get(tag) or {}).get("origin")=="rescue" for tag in tags or []): rescued+=1
    rejected=sum(len(v or []) for v in (state.get("rejected_card_tags_by_evidence_id") or {}).values())
    doc={"claims":len(items),"owner_initially_carded":owner,"required_initial_rescue":sum(1 for x in items if not x.get("owner_card_tags")),"claims_with_rescued_support":rescued,"audit_rejected_card_count":rejected,"final_supported_claims":sum(1 for x in items if accepted.get(x["evidence_id"]))}
    write_yaml(output_path(work,"evidence_enriched","evidence-metrics.yaml"),doc)

def prepare_report(work: Path, *, prompt: Path | None = None) -> dict:
    work = Path(work)
    blocks_path = output_path(work, "report_blocks", "report-blocks.yaml")
    if not blocks_path.is_file():
        raise ValueError(
            f"report synthesis requires deterministic report blocks from the declared report.blocks operation: {blocks_path}"
        )
    blocks_doc = read_yaml(blocks_path)
    blocks = blocks_doc.get("blocks") if isinstance(blocks_doc, dict) else None
    schema_validation.validate_report_source_blocks(blocks)
    case, reg = load_case_registry(work)
    context = output_path(work, "self_report_input", "context.yaml")
    write_yaml(context, {"structured_case": case, "variant_registry": reg, "deterministic_report_blocks": blocks})
    return {
        "pass": "report_synthesis",
        "contract": contract_path("report_write"),
        "prompt": prompt,
        "case": layout.input(work, "case.md"),
        "context": context,
        "output": output_path(work, "report_write", "report-write.yaml"),
    }


def prepare_report_preservation(work: Path, *, prompt: Path | None = None) -> dict:
    work=Path(work)
    blocks=read_yaml(output_path(work,'report_blocks','report-blocks.yaml')).get('blocks') or []
    report_path=output_path(work,'report_write','report-write.yaml')
    if not report_path.is_file(): raise ValueError(f'report synthesis output missing: {report_path}')
    schema_validation.validate_report_write(report_path.read_text(encoding='utf-8'),blocks)
    rendered=read_yaml(report_path).get('blocks') or []
    context=output_path(work,'self_report_preservation_input','context.yaml')
    write_yaml(context,{'deterministic_source_blocks':blocks,'rendered_blocks':rendered})
    return {
        'pass':'report_preservation','contract':contract_path('report_preservation'),'prompt':prompt,
        'context':context,'output':output_path(work,'report_write','report-preservation.yaml'),
    }


def accept_report_preservation(work: Path) -> dict:
    blocks=read_yaml(output_path(work,'report_blocks','report-blocks.yaml')).get('blocks') or []
    path=output_path(work,'report_write','report-preservation.yaml')
    if not path.is_file(): return {}
    schema_validation.validate_preservation(path.read_text(encoding='utf-8'),blocks)
    return {a['block_id']:a for a in (read_yaml(path).get('audits') or [])}


def finalize_report(work: Path) -> Path:
    work=Path(work)
    blocks=read_yaml(output_path(work,'report_blocks','report-blocks.yaml')).get('blocks') or []
    report_path=output_path(work,'report_write','report-write.yaml')
    if not report_path.is_file(): raise ValueError(f'report synthesis output missing: {report_path}')
    schema_validation.validate_report_write(report_path.read_text(encoding='utf-8'),blocks)
    rendered=read_yaml(report_path)['blocks']
    audit_map=accept_report_preservation(work)
    final=staged.stage_report_finalize_blocks(work,blocks,rendered,audit_map=audit_map or None)
    case,_reg=load_case_registry(work)
    elements=read_yaml(output_path(work,'evidence_enriched','reportable-elements.yaml'))['elements']
    all_cards,_eligible,digest,manifest=corpus_state(work)
    staged.stage_final(work,case,final,elements,all_cards,digest,manifest)
    return work/'report-final.md'


DEBUG_ZIP_NAME = "ngs-report-debug.zip"
_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def package_debug_bundle(work: Path) -> Path:
    """Package the native-self run deterministically without changing shared workflow metadata.

    Every regular run artifact is included except ZIP files, so the debug bundle
    cannot recursively contain itself or the external-marking bundle.
    """
    work = Path(work).resolve()
    if not work.is_dir():
        raise ValueError(f"work directory not found: {work}")
    output = work / DEBUG_ZIP_NAME
    files = sorted(
        p for p in work.rglob("*")
        if p.is_file() and p.suffix.lower() != ".zip"
    )
    if not files:
        raise ValueError(f"no run artifacts available to package: {work}")
    with zipfile.ZipFile(output, "w") as zf:
        for path in files:
            info = zipfile.ZipInfo(path.relative_to(work).as_posix(), _ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            zf.writestr(info, path.read_bytes())
    return output


def final_artifacts(work: Path) -> dict[str, Path | None]:
    """Return only final artifacts that actually exist for deterministic CLI reporting."""
    work = Path(work).resolve()
    state = staged._load_run_state(work)
    mode = state.get("mode")
    case_id = state.get("validation_case")
    marking = None
    if mode in staged.VALIDATION_MODES and case_id:
        candidate = work / f"{staged.MARKING_PREFIX[mode]}-{case_id}.zip"
        marking = candidate if candidate.is_file() else None
    report = work / "report-final.md"
    report_json = work / "report-final.json"
    dissent = work / "dissent.md"
    debug = work / DEBUG_ZIP_NAME
    return {
        "REPORT": report if report.is_file() else None,
        "REPORT_JSON": report_json if report_json.is_file() else None,
        "MARKING_ZIP": marking,
        "DEBUG_ZIP": debug if debug.is_file() else None,
        "DISSENT": dissent if dissent.is_file() else None,
    }
