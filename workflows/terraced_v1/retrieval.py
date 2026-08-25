"""Terraced-v1 broad-diagnosis and narrow-diagnosis retrieval policy."""
from __future__ import annotations

import json
from pathlib import Path

from scripts import vocab
from scripts.core import card_tags, corpus, provenance
from scripts.core import retrieval as core
from workflows.terraced_v1 import layout

WORKFLOW_ID = "terraced-v1"
DOMAIN_CATEGORY = {
    "prognosis": "prognosis",
    "treatment": "treatment",
    "mrd": "biomarker",
    "germline": "germline",
}


def _load_cards():
    corpus_doc, _index, digest = corpus.load_corpus(corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX)
    cards = corpus.blacklist_cards(corpus.flatten(corpus_doc), corpus.DEFAULT_BLACKLIST)
    return corpus_doc, digest, cards


def _read_case_input(work: Path) -> dict:
    path = layout.input(work, "case-input.json")
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid terraced case-input.json: {exc}") from exc
    return doc


def _diagnostic_selection(cards: list[dict], genes: list[str], cmcs: list[str]) -> list[dict]:
    wanted = {g.upper() for g in genes}
    hits = []
    for card in cards:
        matched_genes = core.match_genes(card, wanted)
        matched_cmcs = core._matches_case_major_category(card, cmcs)
        if card["category"] == "diagnosis":
            if not matched_genes and not matched_cmcs:
                continue
        elif card["category"] == "germline":
            if not matched_genes:
                continue
        else:
            continue
        hit = dict(card)
        hit["matched_genes"] = matched_genes
        if matched_cmcs:
            hit["matched_case_major_categories"] = matched_cmcs
        hit["retrieval_match"] = (
            "gene_and_case_major_category" if matched_genes and matched_cmcs
            else "gene_only" if matched_genes else "case_major_category"
        )
        hits.append(hit)
    return sorted(hits, key=lambda c: c["card_id"])


def diagnosis(work_dir: Path, cmcs: list[str] | None = None) -> Path:
    work = Path(work_dir).resolve()
    case = _read_case_input(work)
    genes = core._normalise_genes(case.get("genes", []), field="genes")
    current_cmcs = cmcs if cmcs is not None else case.get("provisional_cmcs")
    if not isinstance(current_cmcs, list) or not current_cmcs:
        raise ValueError("provisional_cmcs must be a non-empty list")
    for cmc in current_cmcs:
        core._validate_case_major_category(cmc, genes, field="provisional_cmcs")
    # Preserve configured order while deduplicating.
    current_cmcs = list(dict.fromkeys(current_cmcs))
    corpus_doc, digest, cards = _load_cards()
    selected = _diagnostic_selection(cards, genes, current_cmcs)
    tag_map = card_tags.build_card_tags(card["card_id"] for card in cards)
    result = {
        "step": 2,
        "workflow_profile": WORKFLOW_ID,
        "render_profile": "terraced",
        "terraced_domain": "diagnosis",
        "genes": genes,
        "provisional_cmcs": current_cmcs,
        "provisional_disease": case.get("provisional_disease", ""),
        "case_facts": case.get("case_facts", []),
        "accepted_schema_diseases": [],
        "diagnostic_context": [],
        "retrieved": selected,
        "runtime_card_tags": tag_map,
        "corpus": {"path": str(corpus.DEFAULT_CORPUS), "index": str(corpus.DEFAULT_INDEX)},
        "provenance": provenance.provenance(
            corpus_doc, corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX, digest,
            [card["card_id"] for card in selected],
        ),
    }
    output = layout.evidence(work, "evidence-diagnosis.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def _accepted_schema_diseases(work: Path) -> list[str]:
    path = layout.category(work, "category-diagnosis.yaml")
    if not path.is_file():
        raise ValueError("accepted diagnosis state is missing; complete diagnosis evidence alignment first")
    import yaml
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    diagnoses = (doc or {}).get("diagnoses") or []
    values = []
    for row in diagnoses:
        disease = row.get("schema_disease") if isinstance(row, dict) else None
        if not isinstance(disease, str) or disease not in vocab.CASE_DISEASE_SET:
            raise ValueError(f"invalid accepted schema disease in {path}: {disease!r}")
        values.append(disease)
    if not values:
        raise ValueError("accepted diagnosis state contains no diagnoses")
    return list(dict.fromkeys(values))


def _disease_matches(card: dict, schema_diseases: list[str], category: str) -> list[str]:
    card_diseases = set(card.get("diseases") or [])
    matches = []
    for disease in schema_diseases:
        allowed = {disease, *vocab.retrieval_related_diseases(disease, category)}
        if card_diseases & allowed:
            matches.append(disease)
    return matches


def downstream(work_dir: Path, domain: str = "prognosis") -> Path:
    if domain not in DOMAIN_CATEGORY:
        raise ValueError(f"unknown terraced downstream domain {domain!r}")
    work = Path(work_dir).resolve()
    case = _read_case_input(work)
    genes = core._normalise_genes(case.get("genes", []), field="genes")
    wanted = set(genes)
    schema_diseases = _accepted_schema_diseases(work)
    category = DOMAIN_CATEGORY[domain]
    corpus_doc, digest, cards = _load_cards()
    hits = []
    for card in cards:
        if card["category"] != category:
            continue
        matched_genes = core.match_genes(card, wanted)
        if category == "germline":
            if not matched_genes:
                continue
            matched_schema = []
        else:
            matched_schema = _disease_matches(card, schema_diseases, category)
            if not matched_schema:
                continue
            # Narrow exact-disease retrieval is the safety boundary. Prognostic and
            # biomarker framework cards may be geneless or broader within that exact
            # disease. Treatment cards with gene metadata remain variant-gated.
            if category == "treatment" and card.get("genes") and not matched_genes:
                continue
        hit = dict(card)
        hit["matched_genes"] = matched_genes
        if matched_schema:
            hit["matched_schema_diseases"] = matched_schema
        hit["retrieval_match"] = (
            "gene_only" if category == "germline"
            else "narrow_disease_and_gene" if matched_genes
            else "narrow_disease"
        )
        hits.append(hit)
    hits.sort(key=lambda c: c["card_id"])
    tag_map = card_tags.build_card_tags(card["card_id"] for card in cards)
    result = {
        "step": 5,
        "workflow_profile": WORKFLOW_ID,
        "render_profile": "terraced",
        "terraced_domain": domain,
        "genes": genes,
        "provisional_cmcs": case.get("provisional_cmcs", []),
        "accepted_schema_diseases": schema_diseases,
        "diagnostic_context": [],
        "retrieved": hits,
        "runtime_card_tags": tag_map,
        "corpus": {"path": str(corpus.DEFAULT_CORPUS), "index": str(corpus.DEFAULT_INDEX)},
        "provenance": provenance.provenance(
            corpus_doc, corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX, digest,
            [card["card_id"] for card in hits],
        ),
    }
    output = layout.evidence(work, f"evidence-{domain}.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output



def reportability_activation(work_dir: Path, schema_diseases: list[str]) -> Path:
    """Retrieve exact-disease guideline diagnosis cards for Step 6 target activation.

    This intentionally does not use gene matching: the diagnosis itself is the retrieval key.
    Only diagnosis cards tagged to the exact canonical disease and evidence_tier
    ``guideline criterion`` are eligible.
    """
    work = Path(work_dir).resolve()
    if not isinstance(schema_diseases, list):
        raise ValueError("reportability activation diagnoses must be a list")
    diagnoses = []
    for index, disease in enumerate(schema_diseases):
        if not isinstance(disease, str) or disease not in vocab.CASE_DISEASE_SET:
            raise ValueError(
                f"reportability activation diagnosis[{index}] is not a canonical schema disease: {disease!r}"
            )
        if disease not in diagnoses:
            diagnoses.append(disease)

    corpus_doc, digest, cards = _load_cards()
    hits = []
    for card in cards:
        if card.get("category") != "diagnosis":
            continue
        if card.get("evidence_tier") != "guideline criterion":
            continue
        matched = [disease for disease in diagnoses if disease in (card.get("diseases") or [])]
        if not matched:
            continue
        hit = dict(card)
        hit["matched_schema_diseases"] = matched
        hit["retrieval_match"] = "exact_diagnosis_activation"
        hits.append(hit)
    hits.sort(key=lambda c: c["card_id"])

    tag_map = card_tags.build_card_tags(card["card_id"] for card in cards)
    result = {
        "step": 6,
        "workflow_profile": WORKFLOW_ID,
        "render_profile": "terraced",
        "terraced_domain": "reportability_activation",
        "activation_schema_diseases": diagnoses,
        "retrieved": hits,
        "runtime_card_tags": tag_map,
        "corpus": {"path": str(corpus.DEFAULT_CORPUS), "index": str(corpus.DEFAULT_INDEX)},
        "provenance": provenance.provenance(
            corpus_doc, corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX, digest,
            [card["card_id"] for card in hits],
        ),
    }
    output = layout.evidence(work, "evidence-reportability-activation.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output

def combined(work_dir: Path) -> Path:
    """Build the final all-category evidence bundle used only for citation rendering."""
    work = Path(work_dir).resolve()
    corpus_doc, digest, cards = _load_cards()
    by_id = {}
    for domain in ("diagnosis", "prognosis", "treatment", "mrd", "germline"):
        path = layout.evidence(work, f"evidence-{domain}.json")
        if not path.is_file():
            continue
        doc = json.loads(path.read_text(encoding="utf-8"))
        for card in doc.get("retrieved", []):
            by_id.setdefault(card["card_id"], card)
    tag_map = card_tags.build_card_tags(card["card_id"] for card in cards)
    result = {
        "step": 6,
        "workflow_profile": WORKFLOW_ID,
        "render_profile": "terraced",
        "terraced_domain": "all",
        "genes": _read_case_input(work).get("genes", []),
        "accepted_schema_diseases": _accepted_schema_diseases(work),
        "diagnostic_context": [],
        "retrieved": sorted(by_id.values(), key=lambda c: c["card_id"]),
        "runtime_card_tags": tag_map,
        "corpus": {"path": str(corpus.DEFAULT_CORPUS), "index": str(corpus.DEFAULT_INDEX)},
        "provenance": provenance.provenance(
            corpus_doc, corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX, digest, sorted(by_id),
        ),
    }
    output = layout.evidence(work, "evidence-all.json")
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
