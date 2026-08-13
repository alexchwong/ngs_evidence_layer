#!/usr/bin/env python3
"""Deterministic diagnosis and full-evidence retrieval.

Step 2 uses the Step-1 ``case_major_category`` for broad diagnosis recall. A
diagnosis card is eligible when it belongs to that major category, is linked by an
existing diagnosis ``retrieval_related`` rule, or matches a submitted gene. Gene
matching therefore remains disease-unrestricted and can still escape an incorrect
provisional category.

Step 4 carries forward only diagnosis cards actually used in adjudication. For
prognosis, treatment and biomarker evidence it retains the narrower gene + refined
-disease/``retrieval_related`` rule; when adjudication remains indeterminate or at
the original broad major category, the disease side may fall back to that major
category. Germline remains gene-only.
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocab  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CORPUS = REPO_ROOT / "output/corpus/nel.corpus.json"
DEFAULT_INDEX = REPO_ROOT / "output/corpus/nel.index.json"
DISEASE_FILTERED = ("diagnosis", "prognosis", "treatment", "biomarker")

def canonical_bytes(document):
    return (json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()

def load_corpus(corpus_path, index_path):
    """Load the corpus and refuse a stale index.
    A mismatched index means the postings and the cards disagree about what
    exists. Retrieval built on that is not wrong in an obvious way; it is wrong in
    a way that looks like an absence of evidence.
    """
    corpus = json.loads(Path(corpus_path).read_text(encoding="utf-8"))
    index = json.loads(Path(index_path).read_text(encoding="utf-8"))
    digest = hashlib.sha256(canonical_bytes(corpus)).hexdigest()
    if index.get("corpus_sha256") != digest:
        raise ValueError(
            f"index does not match corpus: corpus hashes to {digest}, index claims "
            f"{index.get('corpus_sha256')}. Rebuild before retrieving."
        )
    return corpus, index, digest

def flatten(corpus):
    """One record per card, carrying what render needs and nothing more."""
    cards = []
    for publication in corpus.get("publications", []):
        document = publication.get("document", {})
        citation = document.get("citation", {})
        for card in document.get("cards", []):
            cards.append({
                "card_id": card["card_id"],
                "category": card["category"],
                "genes": list(card.get("genes", [])),
                "diseases": list(card.get("diseases") or []),
                "evidence_tier": card["evidence_tier"],
                "interpretation": card["interpretation"],
                "locator": card["locator"],
                "publication_key": document.get("publication_key"),
                "paper_nickname": document.get("paper_nickname"),
                "publication_year": citation.get("year"),
                "citation_display": citation.get("display"),
                "citation_incomplete": citation.get("citation_incomplete") or [],
                "secondary_citation": card.get("secondary_citation"),
            })
    return cards

def match_genes(card, wanted):
    return sorted({gene.upper() for gene in card["genes"]} & wanted)

def provenance(corpus, corpus_path, index_path, digest, card_ids):
    return {
        "corpus_version": corpus.get("corpus_version"),
        "corpus_generated_at": corpus.get("generated_at"),
        "corpus_sha256": digest,
        "corpus_path": str(corpus_path),
        "index_path": str(index_path),
        "retrieved_at": datetime.now(timezone.utc).isoformat(),
        "card_ids": sorted(card_ids),
    }

def validate_case_facts(case_facts):
    if not isinstance(case_facts, list):
        raise ValueError("case_facts must be a JSON array")
    fact_ids = []
    for index, fact in enumerate(case_facts):
        if not isinstance(fact, dict):
            raise ValueError(f"case_facts[{index}] must be an object")
        fact_id = fact.get("fact_id")
        if not isinstance(fact_id, str) or not fact_id.strip():
            raise ValueError(f"case_facts[{index}].fact_id must be a non-empty string")
        fact_ids.append(fact_id)
    if len(fact_ids) != len(set(fact_ids)):
        raise ValueError("case fact IDs must be unique")
    return case_facts

def _normalise_genes(genes, *, field="genes"):
    if not isinstance(genes, list):
        raise ValueError(f"{field} must be a JSON array")
    normalised = []
    seen = set()
    for index, value in enumerate(genes):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{field}[{index}] must be a non-empty string")
        upper = value.upper()
        if upper in seen:
            raise ValueError(f"{field} contains duplicate gene {upper!r} after normalisation")
        seen.add(upper)
        normalised.append(upper)
    return normalised

def _validate_case_disease(disease, genes, *, field):
    """Validate one case-level disease against the submitted variant genes.
    ``no_haematological_malignancy`` is deliberately case-only and is legal only
    when no variant genes are submitted. Other diseases may also have no reported
    variants; the case-only term must not be inferred solely from an empty gene list.
    """
    if disease not in vocab.CASE_DISEASE_SET:
        raise ValueError(f"{field} {disease!r} is outside the case disease vocabulary")
    if disease == vocab.NO_HAEMATOLOGICAL_MALIGNANCY and genes:
        raise ValueError(
            f"{field} {vocab.NO_HAEMATOLOGICAL_MALIGNANCY!r} requires no reported variants"
        )
    return disease

def _validate_case_major_category(category, genes, *, field="case_major_category"):
    if category not in vocab.CASE_MAJOR_CATEGORY_SET:
        raise ValueError(f"{field} {category!r} is outside the case-major-category vocabulary")
    if category == vocab.NO_HAEMATOLOGICAL_MALIGNANCY and genes:
        raise ValueError(
            f"{field} {vocab.NO_HAEMATOLOGICAL_MALIGNANCY!r} requires no reported variants"
        )
    return category


def validate_case_input(path):
    """Validate Step-1 case input without normalising its provisional diagnosis."""
    if not path.is_file():
        raise ValueError(f"case-input not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"case-input is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("case-input must be a JSON object")
    required = {"case_major_category", "provisional_disease", "genes", "case_facts"}
    if set(document) != required:
        raise ValueError(
            "case-input must contain exactly: " + ", ".join(sorted(required))
        )
    provisional_disease = document["provisional_disease"]
    if not isinstance(provisional_disease, str) or not provisional_disease.strip():
        raise ValueError("case-input provisional_disease must be a non-empty string")
    genes = _normalise_genes(document["genes"], field="case-input genes")
    case_major_category = _validate_case_major_category(
        document["case_major_category"], genes, field="case-input case_major_category"
    )
    case_facts = validate_case_facts(document["case_facts"])
    return {
        "case_major_category": case_major_category,
        "provisional_disease": provisional_disease.strip(),
        "genes": genes,
        "case_facts": case_facts,
    }


def _infer_case_major_category_from_provisional(provisional_disease):
    """Backward-compatible inference for direct callers, never used for case-input."""
    canonical = vocab.canonical_case_disease(provisional_disease)
    if canonical is None:
        return None
    return vocab.preferred_case_major_category(canonical)


def step2(
    cards, genes, provisional_disease, case_facts=None, *, case_major_category=None
):
    case_facts = validate_case_facts(case_facts or [])
    normalised_genes = _normalise_genes(list(genes), field="genes")
    if not isinstance(provisional_disease, str) or not provisional_disease.strip():
        raise ValueError("provisional_disease must be a non-empty string")
    if case_major_category is None:
        case_major_category = _infer_case_major_category_from_provisional(provisional_disease)
        if case_major_category is None:
            raise ValueError(
                "case_major_category is required when provisional_disease is not an exact canonical disease or alias"
            )
    _validate_case_major_category(case_major_category, normalised_genes)
    wanted = set(normalised_genes)
    related_diseases = set(
        vocab.retrieval_related_diseases(case_major_category, "diagnosis")
        if case_major_category in vocab.DISEASE_SET else []
    )
    hits = []
    for card in cards:
        if card["category"] != "diagnosis":
            continue
        matched = match_genes(card, wanted)
        diseases = set(card["diseases"])
        major_category_matched = any(
            vocab.disease_matches_case_major_category(disease, case_major_category)
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
        if disease in vocab.DISEASE_SET
    }
    allowed = [disease for disease in vocab.DISEASES if disease in represented]
    if case_major_category in vocab.CASE_DISEASE_SET and case_major_category not in allowed:
        allowed.insert(0, case_major_category)
    if not allowed:
        # Every normal case-major category is a canonical or case-only routing value;
        # this guard makes malformed future vocabulary fail clearly.
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
        "diagnosis_cards": sorted(hits, key=lambda item: item["card_id"]),
        "allowed_refined_diseases": allowed,
        "genes_with_no_diagnosis_card": sorted(wanted - genes_with_diagnosis_card),
    }


def _validate_user_review(
    adjudication, genes, allowed_refined_diseases, retrieved_card_ids, *,
    require_completed_review
):
    """Validate automatic or manual Step 3 review state."""
    review = adjudication.get("user_review")
    model_refined = adjudication["refined_disease"]
    model_label = adjudication["diagnostic_label"]
    downstream = adjudication["downstream_filter_disease"]

    if review == "automatic":
        if downstream != model_refined:
            raise ValueError(
                "automatic user_review requires downstream_filter_disease to exactly "
                "equal refined_disease"
            )
        return review

    if review is None:
        if require_completed_review:
            raise ValueError("user_review is required before Step 4")
        if downstream != model_refined:
            raise ValueError(
                "without user_review, downstream_filter_disease must exactly equal "
                "refined_disease"
            )
        return None

    review_keys = {"decision", "diagnostic_label", "refined_disease", "reason", "card_ids"}
    if not isinstance(review, dict) or set(review) != review_keys:
        raise ValueError(
            "user_review must be 'automatic' or contain exactly: "
            + ", ".join(sorted(review_keys))
        )
    decision = review["decision"]
    if decision not in {"pending", "agree", "disagree"}:
        raise ValueError(f"invalid user_review decision {decision!r}")
    reviewed_label = review["diagnostic_label"]
    if reviewed_label is not None and (
        not isinstance(reviewed_label, str) or not reviewed_label.strip()
    ):
        raise ValueError(
            "user_review diagnostic_label must be null or a non-empty string"
        )
    reviewed_refined = review["refined_disease"]
    if reviewed_refined is not None:
        _validate_case_disease(
            reviewed_refined,
            genes,
            field="user_review refined_disease",
        )
        if reviewed_refined not in allowed_refined_diseases:
            raise ValueError(
                f"user_review refined_disease {reviewed_refined!r} is not allowed by Step 2"
            )
    reviewed_reason = review["reason"]
    reviewed_cards = review["card_ids"]
    if reviewed_reason is not None and (
        not isinstance(reviewed_reason, str) or not reviewed_reason.strip()
    ):
        raise ValueError("user_review reason must be null or a non-empty string")
    if not isinstance(reviewed_cards, list) or any(
        not isinstance(card_id, str) or not card_id for card_id in reviewed_cards
    ):
        raise ValueError("user_review card_ids must be an array of non-empty strings")
    if len(reviewed_cards) != len(set(reviewed_cards)):
        raise ValueError("user_review card_ids must be unique")
    if any(card_id not in retrieved_card_ids for card_id in reviewed_cards):
        raise ValueError("every user_review card_id must name a retrieved diagnosis card")

    if decision == "pending":
        if (
            reviewed_label is not None
            or reviewed_refined is not None
            or reviewed_reason is not None
            or reviewed_cards
        ):
            raise ValueError(
                "pending user_review must have null diagnostic_label, refined_disease, "
                "and reason, with empty card_ids"
            )
        if downstream != model_refined:
            raise ValueError(
                "pending user_review must preserve the model refined_disease as the "
                "downstream_filter_disease"
            )
        if require_completed_review:
            raise ValueError("user review is pending; Step 4 is blocked")
        return review
    if reviewed_refined is None:
        raise ValueError("completed user_review requires refined_disease")
    if downstream != reviewed_refined:
        raise ValueError(
            "downstream_filter_disease must exactly equal user_review.refined_disease"
        )
    if decision == "agree":
        if (
            reviewed_refined != model_refined
            or reviewed_label != model_label
            or reviewed_reason != adjudication["reason"]
            or reviewed_cards != adjudication["driven_by"]
        ):
            raise ValueError(
                "an agreeing user_review must copy the model diagnostic_label, "
                "refined_disease, reason, and driven_by cards exactly"
            )
    else:
        if reviewed_label is None:
            raise ValueError(
                "a disagreeing user_review requires the user's integrated diagnostic_label"
            )
        if reviewed_reason is None or not reviewed_cards:
            raise ValueError(
                "a disagreeing user_review requires an evidence-grounded reason and card_ids"
            )
    return review

def validate_adjudication(step2_result, adjudication, *, require_completed_review=False):
    base_keys = {
        "status", "provisional_disease", "refined_disease",
        "downstream_filter_disease", "diagnostic_label", "driven_by",
        "criterion_assessment", "reason",
    }
    allowed_key_sets = {frozenset(base_keys), frozenset(base_keys | {"user_review"})}
    if not isinstance(adjudication, dict) or frozenset(adjudication) not in allowed_key_sets:
        raise ValueError(
            "adjudication must contain exactly the model fields and optional user_review: "
            + ", ".join(sorted(base_keys | {"user_review"}))
        )
    status = adjudication["status"]
    if status not in {"criteria_met", "criteria_not_met", "indeterminate"}:
        raise ValueError(f"invalid adjudication status {status!r}")
    provisional = step2_result["provisional_disease"]
    if not isinstance(provisional, str) or not provisional.strip():
        raise ValueError("step2 provisional_disease must be a non-empty string")
    genes = _normalise_genes(step2_result["genes"], field="step2 genes")
    case_major_category = step2_result.get("case_major_category")
    _validate_case_major_category(case_major_category, genes, field="step2 case_major_category")
    allowed_refined_diseases = step2_result.get("allowed_refined_diseases", [])
    if not isinstance(allowed_refined_diseases, list) or any(
        disease not in vocab.CASE_DISEASE_SET for disease in allowed_refined_diseases
    ):
        raise ValueError("step2 allowed_refined_diseases is invalid")
    if adjudication["provisional_disease"] != provisional:
        raise ValueError("adjudication provisional_disease does not match diagnosis result")
    refined = adjudication["refined_disease"]
    _validate_case_disease(refined, genes, field="adjudication refined_disease")
    if refined not in allowed_refined_diseases:
        raise ValueError(
            f"adjudication refined_disease {refined!r} is not allowed by Step 2"
        )
    downstream = adjudication["downstream_filter_disease"]
    _validate_case_disease(
        downstream,
        genes,
        field="adjudication downstream_filter_disease",
    )
    if downstream not in allowed_refined_diseases:
        raise ValueError(
            f"adjudication downstream_filter_disease {downstream!r} is not allowed by Step 2"
        )
    label = adjudication["diagnostic_label"]
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError("diagnostic_label must be null or a non-empty string")
    if not isinstance(adjudication["reason"], str) or not adjudication["reason"].strip():
        raise ValueError("adjudication reason must be a non-empty string")
    retrieved_card_ids = {card["card_id"] for card in step2_result["diagnosis_cards"]}
    driven_by = adjudication["driven_by"]
    if not isinstance(driven_by, list) or any(card_id not in retrieved_card_ids for card_id in driven_by):
        raise ValueError("every driven_by ID must name a retrieved diagnosis card")
    if len(driven_by) != len(set(driven_by)):
        raise ValueError("driven_by card IDs must be unique")
    supplied_fact_ids = {fact["fact_id"] for fact in validate_case_facts(step2_result["case_facts"])}
    assessments = adjudication["criterion_assessment"]
    if not isinstance(assessments, list):
        raise ValueError("criterion_assessment must be an array")
    required_assessments = []
    for index, item in enumerate(assessments):
        item_keys = {"criterion", "required", "status", "card_ids", "case_fact_ids"}
        if not isinstance(item, dict) or set(item) != item_keys:
            raise ValueError(f"criterion_assessment[{index}] has the wrong fields")
        if not isinstance(item["criterion"], str) or not item["criterion"].strip():
            raise ValueError(f"criterion_assessment[{index}].criterion must be non-empty")
        if not isinstance(item["required"], bool):
            raise ValueError(f"criterion_assessment[{index}].required must be boolean")
        if item["status"] not in {"met", "not_met", "unknown"}:
            raise ValueError(f"criterion_assessment[{index}] has invalid status")
        if not isinstance(item["card_ids"], list) or not item["card_ids"]:
            raise ValueError(f"criterion_assessment[{index}] must cite a diagnosis card")
        if any(card_id not in retrieved_card_ids for card_id in item["card_ids"]):
            raise ValueError(f"criterion_assessment[{index}] cites an unretrieved card")
        if not isinstance(item["case_fact_ids"], list):
            raise ValueError(f"criterion_assessment[{index}].case_fact_ids must be an array")
        if any(fact_id not in supplied_fact_ids for fact_id in item["case_fact_ids"]):
            raise ValueError(f"criterion_assessment[{index}] cites an unsupplied case fact")
        if item["status"] != "unknown" and not item["case_fact_ids"]:
            raise ValueError(f"criterion_assessment[{index}] must cite a case fact")
        if item["required"]:
            required_assessments.append(item)
    if status == "criteria_met" and any(
        item["status"] != "met" for item in required_assessments
    ):
        raise ValueError("criteria_met requires every required criterion to be met")
    changed_major_category = not vocab.disease_matches_case_major_category(
        refined, case_major_category
    )
    if status != "criteria_met" and changed_major_category:
        raise ValueError(
            "non-met or indeterminate adjudication must remain within the original case_major_category"
        )
    if changed_major_category:
        if not driven_by:
            raise ValueError("a changed major category requires at least one driving card")
        if not required_assessments:
            raise ValueError("a changed major category requires at least one required criterion")
        if any(item["status"] != "met" for item in required_assessments):
            raise ValueError("a changed major category requires every required criterion to be met")
    _validate_user_review(
        adjudication,
        genes,
        allowed_refined_diseases,
        retrieved_card_ids,
        require_completed_review=require_completed_review,
    )
    return adjudication

def _adjudication_diagnosis_card_ids(adjudication):
    """Return diagnosis cards actually cited/used by Step 3, preserving no extras."""
    selected = set(adjudication.get("driven_by") or [])
    for assessment in adjudication.get("criterion_assessment") or []:
        selected.update(assessment.get("card_ids") or [])
    review = adjudication.get("user_review")
    if isinstance(review, dict) and review.get("decision") in {"agree", "disagree"}:
        selected.update(review.get("card_ids") or [])
    return selected


def step4(
    cards, genes, refined_disease, diagnosis_cards, *, adjudication=None,
    case_major_category=None
):
    normalised_genes = _normalise_genes(list(genes), field="genes")
    _validate_case_disease(refined_disease, normalised_genes, field="refined_disease")
    if case_major_category is None:
        case_major_category = vocab.preferred_case_major_category(refined_disease)
    if case_major_category is not None:
        _validate_case_major_category(case_major_category, normalised_genes)
    wanted = set(normalised_genes)
    retrieved = []
    suppressed = []
    retrieval_scope = {
        category: vocab.retrieval_related_diseases(refined_disease, category)
        for category in DISEASE_FILTERED
    }
    diagnosis_by_id = {card["card_id"]: card for card in diagnosis_cards}
    if adjudication is None:
        # Backward-compatible direct-call behaviour: Step-2 diagnosis cards remain
        # eligible under the old stricter filter.
        selected_diagnosis_ids = set(diagnosis_by_id)
        carry_used_only = False
        broad_major_fallback = False
    else:
        selected_diagnosis_ids = _adjudication_diagnosis_card_ids(adjudication)
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
        matched = match_genes(card, wanted)
        hit = dict(card)
        hit["matched_genes"] = matched

        if category == "diagnosis":
            if card["card_id"] not in selected_diagnosis_ids:
                continue
            if carry_used_only:
                hit["retrieval_match"] = "adjudication_used"
                retrieved.append(hit)
                continue
            # Legacy direct-call path below keeps the historical Step-4 filtering.

        if category == "germline":
            if matched:
                hit["retrieval_match"] = "gene_only"
                retrieved.append(hit)
            continue
        if category not in DISEASE_FILTERED:
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
                if vocab.disease_matches_case_major_category(disease, case_major_category)
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


def run_diagnosis(args):
    corpus, _index, digest = load_corpus(args.corpus, args.index)
    cards = flatten(corpus)
    case_input = None
    overrides = []
    if args.case_input:
        case_input = validate_case_input(args.case_input)
    if args.genes:
        genes = [gene.upper() for gene in args.genes]
        if case_input:
            overrides.append("genes")
    elif case_input:
        genes = case_input["genes"]
    else:
        raise ValueError("--genes is required unless --case-input is provided")
    if args.provisional_disease is not None:
        provisional = args.provisional_disease
        if case_input:
            overrides.append("provisional-disease")
    elif case_input:
        provisional = case_input["provisional_disease"]
    else:
        provisional = vocab.UNSPECIFIED_DISEASE
    if args.case_major_category is not None:
        case_major_category = args.case_major_category
        if case_input:
            overrides.append("case-major-category")
    elif case_input:
        case_major_category = case_input["case_major_category"]
    else:
        case_major_category = None
    if args.case_facts:
        facts_document = json.loads(args.case_facts.read_text(encoding="utf-8"))
        case_facts = facts_document.get("case_facts") if isinstance(facts_document, dict) else facts_document
        if case_input:
            overrides.append("case-facts")
    elif case_input:
        case_facts = case_input["case_facts"]
    else:
        raise ValueError("--case-facts is required unless --case-input is provided")
    for field in overrides:
        flag = field if field != "provisional-disease" else "provisional-disease"
        print(f"[retrieve] overriding case-input {field} from --{flag}", file=sys.stderr)
    result = step2(
        cards, genes, provisional, case_facts, case_major_category=case_major_category
    )
    result["corpus"] = {"path": str(args.corpus), "index": str(args.index)}
    result["provenance"] = provenance(
        corpus, args.corpus, args.index, digest,
        [card["card_id"] for card in result["diagnosis_cards"]],
    )
    result["step3_instruction"] = (
        "Use prompts/diagnostic_adjudication_prompt.md to compare only case_facts with "
        "the retrieved diagnosis_cards. provisional_disease is the supplied free-text "
        "starting diagnosis; refined_disease must be one allowed canonical value. A "
        "change outside case_major_category requires fully met diagnostic criteria."
    )
    return result

def run_full(args):
    step2_result = json.loads(Path(args.diagnosis_result).read_text(encoding="utf-8"))
    adjudication = json.loads(Path(args.adjudication_result).read_text(encoding="utf-8"))
    validate_adjudication(
        step2_result,
        adjudication,
        require_completed_review=True,
    )
    corpus_path = Path(args.corpus or step2_result["corpus"]["path"])
    index_path = Path(args.index or step2_result["corpus"]["index"])
    corpus, _index, digest = load_corpus(corpus_path, index_path)
    provisional = step2_result["provisional_disease"]
    refined = adjudication["downstream_filter_disease"]
    genes = args.genes if args.genes is not None else step2_result["genes"]
    cards = flatten(corpus)
    result = step4(
        cards, genes, refined, step2_result["diagnosis_cards"],
        adjudication=adjudication,
        case_major_category=step2_result["case_major_category"],
    )
    result = {
        "step": 4,
        "genes": sorted({gene.upper() for gene in genes}),
        "case_major_category": step2_result["case_major_category"],
        "provisional_disease": provisional,
        "refined_disease": refined,
        "diagnostic_adjudication": adjudication,
        **result,
    }
    result["provenance"] = provenance(
        corpus, corpus_path, index_path, digest,
        [card["card_id"] for card in result["retrieved"]],
    )
    return result

def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    diagnosis = sub.add_parser("diagnosis", help="step 2")
    diagnosis.add_argument("--case-input", type=Path,
                           help="JSON object with case_major_category, provisional_disease, genes, and case_facts")
    diagnosis.add_argument("--genes", nargs="+")
    diagnosis.add_argument("--case-facts", type=Path,
                           help="JSON array, or object with case_facts array")
    diagnosis.add_argument("--provisional-disease", default=None)
    diagnosis.add_argument(
        "--case-major-category", default=None, choices=vocab.CASE_MAJOR_CATEGORIES
    )
    diagnosis.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    diagnosis.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    full = sub.add_parser("full", help="step 4")
    full.add_argument("--diagnosis-result", type=Path, required=True)
    full.add_argument("--adjudication-result", type=Path, required=True,
                      help="JSON emitted under diagnostic_adjudication_prompt.md")
    full.add_argument("--genes", nargs="+")
    full.add_argument("--corpus", type=Path)
    full.add_argument("--index", type=Path)
    for sub_parser in (diagnosis, full):
        sub_parser.add_argument("--output", type=Path, help="write JSON here instead of stdout")
    args = parser.parse_args()
    try:
        result = run_diagnosis(args) if args.command == "diagnosis" else run_full(args)
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"retrieval failed: {exc}")
    payload = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
        print(f"wrote {args.output}", file=sys.stderr)
    else:
        print(payload)


if __name__ == "__main__":
    main()
