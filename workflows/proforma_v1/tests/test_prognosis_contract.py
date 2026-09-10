from __future__ import annotations

import unittest

from workflows.proforma_v1.rules import prognosis_contract


class PrognosisContractTests(unittest.TestCase):
    def test_null_tier_allows_reason_that_score_cannot_be_calculated(self):
        doc = {
            "prognostic_frameworks": [
                {
                    "name": "IPSS-M",
                    "tier": None,
                    "reason": "A complete IPSS-M score cannot be calculated from supplied findings alone.",
                }
            ],
            "classification": [],
        }

        self.assertEqual(prognosis_contract(doc, {}, {}), [])

    def test_not_calculable_text_in_tier_is_rejected(self):
        doc = {
            "prognostic_frameworks": [
                {
                    "name": "IPSS-M",
                    "tier": "cannot be calculated",
                    "reason": "IPSS-M is applicable to this disease.",
                }
            ],
            "classification": [],
        }

        issues = prognosis_contract(doc, {}, {})
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].path, "prognostic_frameworks[0].tier")


if __name__ == "__main__":
    unittest.main()
