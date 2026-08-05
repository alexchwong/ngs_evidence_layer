#!/usr/bin/env python3
"""Unit tests for structured evidence-card rendering and reference mapping."""

import copy
import importlib.util
import json
import sys
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


render = load("nel_render", "render.py")


def card(
    card_id,
    interpretation,
    category="diagnosis",
    year=2020,
    secondary=None,
    citation="Publication",
    tier="guideline criterion",
    publication_key="pub",
    locator="Fixture label",
    genes=None,
    diseases=None,
    escalates_to=None,
):
    return {
        "card_id": card_id,
        "category": category,
        "genes": genes or ["GENEA"],
        "diseases": diseases or ["MDS"],
        "evidence_tier": tier,
        "interpretation": interpretation,
        "locator": locator,
        "publication_key": publication_key,
        "publication_year": year,
        "citation_display": citation,
        "citation_incomplete": [],
        "secondary_citation": secondary,
        "escalates_to": escalates_to,
    }


def bundle(cards, genes=None):
    return {
        "step": 4,
        "genes": genes or ["GENEA"],
        "provisional_disease": "MDS",
        "refined_disease": "MDS",
        "diagnostic_adjudication": {
            "status": "criteria_met",
            "provisional_disease": "MDS",
            "refined_disease": "MDS",
            "downstream_filter_disease": "MDS",
            "diagnostic_label": None,
            "driven_by": [],
            "criterion_assessment": [],
            "reason": "Fixture.",
        },
        "provenance": {
            "corpus_version": "1.1",
            "corpus_sha256": "0" * 64,
            "retrieved_at": "2026-01-01T00:00:00+00:00",
        },
        "retrieved": cards,
        "suppressed": {"count": 0, "by_disease": {}},
        "not_assessed": [],
    }


class RenderMappingTests(unittest.TestCase):
    def test_evidence_body_renders_complete_structured_card(self):
        cards = [card(
            "C1-1",
            "Interpretation text.",
            category="prognosis",
            tier="multivariable-adjusted",
            locator="Named finding",
            genes=["GENEA", "GENEB"],
            diseases=["MDS", "AML"],
            escalates_to="primary study",
        )]
        text = render.render(bundle(cards))["text"]

        self.assertIn("## Prognostic significance", text)
        self.assertIn("### Named finding", text)
        self.assertIn("- Card ID: `C1-1`", text)
        self.assertIn("- Category: prognosis", text)
        self.assertIn("- Genes: GENEA, GENEB", text)
        self.assertIn("- Disease context: MDS, AML", text)
        self.assertIn("- Evidence tier: multivariable-adjusted", text)
        self.assertIn("- Interpretation: Interpretation text.", text)
        self.assertIn("- Source locator: Named finding", text)
        self.assertIn("- Escalates to: primary study", text)

    def test_card_label_falls_back_to_card_id(self):
        text = render.render(bundle([
            card("C1-1", "Text.", locator=""),
        ]))["text"]
        self.assertIn("### C1-1", text)

    def test_refs_before_references(self):
        text = render.render(bundle([card("C1-1", "Text.")]))["text"]
        self.assertLess(text.index("## Refs"), text.index("## References"))

    def test_one_card_primary_only(self):
        result = render.render(bundle([card("C1-1", "Text.")]))
        self.assertEqual(result["card_reference_map"], [{
            "card_ids": ["C1-1"],
            "primary_refs": [1],
            "secondary_refs": [],
        }])
        self.assertIn("C1-1: primary ref 1", result["text"])

    def test_one_card_primary_and_secondary(self):
        secondary = {
            "display": "Secondary publication",
            "citation_incomplete": [],
        }
        result = render.render(bundle([
            card("C1-1", "Text.", secondary=secondary),
        ]))
        self.assertEqual(result["card_reference_map"], [{
            "card_ids": ["C1-1"],
            "primary_refs": [1],
            "secondary_refs": [2],
        }])
        self.assertIn(
            "C1-1: primary ref 1; secondary ref 2",
            result["text"],
        )

    def test_cards_sharing_primary_are_grouped_in_terminal_map(self):
        cards = [
            card("C1-1", "Same text."),
            card("C1-2", "Same text."),
            card(
                "C1-3",
                "Other text.",
                publication_key="pub-other",
                citation="Other publication",
            ),
        ]
        result = render.render(bundle(cards))
        self.assertIn("C1-1,C1-2: primary ref 1", result["text"])
        self.assertIn("C1-3: primary ref 2", result["text"])

    def test_different_secondary_mappings_not_grouped(self):
        secondary = {
            "display": "Secondary publication",
            "citation_incomplete": [],
        }
        cards = [
            card("C1-1", "Same text."),
            card("C1-2", "Same text.", secondary=secondary),
        ]
        result = render.render(bundle(cards))
        self.assertIn("C1-1: primary ref 1", result["text"])
        self.assertIn(
            "C1-2: primary ref 1; secondary ref 2",
            result["text"],
        )

    def test_primary_and_secondary_roles_not_conflated(self):
        secondary = {
            "display": "Secondary publication",
            "citation_incomplete": [],
        }
        cards = [
            card("C1-1", "Text A.", secondary=secondary),
            card("C1-2", "Text B.", secondary=secondary),
        ]
        result = render.render(bundle(cards))
        self.assertIn(
            "C1-1,C1-2: primary ref 1; secondary ref 2",
            result["text"],
        )
        self.assertNotIn(
            "C1-1: primary ref 1; secondary ref 2",
            result["text"],
        )

    def test_identical_interpretations_remain_separate_cards(self):
        cards = [
            card("C1-1", "Identical text.", locator="First card"),
            card("C1-2", "Identical text.", locator="Second card"),
        ]
        result = render.render(bundle(cards))

        self.assertEqual(len(result["rendered_cards"]), 2)
        self.assertEqual(len(result["rendered_facts"]), 2)
        self.assertEqual(
            [item["card_id"] for item in result["rendered_cards"]],
            ["C1-1", "C1-2"],
        )
        self.assertEqual(result["text"].count("Identical text."), 2)
        self.assertIn("### First card", result["text"])
        self.assertIn("### Second card", result["text"])

    def test_separate_cards_may_produce_multiple_mapping_lines(self):
        secondary = {
            "display": "Secondary publication",
            "citation_incomplete": [],
        }
        cards = [
            card("C1-1", "Identical text."),
            card("C1-2", "Identical text.", secondary=secondary),
        ]
        result = render.render(bundle(cards))
        self.assertEqual(len(result["rendered_cards"]), 2)
        self.assertEqual(len(result["card_reference_map"]), 2)
        self.assertIn("C1-1: primary ref 1", result["text"])
        self.assertIn(
            "C1-2: primary ref 1; secondary ref 2",
            result["text"],
        )

    def test_reference_numbering_first_appearance_deterministic(self):
        cards = [
            card("C1-1", "Text A.", citation="Pub A", publication_key="pub-a"),
            card("C1-2", "Text B.", citation="Pub B", publication_key="pub-b"),
            card("C1-3", "Text C.", citation="Pub A", publication_key="pub-a"),
        ]
        result = render.render(bundle(cards))
        self.assertEqual(
            [reference["number"] for reference in result["references"]],
            [1, 2],
        )
        self.assertEqual(result["references"][0]["display"], "Pub A")
        self.assertEqual(result["references"][1]["display"], "Pub B")

    def test_duplicate_publication_citations_reuse_one_number(self):
        cards = [
            card("C1-1", "Text A.", citation="Pub A", publication_key="pub-a"),
            card("C1-2", "Text B.", citation="Pub A", publication_key="pub-a"),
        ]
        result = render.render(bundle(cards))
        self.assertEqual(len(result["references"]), 1)
        self.assertIn("C1-1,C1-2: primary ref 1", result["text"])

    def test_duplicate_secondary_citations_reuse_one_number(self):
        secondary = {
            "display": "Secondary publication",
            "citation_incomplete": [],
        }
        cards = [
            card("C1-1", "Text A.", secondary=secondary),
            card("C1-2", "Text B.", secondary=secondary),
        ]
        result = render.render(bundle(cards))
        self.assertEqual(len(result["references"]), 2)
        self.assertIn(
            "C1-1,C1-2: primary ref 1; secondary ref 2",
            result["text"],
        )

    def test_missing_citation_placeholder_remains_numbered(self):
        result = render.render(bundle([
            card("C1-1", "Text.", citation=None, publication_key=None),
        ]))
        self.assertEqual(
            result["references"][0]["display"],
            "[citation missing]",
        )
        self.assertIn("C1-1: primary ref 1", result["text"])

    def test_truncated_cards_disappear_from_body_and_all_mappings(self):
        cards = [
            card("C1-1", "Guideline text.", tier="guideline criterion"),
            card("C1-2", "Restated text.", tier="restated secondary"),
        ]
        result = render.render(bundle(cards), token_budget=100)
        self.assertNotIn("C1-2", result["text"])
        self.assertNotIn("C1-2", json.dumps(result["rendered_cards"]))
        self.assertNotIn("C1-2", json.dumps(result["rendered_facts"]))
        self.assertNotIn("C1-2", json.dumps(result["card_reference_map"]))
        self.assertNotIn("Restated text.", result["text"])

    def test_references_used_only_by_truncated_cards_disappear(self):
        cards = [
            card(
                "C1-1",
                "Guideline text.",
                tier="guideline criterion",
                citation="Pub A",
                publication_key="pub-a",
            ),
            card(
                "C1-2",
                "Restated text.",
                tier="restated secondary",
                citation="Pub B",
                publication_key="pub-b",
            ),
        ]
        result = render.render(bundle(cards), token_budget=100)
        self.assertEqual(
            [reference["display"] for reference in result["references"]],
            ["Pub A"],
        )

    def test_json_rendered_cards_and_map_match_markdown(self):
        cards = [
            card("C1-1", "Text A.", locator="Label A"),
            card("C1-2", "Text B.", locator="Label B"),
        ]
        result = render.render(bundle(cards))

        self.assertEqual(result["rendered_facts"], result["rendered_cards"])
        for rendered_card in result["rendered_cards"]:
            self.assertIn(rendered_card["interpretation"], result["text"])
            self.assertIn(
                f"- Card ID: `{rendered_card['card_id']}`",
                result["text"],
            )
            self.assertIn(
                f"### {rendered_card['label']}",
                result["text"],
            )
        for group in result["card_reference_map"]:
            for card_id in group["card_ids"]:
                self.assertIn(card_id, result["text"])

    def test_every_rendered_card_occurs_exactly_once_in_map(self):
        cards = [
            card("C1-1", "Text A."),
            card("C1-2", "Text B."),
            card("C1-3", "Text C."),
        ]
        result = render.render(bundle(cards))
        mapped = [
            card_id
            for group in result["card_reference_map"]
            for card_id in group["card_ids"]
        ]
        rendered = [item["card_id"] for item in result["rendered_cards"]]
        self.assertEqual(sorted(mapped), sorted(rendered))
        self.assertEqual(len(mapped), len(set(mapped)))

    def test_every_mapped_number_resolves_to_bibliography_entry(self):
        secondary = {
            "display": "Secondary publication",
            "citation_incomplete": [],
        }
        result = render.render(bundle([
            card("C1-1", "Text.", secondary=secondary),
        ]))
        numbers = {reference["number"] for reference in result["references"]}
        for group in result["card_reference_map"]:
            for number in group["primary_refs"] + group["secondary_refs"]:
                self.assertIn(number, numbers)

    def test_zero_card_output(self):
        result = render.render(bundle([]))
        self.assertIn("## Refs", result["text"])
        self.assertIn("None; no cards were rendered.", result["text"])
        self.assertIn("## References", result["text"])
        self.assertIn("None; no cards were retrieved.", result["text"])
        self.assertEqual(result["card_reference_map"], [])
        self.assertEqual(result["rendered_facts"], [])
        self.assertEqual(result["rendered_cards"], [])

    def test_repeated_runs_byte_identical(self):
        cards = [
            card("C1-1", "Text A."),
            card(
                "C1-2",
                "Text B.",
                secondary={
                    "display": "Secondary",
                    "citation_incomplete": [],
                },
            ),
        ]
        first = render.render(bundle(cards))
        second = render.render(bundle(copy.deepcopy(cards)))
        self.assertEqual(first["text"], second["text"])
        self.assertEqual(
            first["rendered_cards"],
            second["rendered_cards"],
        )
        self.assertEqual(
            first["card_reference_map"],
            second["card_reference_map"],
        )


if __name__ == "__main__":
    unittest.main()
