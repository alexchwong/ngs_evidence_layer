"""Legacy-v1 retrieval policy layered on shared retrieval mechanics."""
from __future__ import annotations

import json
from pathlib import Path

from scripts import retrieval_core as core

WORKFLOW_ID = "legacy-v1"


def step2(cards, genes, provisional_disease, case_facts=None, *, case_major_category=None):
    case_facts = core.validate_case_facts(case_facts or [])
    normalised_genes = core._normalise_genes(list(genes), field="genes")
    if not isinstance(provisional_disease, str) or not provisional_disease.strip():
        raise ValueError("provisional_disease must be a non-empty string")
    if case_major_category is None:
        case_major_category = core._infer_case_major_category_from_provisional(provisional_disease)
        if case_major_category is None:
            raise ValueError(
                "case_major_category is required when provisional_disease is not an exact canonical disease or alias"
            )
    core._validate_case_major_category(case_major_category, normalised_genes)
    wanted = set(normalised_genes)
    related_diseases = set(
        core.vocab.retrieval_related_diseases(case_major_category, "diagnosis")
        if case_major_category in core.vocab.DISEASE_SET else []
    )
    hits = []
    for card in cards:
        if card["category"] != "diagnosis":
            continue
        matched = core.match_genes(card, wanted)
        diseases = set(card["diseases"])
        major_category_matched = any(
            core.vocab.disease_matches_case_major_category(disease, case_major_category)
            for disease in diseases
        )
        related_matches = sorted(diseases & related_diseases)
        if not matched and not major_category_matched and not related_matches:
            continue
        hit = dict(card)
        hit["matched_genes"] = matched
        if major_category_matched:
            hit["matched_case_major_category"] = case_major_category
        if related_matches:
            hit["matched_retrieval_related_diseases"] = related_matches
        hits.append(hit)

    represented = {
        disease
        for hit in hits
        for disease in hit.get("diseases", [])
        if disease in core.vocab.DISEASE_SET
    }
    allowed = [disease for disease in core.vocab.DISEASES if disease in represented]
    if case_major_category in core.vocab.CASE_DISEASE_SET and case_major_category not in allowed:
        allowed.insert(0, case_major_category)
    if not allowed:
        raise ValueError(
            f"case_major_category {case_major_category!r} provides no allowed refined disease"
        )
    genes_with_diagnosis_card = {gene for hit in hits for gene in hit["matched_genes"]}
    return {
        "step": 2,
        "case_major_category": case_major_category,
        "provisional_disease": provisional_disease.strip(),
        "genes": sorted(wanted),
        "case_facts": case_facts,
        "diagnosis_cards": [
            core.step2_card_view(hit)
            for hit in sorted(hits, key=lambda item: item["card_id"])
        ],
        "allowed_refined_diseases": allowed,
        "genes_with_no_diagnosis_card": sorted(wanted - genes_with_diagnosis_card),
    }


def step4(
    cards, genes, refined_disease, diagnosis_cards, *, adjudication=None,
    case_major_category=None,
):
    normalised_genes = core._normalise_genes(list(genes), field="genes")
    core._validate_case_disease(refined_disease, normalised_genes, field="refined_disease")
    if case_major_category is None:
        case_major_category = core.vocab.preferred_case_major_category(refined_disease)
    if case_major_category is not None:
        core._validate_case_major_category(case_major_category, normalised_genes)
    wanted = set(normalised_genes)
    retrieved = []
    suppressed = []
    retrieval_scope = {
        category: core.vocab.retrieval_related_diseases(refined_disease, category)
        for category in core.DISEASE_FILTERED
    }
    diagnosis_by_id = {card["card_id"]: card for card in diagnosis_cards}
    if adjudication is None:
        selected_diagnosis_ids = set(diagnosis_by_id)
        carry_used_only = False
        broad_major_fallback = False
    else:
        selected_diagnosis_ids = core._adjudication_diagnosis_card_ids(adjudication)
        unknown_ids = selected_diagnosis_ids - set(diagnosis_by_id)
        if unknown_ids:
            raise ValueError(
                "adjudication uses diagnosis card(s) absent from Step 2: "
                + ", ".join(sorted(unknown_ids))
            )
        carry_used_only = True
        review = adjudication.get("user_review")
        effective_label = adjudication.get("diagnostic_label")
        if isinstance(review, dict) and review.get("decision") in {"agree", "disagree"}:
            effective_label = review.get("diagnostic_label")
        diagnosis_remains_broad = (
            case_major_category is not None
            and refined_disease == case_major_category
            and (effective_label is None or effective_label == refined_disease)
        )
        broad_major_fallback = (
            adjudication.get("status") == "indeterminate" or diagnosis_remains_broad
        )

    for card in cards:
        category = card["category"]
        matched = core.match_genes(card, wanted)
        hit = dict(card)
        hit["matched_genes"] = matched

        if category == "diagnosis":
            if card["card_id"] not in selected_diagnosis_ids:
                continue
            if carry_used_only:
                hit["retrieval_match"] = "adjudication_used"
                retrieved.append(hit)
                continue

        if category == "germline":
            if matched:
                hit["retrieval_match"] = "gene_only"
                retrieved.append(hit)
            continue
        if category not in core.DISEASE_FILTERED:
            continue

        diseases = card["diseases"]
        if not diseases:
            if matched:
                suppressed.append(hit)
            continue
        exact_match = refined_disease in diseases
        related = set(retrieval_scope.get(category, []))
        related_matches = [disease for disease in diseases if disease in related]
        major_matches = []
        if broad_major_fallback and case_major_category is not None:
            major_matches = [
                disease for disease in diseases
                if core.vocab.disease_matches_case_major_category(disease, case_major_category)
            ]
        disease_matched = exact_match or bool(related_matches) or bool(major_matches)
        geneless_allowed = not card["genes"] and category in {"diagnosis", "treatment"}
        if disease_matched and (matched or geneless_allowed):
            if exact_match:
                hit["retrieval_match"] = "exact_geneless" if geneless_allowed else "exact"
            elif related_matches:
                hit["retrieval_match"] = "related_geneless" if geneless_allowed else "related"
                hit["matched_retrieval_related_diseases"] = related_matches
            else:
                hit["retrieval_match"] = "major_category_geneless" if geneless_allowed else "major_category"
                hit["matched_case_major_category"] = case_major_category
            retrieved.append(hit)
            continue
        if matched:
            suppressed.append(hit)

    assessed = {gene for hit in retrieved for gene in hit["matched_genes"]}
    assessed |= {gene for hit in suppressed for gene in hit["matched_genes"]}
    not_assessed = sorted(wanted - assessed)
    by_disease = {}
    for hit in suppressed:
        for disease in hit["diseases"]:
            by_disease[disease] = by_disease.get(disease, 0) + 1
    return {
        "retrieval_scope": {
            "case_disease": refined_disease,
            "case_major_category": case_major_category,
            "broad_major_category_fallback": broad_major_fallback,
            "retrieval_related": retrieval_scope,
        },
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
            {"gene": gene, "reason": "no card in any category in this corpus version"}
            for gene in not_assessed
        ],
    }


def diagnosis(work_dir: Path) -> Path:
    case_input_path = work_dir / "case-input.json"
    output = work_dir / "diagnostic_evidence.md"
    case_input = core.validate_case_input(case_input_path)
    corpus, _index, digest = core.load_corpus(core.DEFAULT_CORPUS, core.DEFAULT_INDEX)
    cards = core.blacklist_cards(core.flatten(corpus), core.DEFAULT_BLACKLIST)
    result = step2(
        cards,
        case_input["genes"],
        case_input["provisional_disease"],
        case_input["case_facts"],
        case_major_category=case_input["case_major_category"],
    )
    global_tag_map = core.card_tags.build_card_tags(card["card_id"] for card in cards)
    result["card_tags"] = global_tag_map
    result["corpus"] = {"path": str(core.DEFAULT_CORPUS), "index": str(core.DEFAULT_INDEX)}
    result["provenance"] = core.provenance(
        corpus, core.DEFAULT_CORPUS, core.DEFAULT_INDEX, digest,
        [card["card_id"] for card in result["diagnosis_cards"]],
    )
    result["step3_instruction"] = (
        "Use workflows/legacy_v1/prompts/adjudicate_diagnosis.md to compare only case_facts with "
        "the retrieved diagnosis_cards. provisional_disease is the supplied free-text "
        "starting diagnosis; refined_disease must be one allowed canonical value. A "
        "change outside case_major_category requires fully met diagnostic criteria."
    )
    output.write_text(core.render_step_markdown(result), encoding="utf-8")
    core.write_step_json(result, output.with_suffix(".json"))
    return output


def downstream(work_dir: Path) -> Path:
    diagnosis_result = work_dir / "diagnostic_evidence.md"
    adjudication_result = work_dir / "adjudication.json"
    bundle_path = work_dir / "bundle.json"

    step2_result = core.load_step_json(diagnosis_result)
    adjudication_raw = json.loads(adjudication_result.read_text(encoding="utf-8"))
    adjudication = core.normalise_adjudication(
        step2_result, adjudication_raw, require_completed_review=True
    )
    corpus_path = Path(step2_result["corpus"]["path"])
    index_path = Path(step2_result["corpus"]["index"])
    corpus, _index, digest = core.load_corpus(corpus_path, index_path)
    provisional = step2_result["provisional_disease"]
    refined = adjudication["downstream_filter_disease"]
    genes = step2_result["genes"]
    cards = core.blacklist_cards(core.flatten(corpus), core.DEFAULT_BLACKLIST)
    eligible_card_ids = {card["card_id"] for card in cards}
    current_tag_map = core.card_tags.build_card_tags(eligible_card_ids)
    step2_tag_map = step2_result.get("card_tags")
    step2_tags = core.card_tags.tag_by_id(step2_tag_map or {})
    current_tags = core.card_tags.tag_by_id(current_tag_map)
    changed_tags = sorted(
        card_id for card_id in {card["card_id"] for card in step2_result["diagnosis_cards"]}
        if step2_tag_map and step2_tags.get(card_id) != current_tags.get(card_id)
    )
    if changed_tags:
        raise ValueError(
            "runtime card tags for Step-2 diagnosis evidence no longer match the current eligible corpus: "
            + ", ".join(changed_tags)
            + ". Rerun diagnosis and adjudication under the current corpus/blacklist before downstream retrieval."
        )
    newly_blocked_diagnosis = sorted(
        core._adjudication_diagnosis_card_ids(adjudication) - eligible_card_ids
    )
    if newly_blocked_diagnosis:
        raise ValueError(
            "blacklist excludes diagnosis card(s) used by the completed adjudication: "
            + ", ".join(newly_blocked_diagnosis)
            + ". Rerun diagnosis and adjudication under the current blacklist."
        )
    selected = step4(
        cards, genes, refined, step2_result["diagnosis_cards"],
        adjudication=adjudication,
        case_major_category=step2_result["case_major_category"],
    )
    result = {
        "step": 4,
        "workflow_profile": WORKFLOW_ID,
        "genes": sorted({gene.upper() for gene in genes}),
        "case_major_category": step2_result["case_major_category"],
        "provisional_disease": provisional,
        "refined_disease": refined,
        "diagnostic_adjudication": adjudication,
        "diagnostic_context": [
            dict(card) for card in cards
            if card["category"] == "diagnosis"
            and card["card_id"] in {item["card_id"] for item in step2_result["diagnosis_cards"]}
        ],
        "runtime_card_tags": current_tag_map,
        **selected,
    }
    result["provenance"] = core.provenance(
        corpus, corpus_path, index_path, digest,
        [card["card_id"] for card in result["retrieved"]],
    )
    bundle_path.write_text(json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return bundle_path
