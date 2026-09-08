import json
import unittest
from pathlib import Path

from workflows.proforma_v1 import model_context, runtime


HERE = Path(__file__).resolve().parents[1]


class ConcurrentPathologyAliasTests(unittest.TestCase):
    def test_simple_three_letter_protein_substitution_aliases(self):
        self.assertEqual(model_context.protein_substitution_alias("KIT NM_000222.3:c.2447A>T p.(Asp816Val)"), "D816V")
        self.assertEqual(model_context.protein_substitution_alias("MYD88 p.Leu265Pro"), "L265P")
        self.assertEqual(model_context.protein_substitution_alias("TP53 p.(Arg175His)"), "R175H")

    def test_complex_or_unsupported_protein_hgvs_has_no_alias(self):
        for text in (
            "NPM1 p.Trp288CysfsTer12",
            "GENE p.Gly12_Gly13insArg",
            "GENE c.123+1G>A",
            "GENE p.?",
        ):
            self.assertIsNone(model_context.protein_substitution_alias(text))

    def test_model_registry_adds_alias_without_changing_description(self):
        reg = {
            "v01": {
                "variant_id": "V1",
                "gene": "KIT",
                "description": "KIT NM_000222.3:c.2447A>T p.(Asp816Val)",
                "event_type": "sequence_variant",
                "vaf": "12%",
            }
        }
        projected = model_context.canonical_registry(reg, fields=model_context.DIAGNOSIS_REGISTRY_FIELDS)
        self.assertEqual(projected["v01"]["protein_alias"], "D816V")
        self.assertEqual(projected["v01"]["description"], reg["v01"]["description"])
        self.assertNotIn("variant_id", projected["v01"])

    def test_concurrent_pathology_projection_accepts_default_and_v2_terms(self):
        for classification in ("diagnostic_for_other_pathology", "suspicious_for_other_pathology"):
            who = {
                "variant_assessments": [{
                    "variant_id": "v01",
                    "classification": classification,
                    "other_pathology": "systemic mastocytosis",
                    "reason": "Strong signal warrants investigation.",
                }]
            }
            self.assertEqual(runtime.concurrent_pathology_from_who(who), [{
                "variant_id": "v01",
                "other_pathology": "systemic mastocytosis",
                "reason": "Strong signal warrants investigation.",
            }])

    def test_shared_schema_remains_backward_compatible(self):
        schema = json.loads((HERE / "schemas" / "diagnosis_who5.json").read_text(encoding="utf-8"))
        item = schema["properties"]["variant_assessments"]["items"]
        values = item["properties"]["classification"]["enum"]
        self.assertIn("diagnostic_for_other_pathology", values)
        self.assertIn("suspicious_for_other_pathology", values)


if __name__ == "__main__":
    unittest.main()
