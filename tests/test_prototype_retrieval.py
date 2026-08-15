import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import retrieve  # noqa: E402


def card(card_id, category, genes, diseases):
    return {
        "card_id": card_id,
        "category": category,
        "genes": genes,
        "diseases": diseases,
        "evidence_tier": "guideline criterion",
        "interpretation": "Fixture.",
        "locator": "fixture",
        "publication_key": "fixture",
        "paper_nickname": "Fixture",
        "publication_year": 2026,
        "citation_display": "Fixture citation.",
        "citation_incomplete": [],
        "secondary_citation": None,
    }


class PrototypeRetrievalTests(unittest.TestCase):
    def test_diagnosis_retrieval_is_cmc_or_gene_plus_gene_germline(self):
        cards = [
            card("dx-cmc", "diagnosis", [], ["AML"]),
            card("dx-gene", "diagnosis", ["SF3B1"], ["MDS"]),
            card("dx-other", "diagnosis", [], ["MDS"]),
            card("germ-gene", "germline", ["SF3B1"], []),
            card("germ-other", "germline", ["RUNX1"], []),
            card("prog", "prognosis", ["SF3B1"], ["AML"]),
        ]
        result = retrieve.prototype_step2(
            cards, ["SF3B1"], "AML", [], "AML"
        )
        self.assertEqual(
            {c["card_id"] for c in result["retrieved"]},
            {"dx-cmc", "dx-gene", "germ-gene"},
        )

    def test_changed_cmc_reintroduces_both_cmc_diagnosis_sets_and_gene_escape(self):
        cards = [
            card("dx-old", "diagnosis", [], ["MDS"]),
            card("dx-new", "diagnosis", [], ["AML"]),
            card("dx-gene", "diagnosis", ["SF3B1"], ["MPN"]),
            card("prog-new", "prognosis", ["SF3B1"], ["AML"]),
            card("prog-old", "prognosis", ["SF3B1"], ["MDS"]),
            card("tx-geneless", "treatment", [], ["AML"]),
            card("germ", "germline", ["SF3B1"], []),
        ]
        result = retrieve.prototype_step4(
            cards, ["SF3B1"], "MDS", "AML", []
        )
        ids = {c["card_id"] for c in result["retrieved"]}
        self.assertEqual(ids, {"dx-old", "dx-new", "dx-gene", "prog-new", "tx-geneless", "germ"})
        self.assertNotIn("prog-old", ids)

    def test_unchanged_cmc_omits_diagnosis_from_downstream(self):
        cards = [
            card("dx", "diagnosis", ["SF3B1"], ["MDS"]),
            card("prog", "prognosis", ["SF3B1"], ["MDS"]),
            card("germ", "germline", ["SF3B1"], []),
        ]
        result = retrieve.prototype_step4(cards, ["SF3B1"], "MDS", "MDS", [])
        self.assertEqual({c["card_id"] for c in result["retrieved"]}, {"prog", "germ"})


if __name__ == "__main__":
    unittest.main()
