#!/usr/bin/env python3
"""Regenerate diagnosis_lab input fixtures for repository examples 1-6."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts import vocab
from scripts.core import corpus
from scripts.core import retrieval as core_retrieval

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[2]
FIXTURES = HERE / "fixtures"
PANEL_SCOPE = REPO / "config" / "ngs-panel-scope.md"

EXAMPLES = {
    1: {
        "slug": "01-escalation-fires",
        "provisional_cmcs": ["MDS"],
        "provisional_disease": "MDS",
        "genes": ["NPM1", "DNMT3A", "FLT3"],
        "detected_variants_summary": "NGS detected NPM1 c.863_864insTCTG p.(Trp288CysfsTer12) (VAF 41%), DNMT3A p.(Arg882His) (VAF 46%), and FLT3-ITD (allelic ratio 0.38).",
        "case_facts": [
            {"fact_id": "F1", "kind": "demographics", "value": "68-year-old man."},
            {"fact_id": "F2", "kind": "clinical", "value": "Pancytopenic for three months and transfusion dependent."},
            {"fact_id": "F3", "kind": "morphology", "value": "Marrow reported as MDS with 12% aspirate blasts and dysplasia in two lineages."},
            {"fact_id": "F4", "kind": "cytogenetics", "value": "Normal karyotype on 20 metaphases."},
            {"fact_id": "F5", "kind": "ngs", "value": "NPM1 c.863_864insTCTG p.(Trp288CysfsTer12), VAF 41%."},
            {"fact_id": "F6", "kind": "ngs", "value": "DNMT3A p.(Arg882His), VAF 46%."},
            {"fact_id": "F7", "kind": "ngs", "value": "FLT3-ITD, allelic ratio 0.38."},
        ],
    },
    2: {
        "slug": "02-escalation-does-not-fire",
        "provisional_cmcs": ["MDS"],
        "provisional_disease": "MDS",
        "genes": ["SF3B1", "TET2", "ASXL1"],
        "detected_variants_summary": "NGS detected SF3B1 p.(Lys700Glu) (VAF 38%), TET2 p.(Gln1548Ter) (VAF 22%), and ASXL1 p.(Gly646TrpfsTer12) (VAF 9%).",
        "case_facts": [
            {"fact_id": "F1", "kind": "demographics", "value": "74-year-old woman."},
            {"fact_id": "F2", "kind": "clinical", "value": "Macrocytic anaemia, Hb 92 g/L; not yet transfusion dependent; neutrophils and platelets normal."},
            {"fact_id": "F3", "kind": "morphology", "value": "Hypercellular marrow with erythroid dysplasia and ring sideroblasts; no excess blasts."},
            {"fact_id": "F4", "kind": "cytogenetics", "value": "Normal karyotype."},
            {"fact_id": "F5", "kind": "ngs", "value": "SF3B1 p.(Lys700Glu), VAF 38%."},
            {"fact_id": "F6", "kind": "ngs", "value": "TET2 p.(Gln1548Ter), VAF 22%."},
            {"fact_id": "F7", "kind": "ngs", "value": "ASXL1 p.(Gly646TrpfsTer12), VAF 9%."},
        ],
    },
    3: {
        "slug": "03-ambiguous-disease",
        "provisional_cmcs": ["myeloid neoplasm, unspecified"],
        "provisional_disease": "myeloid neoplasm, unspecified",
        "genes": ["TET2"],
        "detected_variants_summary": "NGS detected TET2 p.(Cys1273Tyr) (VAF 12%); no other variant was detected above the reporting threshold.",
        "case_facts": [
            {"fact_id": "F1", "kind": "demographics", "value": "61-year-old man."},
            {"fact_id": "F2", "kind": "clinical", "value": "Incidental persistent neutropenia: neutrophils 1.4 on three counts over eight months; Hb 128 g/L; platelets 178."},
            {"fact_id": "F3", "kind": "clinical", "value": "B12, folate, copper, thyroid function, viral serology and autoimmune screen unremarkable."},
            {"fact_id": "F4", "kind": "morphology", "value": "Marrow mildly hypocellular for age, no convincing dysplasia, 2% blasts."},
            {"fact_id": "F5", "kind": "cytogenetics", "value": "Normal karyotype."},
            {"fact_id": "F6", "kind": "ngs", "value": "TET2 p.(Cys1273Tyr), VAF 12%."},
            {"fact_id": "F7", "kind": "ngs", "value": "No other variant above the reporting threshold."},
        ],
    },
    4: {
        "slug": "04-genes-the-corpus-cannot-address",
        "provisional_cmcs": ["AML"],
        "provisional_disease": "AML",
        "genes": ["RUNX1", "SRSF2", "CSF3R", "SETBP1"],
        "detected_variants_summary": "NGS at diagnosis detected RUNX1 p.(Arg204Ter) (VAF 44%), SRSF2 p.(Pro95His) (VAF 41%), CSF3R p.(Thr618Ile) (VAF 8%), and SETBP1 p.(Asp868Asn) (VAF 7%).",
        "case_facts": [
            {"fact_id": "F1", "kind": "demographics", "value": "57-year-old woman."},
            {"fact_id": "F2", "kind": "diagnosis", "value": "Known AML."},
            {"fact_id": "F3", "kind": "treatment", "value": "Day 28 marrow after intensive induction."},
            {"fact_id": "F4", "kind": "morphology", "value": "Morphological remission."},
            {"fact_id": "F5", "kind": "ngs", "value": "At diagnosis: RUNX1 p.(Arg204Ter), VAF 44%."},
            {"fact_id": "F6", "kind": "ngs", "value": "At diagnosis: SRSF2 p.(Pro95His), VAF 41%."},
            {"fact_id": "F7", "kind": "ngs", "value": "At diagnosis: CSF3R p.(Thr618Ile), VAF 8%."},
            {"fact_id": "F8", "kind": "ngs", "value": "At diagnosis: SETBP1 p.(Asp868Asn), VAF 7%."},
        ],
    },
    5: {
        "slug": "05-germline-architecture",
        "provisional_cmcs": ["myeloid neoplasm, unspecified"],
        "provisional_disease": "myeloid neoplasm, unspecified",
        "genes": ["DDX41"],
        "detected_variants_summary": "NGS detected DDX41 p.(Met1Ile) (VAF 48%) and DDX41 p.(Arg525His) (VAF 11%).",
        "case_facts": [
            {"fact_id": "F1", "kind": "demographics", "value": "34-year-old man."},
            {"fact_id": "F2", "kind": "family_history", "value": "Two first-degree relatives had haematological malignancy in their forties."},
            {"fact_id": "F3", "kind": "clinical", "value": "Presents with cytopenias."},
            {"fact_id": "F4", "kind": "morphology", "value": "Marrow hypocellular with mild dysplasia."},
            {"fact_id": "F5", "kind": "ngs", "value": "DDX41 p.(Met1Ile), VAF 48%."},
            {"fact_id": "F6", "kind": "ngs", "value": "DDX41 p.(Arg525His), VAF 11%."},
        ],
    },
    6: {
        "slug": "06-sf3b1-diagnostic-adjudication",
        "provisional_cmcs": ["myeloid neoplasm, unspecified"],
        "provisional_disease": "myeloid neoplasm, unspecified",
        "genes": ["SF3B1"],
        "detected_variants_summary": "NGS detected an SF3B1 pathogenic variant (VAF 30%).",
        "case_facts": [
            {"fact_id": "F1", "kind": "demographics", "value": "72-year-old woman."},
            {"fact_id": "F2", "kind": "clinical", "value": "Persistent macrocytic anaemia."},
            {"fact_id": "F3", "kind": "morphology", "value": "Bone marrow has insufficient dysplastic change for a diagnosis of MDS; blasts are not increased."},
            {"fact_id": "F4", "kind": "morphology", "value": "Iron stain shows 7% ring sideroblasts."},
            {"fact_id": "F5", "kind": "ngs", "value": "SF3B1 pathogenic variant, VAF 30%."},
        ],
    },
}


def _selected_cards(genes: list[str], cmcs: list[str]) -> tuple[list[dict], str]:
    corpus_doc, _index, digest = corpus.load_corpus(corpus.DEFAULT_CORPUS, corpus.DEFAULT_INDEX)
    cards = corpus.blacklist_cards(corpus.flatten(corpus_doc), corpus.DEFAULT_BLACKLIST)
    wanted = {g.upper() for g in genes}
    hits = []
    for card in cards:
        matched_genes = core_retrieval.match_genes(card, wanted)
        matched_cmcs = core_retrieval._matches_case_major_category(card, cmcs)
        if card.get("category") == "diagnosis":
            if not matched_genes and not matched_cmcs:
                continue
        elif card.get("category") == "germline":
            if not matched_genes:
                continue
        else:
            continue
        hit = {
            "card_id": card.get("card_id"),
            "category": card.get("category"),
            "genes": card.get("genes") or [],
            "diseases": card.get("diseases") or [],
            "evidence_tier": card.get("evidence_tier"),
            "interpretation": card.get("interpretation"),
            "paper_nickname": card.get("paper_nickname"),
            "publication_year": card.get("publication_year"),
            "matched_genes": matched_genes,
            "matched_case_major_categories": matched_cmcs,
        }
        hits.append(hit)
    hits.sort(key=lambda row: row["card_id"] or "")
    return hits, digest


def build() -> None:
    panel_text = PANEL_SCOPE.read_text(encoding="utf-8")
    for number, meta in EXAMPLES.items():
        slug = meta["slug"]
        case_path = REPO / "examples" / "cases" / f"{slug}.md"
        expected_path = REPO / "examples" / "expected" / f"{slug}.md"
        case_text = case_path.read_text(encoding="utf-8")
        expected_text = expected_path.read_text(encoding="utf-8")
        case_input = {k: v for k, v in meta.items() if k != "slug"}
        cards, digest = _selected_cards(case_input["genes"], case_input["provisional_cmcs"])
        fixture = {
            "schema_version": 1,
            "example": number,
            "slug": slug,
            "source_case_path": str(case_path.relative_to(REPO)),
            "source_expected_path": str(expected_path.relative_to(REPO)),
            "case_notes": case_text,
            "structured_case": case_input,
            "ngs_panel_scope": panel_text,
            "allowed_provisional_cmcs": list(vocab.CASE_MAJOR_CATEGORIES),
            "allowed_schema_diseases": list(vocab.CASE_DISEASES),
            "diagnosis_evidence_cards": cards,
            "corpus_digest": digest,
        }
        out_dir = FIXTURES / f"example-{number:02d}"
        out_dir.mkdir(parents=True, exist_ok=True)
        out = out_dir / "input.json"
        out.write_text(json.dumps(fixture, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        digest_path = out_dir / "input.sha256"
        digest_path.write_text(hashlib.sha256(out.read_bytes()).hexdigest() + "\n", encoding="utf-8")
        (out_dir / "expected.md").write_text(expected_text, encoding="utf-8")
        print(f"wrote {out.relative_to(REPO)} ({len(cards)} diagnosis/germline cards)")


if __name__ == "__main__":
    build()
