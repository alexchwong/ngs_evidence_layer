#!/usr/bin/env python3
"""Build a single self-contained HTML browser for the accepted card corpus.

The default browser keeps the compact corpus-only view. ``--full`` enriches
cards with their accepted evidence package and enables a click-through detail
pane containing the complete card, evidence, publication and provenance data.
Because accepted evidence is private/gitignored, full mode writes into the
private ``evidence/`` directory by default.

Usage:
  build_card_browser.py [--corpus output/corpus/nel.corpus.json]
                        [--output output/reports/card-browser.html]
  build_card_browser.py --full [--accept-dir accept]
                        [--output evidence/card-browser-full.html]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core import corpus as corpus_core  # noqa: E402
from scripts.core import cul as cul_core  # noqa: E402


def _short_card_id(card_id: str) -> str:
    return cul_core.short_card_id(card_id)


def _profile_payload(name: str, document, cards) -> dict:
    path = cul_core.profile_path(name)
    raw = json.loads(path.read_text(encoding="utf-8"))
    layer = cul_core.load_profile(path, corpus_document=document, cards=cards, strict=False)
    return {
        "profile": layer["profile"],
        "description": layer.get("description") or "",
        "scope": raw.get("scope") or {"enabled": True, "global": {}, "papers": {}},
        "amendments": {
            card_id: {
                **{f: entry[f] for f in cul_core.AMENDABLE_FIELDS if f in entry},
                "base_sha256": entry.get("base_sha256"),
                "stale": entry.get("stale", False),
            }
            for card_id, entry in layer["amendments"].items()
        },
        "stale": layer.get("stale") or [],
    }


def _all_profiles(document, cards) -> dict:
    """Every profile in config/cul/, so the browser can switch without rebuilding.

    Profiles are a few kilobytes each; embedding them avoids a rebuild or a file
    dialog just to compare two profiles against the same corpus.
    """
    out = {}
    for name in cul_core.available_profiles():
        try:
            out[name] = _profile_payload(name, document, cards)
        except (ValueError, cul_core.CULError):
            continue
    return out


def _vocabulary() -> dict:
    """Closed value sets the browser's edit controls must honour.

    Shipping these with the payload keeps the browser's dropdowns and the
    ``cul.py`` validator reading from the same source, so an edit cannot be
    composed in the browser that the CLI will later reject.
    """
    from scripts import vocab as vocab_module

    return {
        "categories": sorted(corpus_core.CARD_CATEGORIES),
        "evidenceTiers": list(cul_core.EVIDENCE_TIERS),
        # The full schema vocabulary, not merely the terms the corpus happens to
        # use, and sorted for a searchable picker rather than kept in the
        # schema's taxonomic order.
        "diseases": sorted(vocab_module.DISEASES, key=str.casefold),
    }
DEFAULT_CORPUS = REPO_ROOT / "output" / "corpus" / "nel.corpus.json"
DEFAULT_OUTPUT = REPO_ROOT / "output" / "reports" / "card-browser.html"
DEFAULT_FULL_OUTPUT = REPO_ROOT / "evidence" / "card-browser-full.html"
#: The editor is owned by cul.py and lives beside the profiles it edits, never
#: under output/, which incorporation regenerates.
DEFAULT_EDIT_OUTPUT = REPO_ROOT / "config" / "cul" / "corpus-user-layer.html"
DEFAULT_ACCEPT_DIR = REPO_ROOT / "accept"
TEMPLATE = Path(__file__).resolve().parent / "assets" / "card_browser_template.html"
CUL_SCRIPT = Path(__file__).resolve().parent / "assets" / "card_browser_cul.js"


def _load_json(path: Path, label: str) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError(f"{label} not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"{label} is not valid JSON: {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must contain a JSON object: {path}")
    return value


def _accepted_package(publication_key: str, accept_dir: Path) -> dict:
    path = accept_dir / f"{publication_key}.final.json"
    return _load_json(path, "accepted package")


def _full_details(entry: dict, accept_dir: Path) -> tuple[dict, dict[str, dict]]:
    """Return paper-level detail and evidence indexed by card ID.

    Full mode deliberately verifies that the accepted package still matches the
    incorporated corpus. Mixing a newer accepted package with an older corpus
    would otherwise produce a plausible-looking but internally inconsistent
    browser.
    """
    document = entry["document"]
    source = entry.get("source", {})
    publication_key = document["publication_key"]
    envelope = _accepted_package(publication_key, accept_dir)
    package = envelope.get("final")
    if not isinstance(package, dict):
        raise ValueError(
            f"accepted package has no object-valued final package: "
            f"{accept_dir / (publication_key + '.final.json')}"
        )

    package_cards = package.get("cards")
    evidence_items = package.get("evidence")
    if not isinstance(package_cards, list) or not isinstance(evidence_items, list):
        raise ValueError(
            f"accepted package final.cards/final.evidence must be arrays: {publication_key}"
        )

    accepted_cards: dict[str, dict] = {}
    for card in package_cards:
        if not isinstance(card, dict) or not card.get("card_id"):
            raise ValueError(f"accepted package contains an invalid card: {publication_key}")
        card_id = card["card_id"]
        if card_id in accepted_cards:
            raise ValueError(f"accepted package contains duplicate card_id {card_id}")
        accepted_cards[card_id] = card

    evidence_by_card: dict[str, dict] = {}
    for evidence in evidence_items:
        if not isinstance(evidence, dict) or not evidence.get("card_id"):
            raise ValueError(f"accepted package contains invalid evidence: {publication_key}")
        card_id = evidence["card_id"]
        if card_id in evidence_by_card:
            raise ValueError(f"accepted package contains duplicate evidence for {card_id}")
        evidence_by_card[card_id] = evidence

    corpus_cards = {card["card_id"]: card for card in document.get("cards", [])}
    corpus_ids = set(corpus_cards)
    accepted_ids = set(accepted_cards)
    evidence_ids = set(evidence_by_card)
    if accepted_ids != corpus_ids or evidence_ids != corpus_ids:
        missing_cards = sorted(corpus_ids - accepted_ids)
        extra_cards = sorted(accepted_ids - corpus_ids)
        missing_evidence = sorted(corpus_ids - evidence_ids)
        extra_evidence = sorted(evidence_ids - corpus_ids)
        parts = []
        if missing_cards:
            parts.append("missing accepted cards: " + ", ".join(missing_cards))
        if extra_cards:
            parts.append("extra accepted cards: " + ", ".join(extra_cards))
        if missing_evidence:
            parts.append("missing evidence: " + ", ".join(missing_evidence))
        if extra_evidence:
            parts.append("extra evidence: " + ", ".join(extra_evidence))
        raise ValueError(
            f"accepted package does not match incorporated corpus for {publication_key}; "
            + "; ".join(parts)
            + ". Re-run incorporation before building --full."
        )

    for card_id, corpus_card in corpus_cards.items():
        comparable_corpus = {k: v for k, v in corpus_card.items() if k != "disease_ancestors"}
        comparable_accepted = {k: v for k, v in accepted_cards[card_id].items() if k != "disease_ancestors"}
        if comparable_accepted != comparable_corpus:
            raise ValueError(
                f"accepted card {card_id} differs from the incorporated corpus. "
                "Re-run incorporation before building --full."
            )

    # Retain every paper/provenance field without duplicating every card and
    # evidence item in every card payload. The selected card carries its exact
    # card/evidence objects; these paper details carry the remaining fields.
    acceptance = {key: value for key, value in envelope.items() if key != "final"}

    # Compute the latest acceptance version from redos/supplements/revisions
    # if not already set in the envelope.
    if not acceptance.get("latest_version"):
        modifications = []
        for field in ("supplements", "revisions", "redos"):
            entries = envelope.get(field) or []
            for entry in entries:
                accepted_time = entry.get("accepted_at")
                version = entry.get("accepted_in_version")
                if accepted_time and version:
                    modifications.append((accepted_time, version))
        if modifications:
            modifications.sort()
            acceptance["latest_version"] = modifications[-1][1]
    package_fields = {
        key: value for key, value in package.items() if key not in {"cards", "evidence"}
    }
    paper_details = {
        "document": {key: value for key, value in document.items() if key != "cards"},
        "source": source,
        "accepted_package": acceptance,
        "final_package": package_fields,
    }
    return paper_details, evidence_by_card


def collect(corpus_path: Path, *, full: bool = False, accept_dir: Path = DEFAULT_ACCEPT_DIR,
            cul_profile: dict | None = None, corpus_sha256: str | None = None,
            profiles: dict | None = None, editor: bool = False) -> dict:
    corpus = _load_json(corpus_path, "corpus")
    papers = []
    cards = []
    missing_packages = []
    mismatched_packages = []

    for entry in corpus.get("publications", []):
        document = entry["document"]
        key = document["publication_key"]
        citation = document.get("citation", {})
        source = entry.get("source") or {}
        audit = source.get("audit") or {}
        audit_by_card = {
            item.get("card_id"): {
                "verdict": item.get("verdict"),
                "basis": item.get("review_basis"),
            }
            for item in (audit.get("results") or [])
            if item.get("card_id")
        }
        paper = {
            "key": key,
            "nickname": document.get("paper_nickname") or key,
            "display": citation.get("display", ""),
            "journal": citation.get("journal", ""),
            "year": citation.get("year"),
            "type": document.get("publication_type", ""),
            "doi": citation.get("doi", ""),
            "citation": citation,
            "auditModel": audit.get("audit_model"),
            "extractionModel": document.get("extraction_model"),
            "auditDate": audit.get("audit_date"),
        }

        paper_details = None
        evidence_by_card = {}
        if full:
            package_path = accept_dir / f"{key}.final.json"
            if not package_path.exists():
                # A release payload ships no accepted packages. Corpus-only is the
                # normal state there, not a defect, so degrade quietly per paper.
                missing_packages.append(key)
                paper["evidence"] = "absent"
            else:
                try:
                    paper_details, evidence_by_card = _full_details(entry, accept_dir)
                except ValueError as exc:
                    # A package that exists but disagrees with the corpus is a real
                    # sync defect and must not look like a clean release checkout.
                    mismatched_packages.append(key)
                    paper["evidence"] = "mismatched"
                    paper["evidenceWarning"] = str(exc)
                    paper_details = None
                    evidence_by_card = {}
                else:
                    paper["evidence"] = "present"
                    paper["details"] = paper_details
        else:
            paper["evidence"] = "absent"
        papers.append(paper)

        for card in document.get("cards", []):
            row = {
                "id": card["card_id"],
                "shortId": _short_card_id(card["card_id"]),
                "paper": key,
                "category": card.get("category", ""),
                "tier": card.get("evidence_tier", ""),
                "genes": card.get("genes", []),
                "diseases": card.get("diseases", []),
                "ancestors": card.get("disease_ancestors", []),
                "locator": card.get("locator", ""),
                "secondary": card.get("secondary_citation"),
                "text": card.get("interpretation", ""),
                "baseSha256": cul_core.base_digest(card),
                "audit": audit_by_card.get(card["card_id"]),
            }
            if full and paper_details is not None:
                row["details"] = {
                    "card": card,
                    "evidence": evidence_by_card[card["card_id"]],
                }
            cards.append(row)

    papers.sort(key=lambda item: (-(item["year"] or 0), item["nickname"]))
    cards.sort(key=lambda item: item["id"])
    return {
        "corpusVersion": corpus.get("corpus_version"),
        "corpusSha256": corpus_sha256,
        "generatedAt": corpus.get("generated_at"),
        "full": full,
        "evidenceMode": (
            "none" if not full
            else "partial" if (missing_packages or mismatched_packages)
            else "full"
        ),
        "missingPackages": sorted(missing_packages),
        "mismatchedPackages": sorted(mismatched_packages),
        "papers": papers,
        "cards": cards,
        "cul": cul_profile,
        "editor": editor,
        "profiles": profiles or {},
        "vocabulary": _vocabulary(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", type=Path, default=DEFAULT_CORPUS)
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="output HTML path (default changes to evidence/card-browser-full.html with --full)",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="include accepted evidence and enable the full-detail preview pane",
    )
    parser.add_argument(
        "--accept-dir",
        type=Path,
        default=DEFAULT_ACCEPT_DIR,
        help="accepted package directory used by --full (default: accept)",
    )
    parser.add_argument(
        "--edit",
        action="store_true",
        help="build the Corpus User Layer editor instead of the read-only browser",
    )
    args = parser.parse_args()

    if args.edit and args.full:
        parser.error("--edit builds the editor from the corpus alone; --full is not supported")
    output = args.output or (
        DEFAULT_EDIT_OUTPUT if args.edit
        else DEFAULT_FULL_OUTPUT if args.full
        else DEFAULT_OUTPUT
    )
    # Read the corpus given, not the repository's. incorporate.py builds the
    # browser from a corpus it has just written to a temporary directory, whose
    # index is not the one under output/corpus.
    document = _load_json(args.corpus, "corpus")
    corpus_sha256 = hashlib.sha256(corpus_core.canonical_bytes(document)).hexdigest()
    flat = corpus_core.flatten(document)
    profiles = _all_profiles(document, flat)
    # The editor always starts on the default profile; every other profile is
    # embedded and reachable from the dropdown. Starting from an empty scope
    # would let a save silently drop the shipped retrieval rules.
    selected = cul_core.DEFAULT_PROFILE if cul_core.DEFAULT_PROFILE in profiles else None
    cul_profile = profiles[selected] if selected else None

    try:
        data = collect(args.corpus, full=args.full, accept_dir=args.accept_dir,
                       cul_profile=cul_profile, corpus_sha256=corpus_sha256,
                       profiles=profiles, editor=args.edit)
    except ValueError as exc:
        parser.error(str(exc))

    template = TEMPLATE.read_text(encoding="utf-8")
    cul_script = CUL_SCRIPT.read_text(encoding="utf-8")
    template = template.replace("/*__CUL_LAYER__*/", cul_script)
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("</", "<\\/")
    html = template.replace("/*__CARD_DATA__*/null", payload)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html, encoding="utf-8")
    mode = {"none": "corpus-only", "partial": "partial evidence", "full": "full"}[
        data["evidenceMode"]
    ]
    print(f"{output} ({mode}, {len(data['cards'])} cards, {len(data['papers'])} papers)")
    if data["missingPackages"]:
        print(f"  evidence absent for {len(data['missingPackages'])} paper(s)")
    if data["mismatchedPackages"]:
        print(
            "  WARNING: accepted package disagrees with the corpus for "
            f"{len(data['mismatchedPackages'])} paper(s): "
            + ", ".join(data["mismatchedPackages"])
            + "\n  Re-run incorporation."
        )


if __name__ == "__main__":
    main()
