"""Categorical-v1 retrieval policy layered on shared retrieval mechanics."""
from __future__ import annotations

import json
from pathlib import Path

from scripts.core import card_tags, corpus, provenance
from scripts.core import retrieval as core

WORKFLOW_ID = "categorical-v1"


def step2(cards, genes, provisional_disease, case_facts, case_major_category):
    case_facts = core.validate_case_facts(case_facts or [])
    normalised_genes = core._normalise_genes(list(genes), field="genes")
    core._validate_case_major_category(case_major_category, normalised_genes)
    if not isinstance(provisional_disease, str) or not provisional_disease.strip():
        raise ValueError("provisional_disease must be a non-empty string")

    wanted = set(normalised_genes)
    retrieved = []
    for card in cards:
        matched_genes = core.match_genes(card, wanted)
        matched_cmcs = core._matches_case_major_category(card, [case_major_category])
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
            "gene_and_case_major_category"
            if matched_genes and matched_cmcs
            else "gene_only" if matched_genes
            else "case_major_category"
        )
        retrieved.append(hit)

    diagnosis_gene_hits = {
        gene
        for hit in retrieved
        if hit["category"] == "diagnosis"
        for gene in hit.get("matched_genes", [])
    }
    return {
        "genes": normalised_genes,
        "case_major_category": case_major_category,
        "provisional_disease": provisional_disease.strip(),
        "case_facts": case_facts,
        "retrieved": sorted(retrieved, key=lambda item: item["card_id"]),
        "genes_with_no_diagnosis_card": sorted(wanted - diagnosis_gene_hits),
    }


def step4(
    cards, genes, initial_case_major_category, refined_case_major_category,
    diagnostic_context,
):
    normalised_genes = core._normalise_genes(list(genes), field="genes")
    core._validate_case_major_category(
        initial_case_major_category,
        normalised_genes,
        field="initial_case_major_category",
    )
    core._validate_case_major_category(
        refined_case_major_category,
        normalised_genes,
        field="refined_case_major_category",
    )
    wanted = set(normalised_genes)
    cmc_changed = refined_case_major_category != initial_case_major_category
    diagnosis_cmcs = [initial_case_major_category, refined_case_major_category]
    retrieved = []
    suppressed = []

    for card in cards:
        category = card["category"]
        matched_genes = core.match_genes(card, wanted)
        hit = dict(card)
        hit["matched_genes"] = matched_genes

        if category == "germline":
            if matched_genes:
                hit["retrieval_match"] = "gene_only"
                retrieved.append(hit)
            continue

        if category == "diagnosis":
            if not cmc_changed:
                continue
            matched_cmcs = core._matches_case_major_category(card, diagnosis_cmcs)
            if matched_genes or matched_cmcs:
                if matched_cmcs:
                    hit["matched_case_major_categories"] = matched_cmcs
                hit["retrieval_match"] = (
                    "gene_and_case_major_category"
                    if matched_genes and matched_cmcs
                    else "gene_only" if matched_genes
                    else "case_major_category"
                )
                retrieved.append(hit)
            continue

        if category not in {"prognosis", "treatment", "biomarker"}:
            continue

        matched_cmcs = core._matches_case_major_category(card, [refined_case_major_category])
        disease_matched = bool(matched_cmcs)
        geneless_allowed = category == "treatment" and not card.get("genes")
        if disease_matched and (matched_genes or geneless_allowed):
            hit["matched_case_major_categories"] = matched_cmcs
            hit["retrieval_match"] = (
                "case_major_category_geneless"
                if geneless_allowed and not matched_genes
                else "gene_and_case_major_category"
            )
            retrieved.append(hit)
        elif matched_genes:
            suppressed.append(hit)

    assessed = {gene for hit in retrieved for gene in hit.get("matched_genes", [])}
    assessed |= {gene for hit in suppressed for gene in hit.get("matched_genes", [])}
    by_disease = {}
    for hit in suppressed:
        for disease in hit.get("diseases", []):
            by_disease[disease] = by_disease.get(disease, 0) + 1

    return {
        "retrieval_scope": {
            "initial_case_major_category": initial_case_major_category,
            "refined_case_major_category": refined_case_major_category,
            "case_major_category_changed": cmc_changed,
        },
        "diagnostic_context": [dict(card) for card in diagnostic_context],
        "retrieved": sorted(retrieved, key=lambda item: item["card_id"]),
        "suppressed": {
            "count": len(suppressed),
            "by_disease": dict(sorted(by_disease.items())),
            "cards": sorted(
                (
                    {
                        "card_id": hit["card_id"],
                        "genes": hit["genes"],
                        "diseases": hit["diseases"],
                        "category": hit["category"],
                    }
                    for hit in suppressed
                ),
                key=lambda item: item["card_id"],
            ),
        },
        "not_assessed": [
            {
                "gene": gene,
                "reason": "no eligible categorical downstream card in this corpus version",
            }
            for gene in sorted(wanted - assessed)
        ],
    }


def diagnosis(work_dir: Path) -> Path:
    case_input = core.validate_case_input(work_dir / "case-input.json")
    corpus_doc, _index, digest = corpus.load_corpus(corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX)
    cards = corpus.blacklist_cards(corpus.flatten(corpus_doc), corpus.DEFAULT_BLACKLIST)
    selected = step2(
        cards,
        case_input["genes"],
        case_input["provisional_disease"],
        case_input["case_facts"],
        case_input["case_major_category"],
    )
    global_tag_map = card_tags.build_card_tags(card["card_id"] for card in cards)
    result = {
        "step": 4,
        "workflow_profile": WORKFLOW_ID,
        "render_profile": "diagnosis_first_diagnosis",
        "genes": selected["genes"],
        "case_major_category": selected["case_major_category"],
        "initial_case_major_category": selected["case_major_category"],
        "refined_case_major_category": selected["case_major_category"],
        "provisional_disease": selected["provisional_disease"],
        "refined_disease": selected["case_major_category"],
        "case_facts": selected["case_facts"],
        "genes_with_no_diagnosis_card": selected["genes_with_no_diagnosis_card"],
        "diagnostic_context": [],
        "retrieved": selected["retrieved"],
        "runtime_card_tags": global_tag_map,
        "corpus": {"path": str(corpus.DEFAULT_CORPUS), "index": str(corpus.DEFAULT_INDEX)},
        "provenance": provenance.provenance(
            corpus_doc,
            corpus.DEFAULT_CORPUS,
            corpus.DEFAULT_INDEX,
            digest,
            [card["card_id"] for card in selected["retrieved"]],
        ),
        "suppressed": {"count": 0, "by_disease": {}, "cards": []},
        "not_assessed": [],
    }
    output = work_dir / "diagnostic_evidence.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output


def downstream(work_dir: Path) -> Path:
    # YAML parsing is diagnosis-first-only. Keep this import local so importing
    # shared retrieval code for legacy-v1 never requires PyYAML.
    from workflows.categorical_v1.runtime import extract_refined_cmc

    diagnosis_path = work_dir / "diagnostic_evidence.json"
    diagnosis_bundle = json.loads(diagnosis_path.read_text(encoding="utf-8"))
    if diagnosis_bundle.get("workflow_profile") != WORKFLOW_ID:
        raise ValueError(
            "categorical downstream retrieval requires diagnostic_evidence.json produced "
            "by categorical-v1"
        )
    initial_cmc = diagnosis_bundle.get("initial_case_major_category")
    refined_cmc = extract_refined_cmc(work_dir / "report-draft-dx.yaml")
    genes = diagnosis_bundle.get("genes", [])
    corpus_path = Path(diagnosis_bundle["corpus"]["path"])
    index_path = Path(diagnosis_bundle["corpus"]["index"])
    corpus_doc, _index, digest = corpus.load_corpus(corpus_path, index_path)
    cards = corpus.blacklist_cards(corpus.flatten(corpus_doc), corpus.DEFAULT_BLACKLIST)

    current_tag_map = card_tags.build_card_tags(card["card_id"] for card in cards)
    previous_tag_map = diagnosis_bundle.get("runtime_card_tags") or {}
    previous_tags = card_tags.tag_by_id(previous_tag_map)
    current_tags = card_tags.tag_by_id(current_tag_map)
    diagnosis_context = diagnosis_bundle.get("retrieved", [])
    changed_tags = sorted(
        card["card_id"]
        for card in diagnosis_context
        if previous_tags.get(card["card_id"]) != current_tags.get(card["card_id"])
    )
    if changed_tags:
        raise ValueError(
            "runtime card tags for categorical diagnosis evidence no longer match the current "
            "eligible corpus: " + ", ".join(changed_tags)
            + ". Rerun diagnosis before downstream retrieval."
        )
    eligible_ids = {card["card_id"] for card in cards}
    newly_blocked = sorted(
        card["card_id"] for card in diagnosis_context if card["card_id"] not in eligible_ids
    )
    if newly_blocked:
        raise ValueError(
            "blacklist now excludes categorical diagnosis evidence card(s): "
            + ", ".join(newly_blocked)
            + ". Rerun diagnosis under the current blacklist."
        )

    selected = step4(cards, genes, initial_cmc, refined_cmc, diagnosis_context)
    result = {
        "step": 4,
        "workflow_profile": WORKFLOW_ID,
        "render_profile": "diagnosis_first_downstream",
        "genes": sorted({gene.upper() for gene in genes}),
        "case_major_category": initial_cmc,
        "initial_case_major_category": initial_cmc,
        "refined_case_major_category": refined_cmc,
        "case_major_category_changed": refined_cmc != initial_cmc,
        "provisional_disease": diagnosis_bundle.get("provisional_disease"),
        "refined_disease": refined_cmc,
        "runtime_card_tags": current_tag_map,
        "corpus": {"path": str(corpus_path), "index": str(index_path)},
        "provenance": provenance.provenance(
            corpus_doc,
            corpus_path,
            index_path,
            digest,
            [card["card_id"] for card in selected["retrieved"]],
        ),
        **selected,
    }
    output = work_dir / "bundle.json"
    output.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return output
