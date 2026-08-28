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
        who1 = read_yaml(output_path(work, "diagnosis_who5_pass_1", "who5.yaml"))
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
    who1 = accept_who(work, pass_number=1)
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
    who1=accept_who(work,pass_number=1)
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
    who1=accept_who(work,pass_number=1); icc=accept_icc(work)
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
        cleaned = staged._sanitize_proforma_text(work, f"self-{domain}", model_path.read_text(encoding="utf-8"))
        disease = finalize_diagnosis(work)["who5"]["schema_disease"]
        contract=contracts.get(domain,domain_contract.contract(domain))
        normalized, identity_records = domain_contract.normalize_model_output(
            cleaned, contract, reg, disease
        )
        if identity_records:
            staged._log_transforms(work, [dict(record, stage=f"self-{domain}") for record in identity_records])
        model_path.write_text(normalized, encoding="utf-8")
        domain_contract.validate(normalized,contract,{"variants":sorted(reg),"registry":reg,"authoritative_disease":disease},spec=specs.get(domain))
        flat = read_yaml(model_path)
        doc = domain_contract.pivot(flat, contract)
        doc, merges = staged._consolidate_rows(domain, doc, reg, contract)
        staged._log_transforms(work, merges)
        write_yaml(output_path(work, f"{domain}_state", "proforma.yaml"), doc)
        domains[domain] = doc
    return domains


def load_domains(work: Path) -> dict[str, dict]:
    return {d: read_yaml(output_path(work, f"{d}_state", "proforma.yaml")) for d in ("prognosis", "treatment", "biomarker", "germline")}


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


def _initial_evidence_state(work: Path, *, contracts: dict | None = None, specs: dict | None = None, max_match_passes: int = 1) -> dict:
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
    catalog = {}
    items = []
    no_candidates = []
    for el in elements:
        candidates = staged._candidate_cards(el, cards_by_domain, reg)
        if not candidates:
            no_candidates.append(el["schema_id"])
            continue
        eid = f"E{len(items)+1:04d}"
        for card in candidates:
            catalog[card["card_id"]] = card
        items.append({
            "evidence_id": eid,
            "schema_id": el["schema_id"],
            "reason": el["reason"],
            "statement": el["statement"],
            "candidate_card_ids": [c["card_id"] for c in candidates],
            "candidate_card_tags": [f"[card:{tag_by_id[c['card_id']]}]" for c in candidates],
        })
    state = {
        "elements": elements,
        "items": items,
        "no_candidate_schema_ids": no_candidates,
        "catalog_card_ids": list(catalog),
        "authoritative_disease": disease,
        "corpus_sha256": digest,
        "max_match_passes": int(max_match_passes),
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
    max_match_passes: int = 1,
) -> dict:
    """Advance evidence matching by at most one physical model pass.

    Pass 1 contains every fact. Each later pass is conditional and contains
    only facts that still have zero selected cards. The configured pass count
    is a workflow policy; all passes remain one logical ``evidence.assignment``
    operation.
    """
    work = Path(work)
    max_match_passes = int(max_match_passes)
    if max_match_passes < 1:
        raise ValueError("max_match_passes must be >= 1")
    state_path = _evidence_state_path(work)
    if state_path.is_file():
        state = _load_evidence_state(work)
        recorded = int(state.get("max_match_passes", max_match_passes))
        if recorded != max_match_passes:
            raise ValueError(
                f"evidence match pass count changed within run: state={recorded}, workflow={max_match_passes}"
            )
        if "max_match_passes" not in state:
            state["max_match_passes"] = max_match_passes
            state.setdefault("match_pass_by_evidence_id", {})
            write_yaml(state_path, state)
    else:
        state = _initial_evidence_state(
            work, contracts=contracts, specs=specs, max_match_passes=max_match_passes
        )

    final_path = _evidence_match_final_path(work)
    items = list(state.get("items") or [])
    if final_path.is_file():
        return {
            "pass": "evidence_resolution",
            "complete": True,
            "match_passes_completed": len([p for p in range(1, max_match_passes + 1) if _evidence_match_pass_path(work, p).is_file()]),
            "output": final_path,
        }
    if not items:
        write_yaml(final_path, {"matches": []})
        return {"pass": "evidence_resolution", "complete": True, "match_passes_completed": 0, "output": final_path}

    pass_docs = []
    unresolved_ids = [item["evidence_id"] for item in items]
    match_pass_by_eid = dict(state.get("match_pass_by_evidence_id") or {})
    for pass_number in range(1, max_match_passes + 1):
        path = _evidence_match_pass_path(work, pass_number)
        if not path.is_file():
            break
        active = [item for item in items if item["evidence_id"] in unresolved_ids]
        validation_items = [
            {"evidence_id": item["evidence_id"], "candidate_card_tags": item["candidate_card_tags"]}
            for item in active
        ]
        schema_validation.validate_evidence_match_batch(path.read_text(encoding="utf-8"), validation_items)
        doc = read_yaml(path)
        pass_docs.append(doc)
        before = set(unresolved_ids)
        merged, unresolved_ids = evidence_engine.merge_match_passes(items, pass_docs)
        resolved_now = before - set(unresolved_ids)
        for eid in resolved_now:
            match_pass_by_eid.setdefault(eid, pass_number)
        if not unresolved_ids:
            break

    merged, unresolved_ids = evidence_engine.merge_match_passes(items, pass_docs) if pass_docs else (
        {"matches": [{"evidence_id": item["evidence_id"], "card_tags": []} for item in items]},
        [item["evidence_id"] for item in items],
    )
    completed_passes = len(pass_docs)
    if not unresolved_ids or completed_passes >= max_match_passes:
        state["match_pass_by_evidence_id"] = match_pass_by_eid
        write_yaml(state_path, state)
        write_yaml(final_path, merged)
        return {
            "pass": "evidence_resolution",
            "complete": True,
            "match_passes_completed": completed_passes,
            "zero_card_evidence_ids": list(unresolved_ids),
            "output": final_path,
        }

    next_pass = completed_passes + 1
    active = [item for item in items if item["evidence_id"] in unresolved_ids]
    all_cards, _eligible, _digest, manifest = corpus_state(work)
    by_id = {card["card_id"]: card for card in all_cards}
    catalog_ids = set(state.get("catalog_card_ids") or [])
    catalog = {cid: by_id[cid] for cid in catalog_ids if cid in by_id}
    tag_by_id = card_identity.tag_by_id(manifest)
    public_rows = [
        {
            "evidence_id": item["evidence_id"],
            "schema_id": item["schema_id"],
            "reason": item["reason"],
            "candidate_card_tags": list(item["candidate_card_tags"]),
        }
        for item in active
    ]
    group = f"self_evidence_resolution_input_pass_{next_pass:02d}"
    facts_path = output_path(work, group, "facts.md")
    facts_path.write_text(
        _fact_blocks(public_rows, catalog, tag_by_id, card_tags_field="candidate_card_tags"),
        encoding="utf-8",
    )
    return {
        "pass": "evidence_resolution",
        "complete": False,
        "match_pass": next_pass,
        "max_match_passes": max_match_passes,
        "fact_count": len(public_rows),
        "contract": contract_path("evidence_match"),
        "prompt": prompt,
        "facts": facts_path,
        "items": facts_path,
        "output": _evidence_match_pass_path(work, next_pass),
        "validation_items": [
            {"evidence_id": row["evidence_id"], "candidate_card_tags": row["candidate_card_tags"]}
            for row in public_rows
        ],
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


def audit_targets(items: list[dict], matches: dict) -> list[dict]:
    """Audit only positively matched cards; false-negative rescue is match-pass work."""
    mmap = {m["evidence_id"]: m for m in matches.get("matches") or []}
    out = []
    for item in items:
        selected = list((mmap.get(item["evidence_id"]) or {}).get("card_tags") or [])
        claim = {"candidate_card_tags": list(item.get("candidate_card_tags") or [])}
        audit_tags = evidence_engine.audit_targets(claim, selected)
        if not audit_tags:
            continue
        out.append({
            "evidence_id": item["evidence_id"],
            "schema_id": item["schema_id"],
            "reason": item["reason"],
            "resolution_card_tags": selected,
            "selected_card_tags": audit_tags,
            "audit_scope": "resolver_selected",
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
    targets = audit_targets(state["items"], matches)
    _assert_audit_targets_applicable(work, state, targets)
    output = output_path(work, "evidence_audits", "self-audit.yaml")
    if not targets:
        write_yaml(output, {"audits": []})
        return {"pass": "evidence_audit", "required": False, "output": output}

    all_cards, _eligible, _digest, manifest = corpus_state(work)
    by_id = {c["card_id"]: c for c in all_cards}
    tag_by_id = card_identity.tag_by_id(manifest)
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in tag_by_id.items()}
    state_catalog = set(state.get("catalog_card_ids") or [])
    catalog = {}
    for target in targets:
        for tag in target["selected_card_tags"]:
            cid = id_by_tag.get(tag)
            if cid in state_catalog and cid in by_id:
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
    }


def accept_evidence_audit(work: Path) -> tuple[dict, list[dict]]:
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    targets = audit_targets(state["items"], matches)
    path = output_path(work, "evidence_audits", "self-audit.yaml")
    if not path.is_file():
        raise ValueError(f"evidence-audit output missing: {path}")
    _assert_audit_targets_applicable(work, state, targets)
    validation_items = [{"evidence_id": x["evidence_id"], "selected_card_tags": x["selected_card_tags"]} for x in targets]
    schema_validation.validate_evidence_audit_batch(path.read_text(encoding="utf-8"), validation_items)
    return read_yaml(path), targets


def compare_evidence(items: list[dict], matches: dict, audits: dict, targets: list[dict]) -> tuple[list[dict], list[dict]]:
    """Delegate disagreement semantics to the generic evidence engine."""
    mmap = {m["evidence_id"]: m for m in matches.get("matches") or []}
    amap = {a["evidence_id"]: a.get("card_audits") or [] for a in audits.get("audits") or []}
    agreed = []
    disputes = []
    for item in items:
        eid = item["evidence_id"]
        selected = list((mmap.get(eid) or {}).get("card_tags") or [])
        generic_audits = [
            {
                "card_tag": row["card_tag"],
                "decision": "include" if row.get("card_is_element_of_reason") else "exclude",
                "comments": row.get("comments") or [],
            }
            for row in amap.get(eid, [])
        ]
        result = evidence_engine.compare(
            claim={"evidence_id": eid, "claim": item["reason"], "candidate_card_tags": item.get("candidate_card_tags") or []},
            assigned_card_tags=selected,
            audit_rows=generic_audits,
        )
        audit_by_tag = {row["card_tag"]: row for row in amap.get(eid, [])}
        for tag in result["agreed_include"]:
            agreed.append({"evidence_id": eid, "schema_id": item["schema_id"], "card_tag": tag, "audit": audit_by_tag[tag]})
        for dispute in result["disputes"]:
            dispute["schema_id"] = item["schema_id"]
            dispute["reason"] = item["reason"]
            disputes.append(dispute)
    return agreed, disputes

def prepare_evidence_adjudication(work: Path, *, prompt: Path | None = None) -> dict:
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    audits, targets = accept_evidence_audit(work)
    agreed, disputes = compare_evidence(state["items"], matches, audits, targets)
    write_yaml(output_path(work, "self_evidence", "agreed.yaml"), {"assignments": agreed})
    crop = output_path(work, "self_evidence_adjudication_input", "disputes.yaml")
    write_yaml(crop, {"disputes": disputes})
    if not disputes:
        return {"pass": "evidence_adjudication", "required": False, "disputes": crop}
    # Card text is deliberately cropped to disputed cards only.
    all_cards, _eligible, _digest, manifest = corpus_state(work)
    tag_by_id = card_identity.tag_by_id(manifest)
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in tag_by_id.items()}
    by_id = {c["card_id"]: c for c in all_cards}
    ids = []
    for row in disputes:
        cid = id_by_tag[row["card_tag"]]
        if cid not in ids:
            ids.append(cid)
    cards_md, _ = _write_pool(work, "self_evidence_adjudication_input", [by_id[cid] for cid in ids], manifest)
    return {
        "pass": "evidence_adjudication",
        "required": True,
        "contract": ADJUDICATION_PROMPT,
        "prompt": prompt,
        "disputes": crop,
        "cards": cards_md,
        "output": output_path(work, "evidence_adjudication", "adjudication.yaml"),
    }


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
    """Apply agreement/adjudication deterministically and build supported elements."""
    work = Path(work)
    state = _load_evidence_state(work)
    matches = accept_evidence_resolution(work)
    audits, targets = accept_evidence_audit(work)
    agreed, disputes = compare_evidence(state["items"], matches, audits, targets)
    adjudications = None
    if disputes:
        apath = output_path(work, "evidence_adjudication", "adjudication.yaml")
        if not apath.is_file():
            raise ValueError(f"evidence disagreements require adjudication output: {apath}")
        adjudications = read_yaml(apath)
        validate_adjudication(adjudications, disputes)
    _record_disputes(work, disputes, adjudications)

    all_cards, _eligible, _digest, manifest = corpus_state(work)
    by_id = {c["card_id"]: c for c in all_cards}
    id_by_tag = {f"[card:{tag}]": cid for cid, tag in card_identity.tag_by_id(manifest).items()}
    assignment_rows = list(agreed)
    if adjudications:
        dmap = {(d["evidence_id"], d["card_tag"]): d for d in disputes}
        for row in adjudications["adjudications"]:
            if row["decision"] == "include":
                d = dmap[(row["evidence_id"], row["card_tag"])]
                assignment_rows.append({
                    "evidence_id": row["evidence_id"], "schema_id": d["schema_id"], "card_tag": row["card_tag"],
                    "audit": {"card_is_element_of_reason": d["auditor_decision"] == "include", "risk": "none", "comments": d.get("audit_comments") or []},
                    "adjudication": row,
                })
    assignments: dict[str, list[dict]] = {}
    for row in assignment_rows:
        assignments.setdefault(row["evidence_id"], []).append(row)

    item_by_schema = {x["schema_id"]: x for x in state["items"]}
    eid_by_schema = {x["schema_id"]: x["evidence_id"] for x in state["items"]}
    keep = []
    for el in state["elements"]:
        eid = eid_by_schema.get(el["schema_id"])
        rows = assignments.get(eid, []) if eid else []
        if rows:
            clone = dict(el)
            clone["evidence"] = []
            for row in rows:
                cid = id_by_tag[row["card_tag"]]
                match_pass=int((state.get('match_pass_by_evidence_id') or {}).get(eid, 1))
                evidence = staged._accepted_evidence(by_id[cid], row["card_tag"], row["audit"], match_pass)
                if row.get("adjudication"):
                    evidence["adjudication"] = row["adjudication"]
                clone["evidence"].append(evidence)
                if row["audit"].get("risk") == "warning":
                    issue = f"evidence-warning:{el['schema_id']}:{row['card_tag']}"
                    staged._semantic_dissent(
                        work, issue_key=issue, stage="evidence audit", reviewed_text=el["reason"],
                        dissent_reason=row["audit"].get("comments") or ["Evidence fidelity/context warning."],
                        action_recommended="Retain this supported card/reason match with dissent visible for review.",
                    )
                    staged._semantic_dissent_address(
                        work, issue_key=issue, stage="evidence resolution", action="Retain supported card/reason match.",
                        outcome="Membership passed; warning remains visible.", status="retained_with_dissent",
                    )
            keep.append(clone)
            continue
        reason = "No candidate evidence card was available for this reportable proposition." if el["schema_id"] in state.get("no_candidate_schema_ids", []) else "Configured evidence match passes did not establish a supported card for this proposition."
        resolved = staged._resolve_no_citation_support(work, el, attempt=1, reason=reason)
        if resolved is not None:
            keep.append(resolved)

    order = {el["schema_id"]: i for i, el in enumerate(state["elements"])}
    keep.sort(key=lambda el: order.get(el["schema_id"], len(order)))
    write_yaml(output_path(work, "evidence_enriched", "reportable-elements.yaml"), {"elements": keep})
    staged._write_dissent(work)
    return keep


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
