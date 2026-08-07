#!/usr/bin/env python3
"""Retrieval steps 2 and 4. Everything here is a script for a reason.

The two model decisions in the procedure are bounded elsewhere: step 1 extracts
structured case facts, genes, and a provisional disease from free text; step 3
adjudicates those facts against retrieved diagnosis cards. Between and after them,
what a gene is allowed to retrieve is decided by code, because a prompt is a
request and code is a guarantee.

Two subcommands:
  diagnosis   step 2. Every diagnosis card for the submitted genes, with no
              disease filter at all, because a gene may point toward a diagnosis
              other than the one the marrow report proposed. Carries structured
              case facts into the evidence-bounded adjudication input.
  full        step 4. prognosis, treatment and biomarker cards on gene match AND
              (disease match OR empty disease array); germline cards on gene match
              alone. Diagnosis cards from the step 2 bundle are carried through so
              the rendered block is complete.
Nothing is silently dropped. Cards excluded by the disease filter appear in
`suppressed`, counted by disease. Submitted genes with no card anywhere appear in
`not_assessed`, named individually. A gene that was considered and cleared and a
gene that was never looked at are very different things, and a clinician reading
the output cannot tell them apart unless the tool says so.

Usage:
  retrieve.py diagnosis --case-input case-input.json --output step2.json
  retrieve.py diagnosis --genes NPM1 DNMT3A FLT3 --case-facts case-facts.json \
      --corpus output/corpus/nel.corpus.json --index output/corpus/nel.index.json \
      --provisional-disease MDS --output step2.json

  retrieve.py full --diagnosis-result step2.json \
      --adjudication-result adjudication.json --output bundle.json
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

DISEASE_FILTERED = ("prognosis", "treatment", "biomarker")


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


def validate_case_input(path):
    """Validate and return the structured case input produced by Step 1."""
    if not path.is_file():
        raise ValueError(f"case-input not found: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"case-input is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("case-input must be a JSON object")
    required = {"provisional_disease", "genes", "case_facts"}
    if set(document) != required:
        raise ValueError(
            "case-input must contain exactly: " + ", ".join(sorted(required))
        )
    provisional_disease = document["provisional_disease"]
    if provisional_disease not in vocab.DISEASE_SET:
        raise ValueError(
            f"case-input provisional_disease {provisional_disease!r} is not in the disease vocabulary"
        )
    genes = document["genes"]
    if not isinstance(genes, list) or not genes:
        raise ValueError("case-input genes must be a non-empty JSON array")
    normalised = []
    seen = set()
    for index, value in enumerate(genes):
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"case-input genes[{index}] must be a non-empty string")
        upper = value.upper()
        if upper in seen:
            raise ValueError(f"case-input contains duplicate gene {upper!r} after normalisation")
        seen.add(upper)
        normalised.append(upper)
    case_facts = validate_case_facts(document["case_facts"])

    return {
        "provisional_disease": provisional_disease,
        "genes": normalised,
        "case_facts": case_facts,
    }


def step2(cards, genes, provisional_disease, case_facts=None):
    case_facts = validate_case_facts(case_facts or [])
    wanted = {gene.upper() for gene in genes}
    hits = []
    for card in cards:
        if card["category"] != "diagnosis":
            continue
        matched = match_genes(card, wanted)
        if matched:
            hit = dict(card)
            hit["matched_genes"] = matched
            hits.append(hit)
    genes_with_diagnosis_card = {gene for hit in hits for gene in hit["matched_genes"]}
    return {
        "step": 2,
        "provisional_disease": provisional_disease,
        "genes": sorted(wanted),
        "case_facts": case_facts,
        "diagnosis_cards": sorted(hits, key=lambda item: item["card_id"]),
        "allowed_refined_diseases": list(vocab.DISEASES),
        "genes_with_no_diagnosis_card": sorted(wanted - genes_with_diagnosis_card),
    }


def _validate_user_review(adjudication, *, require_completed_review):
    """Validate the human review state and return the completed review or ``None``.

    Legacy model-only adjudications remain valid for direct internal validation so
    existing callers can inspect the model decision. ``run_full`` always requests a
    completed review and therefore cannot enter Step 4 through that compatibility
    path.
    """
    review = adjudication.get("user_review")
    model_refined = adjudication["refined_disease"]
    model_label = adjudication["diagnostic_label"]
    downstream = adjudication["downstream_filter_disease"]

    if review is None:
        if require_completed_review:
            raise ValueError(
                "user_review is required before Step 4; present the adjudication JSON "
                "to the user and obtain PROCEED_TO_STEP_4"
            )
        if downstream != model_refined:
            raise ValueError(
                "without user_review, downstream_filter_disease must exactly equal "
                "refined_disease"
            )
        return None

    review_keys = {"decision", "diagnostic_label", "refined_disease"}
    if not isinstance(review, dict) or set(review) != review_keys:
        raise ValueError(
            "user_review must contain exactly: " + ", ".join(sorted(review_keys))
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
    if reviewed_refined is not None and reviewed_refined not in vocab.DISEASE_SET:
        raise ValueError(
            f"user_review refined_disease {reviewed_refined!r} is outside the vocabulary"
        )

    if decision == "pending":
        if reviewed_label is not None or reviewed_refined is not None:
            raise ValueError(
                "pending user_review must have null diagnostic_label and refined_disease"
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
        if reviewed_refined != model_refined or reviewed_label != model_label:
            raise ValueError(
                "an agreeing user_review must copy the model diagnostic_label and "
                "refined_disease exactly"
            )
    elif reviewed_label is None:
        raise ValueError(
            "a disagreeing user_review requires the user's integrated diagnostic_label"
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
    if adjudication["provisional_disease"] != provisional:
        raise ValueError("adjudication provisional_disease does not match diagnosis result")
    refined = adjudication["refined_disease"]
    if refined not in vocab.DISEASE_SET:
        raise ValueError(f"adjudication refined_disease {refined!r} is outside the vocabulary")
    downstream = adjudication["downstream_filter_disease"]
    if downstream not in vocab.DISEASE_SET:
        raise ValueError(
            f"adjudication downstream_filter_disease {downstream!r} is outside the vocabulary"
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
    changed = refined != provisional
    if status != "criteria_met" and changed:
        raise ValueError("non-met or indeterminate adjudication must preserve provisional_disease")
    if changed:
        if not driven_by:
            raise ValueError("a changed major category requires at least one driving card")
        if not required_assessments:
            raise ValueError("a changed major category requires at least one required criterion")
        if any(item["status"] != "met" for item in required_assessments):
            raise ValueError("a changed major category requires every required criterion to be met")

    _validate_user_review(
        adjudication,
        require_completed_review=require_completed_review,
    )
    return adjudication


def step4(cards, genes, refined_disease, diagnosis_cards):
    wanted = {gene.upper() for gene in genes}
    retrieved = list(diagnosis_cards)
    suppressed = []

    for card in cards:
        category = card["category"]
        if category == "diagnosis":
            continue
        matched = match_genes(card, wanted)
        if not matched:
            continue
        hit = dict(card)
        hit["matched_genes"] = matched
        if category == "germline":
            # Germline retrieves on gene alone. A predisposition gene does not stop
            # predisposing because the marrow was called something else.
            retrieved.append(hit)
            continue

        diseases = card["diseases"]
        if not diseases or refined_disease in diseases:
            retrieved.append(hit)
        else:
            suppressed.append(hit)
    assessed = {gene for hit in retrieved for gene in hit["matched_genes"]}
    assessed |= {gene for hit in suppressed for gene in hit["matched_genes"]}
    not_assessed = sorted(wanted - assessed)

    by_disease = {}
    for hit in suppressed:
        for disease in hit["diseases"]:
            by_disease[disease] = by_disease.get(disease, 0) + 1
    return {
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
                "reason": "no card in any category in this corpus version",
            }
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
    result = step2(cards, genes, provisional, case_facts)
    result["corpus"] = {"path": str(args.corpus), "index": str(args.index)}
    result["provenance"] = provenance(
        corpus, args.corpus, args.index, digest,
        [card["card_id"] for card in result["diagnosis_cards"]],
    )
    result["step3_instruction"] = (
        "Use prompts/diagnostic_adjudication_prompt.md to compare only case_facts with "
        "the retrieved diagnosis_cards. refined_disease is the model-proposed major "
        "category; downstream_filter_disease becomes the completed user-reviewed major "
        "category before Step 4."
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

    genes = args.genes or step2_result["genes"]
    cards = flatten(corpus)
    result = step4(cards, genes, refined, step2_result["diagnosis_cards"])
    result = {
        "step": 4,
        "genes": sorted({gene.upper() for gene in genes}),
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
                           help="JSON object with genes, provisional_disease, and case_facts")
    diagnosis.add_argument("--genes", nargs="+")
    diagnosis.add_argument("--case-facts", type=Path,
                           help="JSON array, or object with case_facts array")
    diagnosis.add_argument("--provisional-disease", default=None, choices=vocab.DISEASES)
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
