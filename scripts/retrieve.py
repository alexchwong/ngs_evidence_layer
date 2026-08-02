#!/usr/bin/env python3
"""Retrieval steps 2 and 4. Everything here is a script for a reason.

The two model decisions in the procedure are bounded elsewhere: step 1 extracts
genes and a provisional disease from free text, step 3 picks a refined disease
from a closed set this script produced. Between and after them, what a gene is
allowed to retrieve is decided by code, because a prompt is a request and code is
a guarantee.

Two subcommands:

  diagnosis   step 2. Every diagnosis card for the submitted genes, with no
              disease filter at all, because a gene may point toward a diagnosis
              other than the one the marrow report proposed. Also emits
              escalation_candidates: the closed set from which step 3 may choose.

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
  retrieve.py diagnosis --genes NPM1 DNMT3A FLT3 \\
      --corpus output/corpus/nel.corpus.json --index output/corpus/nel.index.json \\
      --provisional-disease MDS > step2.json

  retrieve.py full --diagnosis-result step2.json --refined-disease AML \\
      --driven-by who5-2022-npm1-dx-001 > bundle.json
"""
import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import vocab  # noqa: E402

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
                "escalates_to": card.get("escalates_to"),
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


def step2(cards, genes, provisional_disease):
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

    escalation = {}
    for hit in hits:
        target = hit.get("escalates_to")
        if target and target != provisional_disease:
            escalation.setdefault(target, []).append(hit["card_id"])

    genes_with_diagnosis_card = {gene for hit in hits for gene in hit["matched_genes"]}
    return {
        "step": 2,
        "provisional_disease": provisional_disease,
        "genes": sorted(wanted),
        "diagnosis_cards": sorted(hits, key=lambda item: item["card_id"]),
        "escalation_candidates": [
            {"disease": disease, "card_ids": sorted(card_ids)}
            for disease, card_ids in sorted(escalation.items())
        ],
        "genes_with_no_diagnosis_card": sorted(wanted - genes_with_diagnosis_card),
    }


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
    result = step2(cards, args.genes, args.provisional_disease)
    result["corpus"] = {"path": str(args.corpus), "index": str(args.index)}
    result["provenance"] = provenance(
        corpus, args.corpus, args.index, digest,
        [card["card_id"] for card in result["diagnosis_cards"]],
    )
    result["step3_instruction"] = (
        "Choose refined_disease from {provisional_disease} union escalation_candidates "
        "only. Any other value is rejected. In most cases there are no candidates and "
        "the provisional disease stands unchanged."
    )
    return result


def run_full(args):
    step2_result = json.loads(Path(args.diagnosis_result).read_text(encoding="utf-8"))
    corpus_path = Path(args.corpus or step2_result["corpus"]["path"])
    index_path = Path(args.index or step2_result["corpus"]["index"])
    corpus, _index, digest = load_corpus(corpus_path, index_path)

    provisional = step2_result["provisional_disease"]
    candidates = [item["disease"] for item in step2_result["escalation_candidates"]]
    allowed = {provisional} | set(candidates)
    refined = args.refined_disease or provisional
    if refined not in allowed:
        raise ValueError(
            f"refined_disease {refined!r} is outside the permitted set "
            f"{sorted(allowed)}. Step 3 may only choose from the provisional disease "
            "and the escalation candidates the corpus actually asserted."
        )
    if refined != provisional and not args.driven_by:
        raise ValueError(
            "--driven-by is required when the refined disease differs from the "
            "provisional one: the cards that moved the diagnosis must be named"
        )

    genes = args.genes or step2_result["genes"]
    cards = flatten(corpus)
    result = step4(cards, genes, refined, step2_result["diagnosis_cards"])

    result = {
        "step": 4,
        "genes": sorted({gene.upper() for gene in genes}),
        "provisional_disease": provisional,
        "refined_disease": refined,
        "escalation": {
            "candidates": step2_result["escalation_candidates"],
            "applied": refined != provisional,
            "driven_by": sorted(args.driven_by or []),
        },
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
    diagnosis.add_argument("--genes", nargs="+", required=True)
    diagnosis.add_argument("--provisional-disease", default=vocab.UNSPECIFIED_DISEASE,
                           choices=vocab.DISEASES)
    diagnosis.add_argument("--corpus", type=Path, default=Path("output/corpus/nel.corpus.json"))
    diagnosis.add_argument("--index", type=Path, default=Path("output/corpus/nel.index.json"))

    full = sub.add_parser("full", help="step 4")
    full.add_argument("--diagnosis-result", type=Path, required=True)
    full.add_argument("--refined-disease", choices=vocab.DISEASES)
    full.add_argument("--driven-by", nargs="+", help="card IDs that moved the diagnosis")
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
