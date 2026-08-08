#!/usr/bin/env python3
"""Tests for case-only disease handling and directional retrieval_related expansion."""

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vocab = load("nel_vocab_retrieval_related", "vocab.py")
retrieve = load("nel_retrieve_retrieval_related", "retrieve.py")
render = load("nel_render_retrieval_related", "render.py")


def card(card_id, disease, category="prognosis", gene="ASXL1"):
    return {
        "card_id": card_id,
        "category": category,
        "genes": [gene],
        "diseases": [disease] if disease is not None else [],
        "evidence_tier": "univariable or descriptive",
        "interpretation": f"{card_id} interpretation",
        "locator": "fixture",
        "publication_key": "fixture",
        "publication_year": 2026,
        "citation_display": "Fixture citation",
        "citation_incomplete": [],
        "secondary_citation": None,
    }


class RetrievalRelatedVocabularyTests(unittest.TestCase):
    def test_case_only_disease_does_not_widen_ingestion_vocabulary(self):
        self.assertNotIn(vocab.NO_HAEMATOLOGICAL_MALIGNANCY, vocab.DISEASE_SET)
        self.assertIn(vocab.NO_HAEMATOLOGICAL_MALIGNANCY, vocab.CASE_DISEASE_SET)
        self.assertEqual(vocab.check_vocabulary_consistency(), [])

    def test_umbrella_taxonomy_is_unchanged(self):
        self.assertEqual(vocab.disease_ancestors(["post-PV/post-ET MF"]), ["MPN"])
        self.assertEqual(vocab.disease_ancestors(["CMML"]), ["MDS", "MDS/MPN", "MPN"])

    def test_related_relationships_are_direct_category_specific_and_directional(self):
        self.assertEqual(
            vocab.retrieval_related_diseases("post-PV/post-ET MF", "treatment"),
            ["PMF", "MPN"],
        )
        self.assertEqual(
            vocab.retrieval_related_diseases("MDS", "biomarker"),
            ["CCUS", "CHIP"],
        )
        self.assertEqual(vocab.retrieval_related_diseases("MDS", "treatment"), [])
        self.assertEqual(vocab.retrieval_related_diseases("MPN", "prognosis"), [])


class NoHaematologicalMalignancyTests(unittest.TestCase):
    def write_case(self, disease, genes):
        tmp = tempfile.TemporaryDirectory()
        path = Path(tmp.name) / "case-input.json"
        path.write_text(
            json.dumps({
                "provisional_disease": disease,
                "genes": genes,
                "case_facts": [
                    {
                        "fact_id": "F-NGS",
                        "type": "test_result_status",
                        "test": "NGS",
                        "complete_reported_findings": True,
                    }
                ],
            }),
            encoding="utf-8",
        )
        return tmp, path

    def test_empty_genes_are_allowed_for_no_malignancy(self):
        tmp, path = self.write_case(vocab.NO_HAEMATOLOGICAL_MALIGNANCY, [])
        try:
            result = retrieve.validate_case_input(path)
            self.assertEqual(result["genes"], [])
            self.assertEqual(result["provisional_disease"], vocab.NO_HAEMATOLOGICAL_MALIGNANCY)
            step2 = retrieve.step2([], [], vocab.NO_HAEMATOLOGICAL_MALIGNANCY, result["case_facts"])
            self.assertEqual(step2["diagnosis_cards"], [])
            self.assertIn(vocab.NO_HAEMATOLOGICAL_MALIGNANCY, step2["allowed_refined_diseases"])
        finally:
            tmp.cleanup()

    def test_no_malignancy_is_rejected_when_a_variant_gene_is_present(self):
        tmp, path = self.write_case(vocab.NO_HAEMATOLOGICAL_MALIGNANCY, ["TET2"])
        try:
            with self.assertRaisesRegex(ValueError, "requires no reported variants"):
                retrieve.validate_case_input(path)
        finally:
            tmp.cleanup()

    def test_empty_genes_are_allowed_for_specified_case_disease(self):
        tmp, path = self.write_case("MDS", [])
        try:
            result = retrieve.validate_case_input(path)
            self.assertEqual(result["provisional_disease"], "MDS")
            self.assertEqual(result["genes"], [])
            step2 = retrieve.step2([], [], "MDS", result["case_facts"])
            self.assertNotIn(
                vocab.NO_HAEMATOLOGICAL_MALIGNANCY,
                step2["allowed_refined_diseases"],
            )
        finally:
            tmp.cleanup()


class RetrievalRelatedStep4Tests(unittest.TestCase):
    def test_secondary_mf_retrieves_exact_pmf_and_mpn_cards(self):
        cards = [
            card("exact", "post-PV/post-ET MF", "prognosis"),
            card("pmf-prog", "PMF", "prognosis"),
            card("pmf-tx", "PMF", "treatment"),
            card("mpn-biomarker", "MPN", "biomarker"),
            card("aml", "AML", "prognosis"),
        ]
        result = retrieve.step4(cards, ["ASXL1"], "post-PV/post-ET MF", [])
        hits = {item["card_id"]: item for item in result["retrieved"]}
        self.assertEqual(set(hits), {"exact", "pmf-prog", "pmf-tx", "mpn-biomarker"})
        self.assertEqual(hits["exact"]["retrieval_match"], "exact")
        self.assertEqual(hits["pmf-prog"]["retrieval_match"], "related")
        self.assertEqual(hits["pmf-tx"]["retrieval_match"], "related")
        self.assertEqual(hits["mpn-biomarker"]["retrieval_match"], "related")
        self.assertEqual(result["suppressed"]["by_disease"], {"AML": 1})
        self.assertEqual(
            result["retrieval_scope"]["retrieval_related"]["treatment"],
            ["PMF", "MPN"],
        )

    def test_mds_borrows_ch_ccus_only_in_configured_categories(self):
        cards = [
            card("mds-tx", "MDS", "treatment", gene="TET2"),
            card("ccus-prog", "CCUS", "prognosis", gene="TET2"),
            card("chip-biomarker", "CHIP", "biomarker", gene="TET2"),
            card("chip-tx", "CHIP", "treatment", gene="TET2"),
        ]
        result = retrieve.step4(cards, ["TET2"], "MDS", [])
        hits = {item["card_id"]: item for item in result["retrieved"]}
        self.assertEqual(set(hits), {"mds-tx", "ccus-prog", "chip-biomarker"})
        self.assertEqual(hits["ccus-prog"]["retrieval_match"], "related")
        self.assertEqual(hits["chip-biomarker"]["retrieval_match"], "related")
        self.assertEqual(result["suppressed"]["by_disease"], {"CHIP": 1})

    def test_related_retrieval_is_directional_not_transitive_or_umbrella_based(self):
        # MPN is an umbrella ancestor of PMF, but MPN has no retrieval_related rule
        # borrowing PMF evidence. Taxonomy therefore does not widen retrieval.
        pmf_card = card("pmf", "PMF", "prognosis", gene="JAK2")
        result = retrieve.step4([pmf_card], ["JAK2"], "MPN", [])
        self.assertEqual(result["retrieved"], [])
        self.assertEqual(result["suppressed"]["count"], 1)

        # CHIP borrows CCUS biomarker evidence, but not MDS biomarker evidence even
        # though CCUS itself is configured to borrow MDS. No transitive expansion.
        mds_card = card("mds", "MDS", "biomarker", gene="TET2")
        result = retrieve.step4([mds_card], ["TET2"], "CHIP", [])
        self.assertEqual(result["retrieved"], [])
        self.assertEqual(result["suppressed"]["count"], 1)

    def test_diagnosis_is_disease_filtered_and_germline_remains_gene_only(self):
        diagnosis = card("dx", "AML", "diagnosis", gene="RUNX1")
        diagnosis["matched_genes"] = ["RUNX1"]
        germline = card("germline", "AML", "germline", gene="RUNX1")
        result = retrieve.step4(
            [diagnosis, germline], ["RUNX1"], "MDS", [diagnosis]
        )
        hits = {item["card_id"]: item for item in result["retrieved"]}
        self.assertEqual(set(hits), {"germline"})
        self.assertEqual(hits["germline"]["retrieval_match"], "gene_only")
        self.assertEqual(result["suppressed"]["by_disease"], {"AML": 1})
        self.assertEqual(
            {item["card_id"] for item in result["suppressed"]["cards"]},
            {"dx"},
        )

    def test_render_exposes_related_match_without_changing_card_disease_context(self):
        pmf = card("pmf-prog", "PMF", "prognosis")
        result = retrieve.step4([pmf], ["ASXL1"], "post-PV/post-ET MF", [])
        bundle = {
            "step": 4,
            "genes": ["ASXL1"],
            "provisional_disease": "post-PV/post-ET MF",
            "refined_disease": "post-PV/post-ET MF",
            "diagnostic_adjudication": {
                "status": "indeterminate",
                "provisional_disease": "post-PV/post-ET MF",
                "refined_disease": "post-PV/post-ET MF",
                "downstream_filter_disease": "post-PV/post-ET MF",
                "diagnostic_label": None,
                "driven_by": [],
                "criterion_assessment": [],
                "reason": "Fixture.",
                "user_review": {
                    "decision": "agree",
                    "diagnostic_label": None,
                    "refined_disease": "post-PV/post-ET MF",
                },
            },
            "provenance": {
                "corpus_version": "test",
                "corpus_sha256": "0" * 64,
                "retrieved_at": "2026-08-07T00:00:00+00:00",
            },
            **result,
        }
        rendered = render.render(bundle)["text"]
        self.assertIn("Disease context: PMF", rendered)
        self.assertIn("Retrieval match: related", rendered)
        self.assertIn("Matched retrieval_related disease: PMF", rendered)


if __name__ == "__main__":
    unittest.main()
