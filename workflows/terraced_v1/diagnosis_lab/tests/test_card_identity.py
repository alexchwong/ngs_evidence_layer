import json
import unittest

from scripts.core import card_tags, citations
from workflows.terraced_v1 import card_identity
from workflows.terraced_v1.diagnosis_lab import connector


class DiagnosisLabCardIdentityTests(unittest.TestCase):
    def setUp(self):
        self.cards = [
            {"card_id": "CARD.B", "category": "diagnosis", "interpretation": "B"},
            {"card_id": "CARD.A", "category": "diagnosis", "interpretation": "A"},
        ]

    def test_manifest_is_order_independent_and_12_hex(self):
        first = card_identity.build_manifest(self.cards, corpus_sha256="abc")
        second = card_identity.build_manifest(reversed(self.cards), corpus_sha256="abc")
        self.assertEqual(first, second)
        self.assertEqual(first["tag_length"], 12)
        for row in first["tags"]:
            self.assertRegex(row["card_tag"], r"^[0-9a-f]{12}$")
            self.assertRegex(row["content_sha256"], r"^[0-9a-f]{64}$")

    def test_connector_uses_initialized_global_tags(self):
        manifest = card_identity.build_manifest(self.cards)
        connector.configure_runtime_card_tags(card_identity.runtime_tag_map(manifest))
        tagged, permitted = connector.runtime_cards([self.cards[0]])
        tag = tagged[0]["runtime_card_tag"][6:-1]
        self.assertIn(tag, permitted)
        self.assertEqual(tag, card_identity.tag_by_id(manifest)["CARD.B"])

    def test_citations_accept_new_12_hex_map(self):
        manifest = card_identity.build_manifest(self.cards)
        tag = card_identity.tag_by_id(manifest)["CARD.B"]
        tag_map = card_identity.runtime_tag_map(manifest, ["CARD.B"])
        evidence = (
            "# Evidence\n\n"
            "## Refs\n\n"
            f"{tag}: primary ref 1\n\n"
            "## References\n\n"
            "1. Example reference.\n"
        )
        report = f"**Diagnosis**\nExample diagnosis statement. [card:{tag}]\n"
        rendered = citations.render(
            report,
            evidence,
            json.dumps(tag_map),
            require_citation_after_full_stop=False,
        )
        self.assertIn("Example diagnosis statement [1].", rendered)
        self.assertIn("1. Example reference.", rendered)

    def test_legacy_six_hex_tag_maps_remain_supported(self):
        legacy = card_tags.build_card_tags(["CARD.A"])
        tag = legacy["tags"][0]["card_tag"]
        evidence = (
            "# Evidence\n\n"
            "## Refs\n\n"
            f"{tag}: primary ref 1\n\n"
            "## References\n\n"
            "1. Example reference.\n"
        )
        report = f"**Diagnosis**\nLegacy statement. [card:{tag}]\n"
        rendered = citations.render(
            report,
            evidence,
            json.dumps(legacy),
            require_citation_after_full_stop=False,
        )
        self.assertIn("Legacy statement [1].", rendered)


if __name__ == "__main__":
    unittest.main()
