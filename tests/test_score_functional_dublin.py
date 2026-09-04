import json
import unittest
from unittest import mock

from validation.scripts import score_functional_dublin as scorer


def marking_text(results):
    return "## Case test\n\n```json\n" + json.dumps({"criterion_results": results}) + "\n```\n"


def all_met(case_id):
    return {
        criterion_id: {"met": True, "failure_mode": None}
        for criterion_id in scorer._criterion_ids(case_id)
    }


class DublinFunctionalMappingTests(unittest.TestCase):
    def test_mapping_matches_every_canonical_dublin_criterion_exactly_once(self):
        scorer.validate_mapping()
        for case_id in scorer.CASE_CRITERION_TO_FUNCTION:
            canonical = set(scorer._criterion_ids(case_id))
            mapped = scorer.CASE_CRITERION_TO_FUNCTION[case_id]
            self.assertEqual(set(mapped), canonical)
            self.assertTrue(set(mapped.values()).issubset(set(scorer.FUNCTIONS)))

    def test_expected_functional_applicability(self):
        expected = {
            "F1": {"1","2","3","4","5","6","7","8","9","10"},
            "F2": {"1","2","3","4","5","9","10"},
            "F3": {"3","5","8"},
            "F4": {"1","3","4","5","6","7","8","9","10"},
            "F5": {"1","2","9"},
            "F6": {"1","2","3"},
            "F7": {"1","4","7"},
            "F8": {"1","4","7"},
            "F9": {"4","5","6","7","8","10"},
        }
        actual = {f: set() for f in scorer.FUNCTIONS}
        for case_id, mapping in scorer.CASE_CRITERION_TO_FUNCTION.items():
            for function in set(mapping.values()):
                actual[function].add(case_id)
        self.assertEqual(actual, expected)


class DublinFunctionalScoringTests(unittest.TestCase):
    def test_all_met_scores_applicable_functions_met(self):
        score = scorer.score_case("1", marking_text(all_met("1")))
        self.assertEqual(score["functions"]["F1"]["result"], "met")
        self.assertEqual(score["functions"]["F8"]["result"], "met")
        self.assertEqual(score["functions"]["F9"]["result"], "not_applicable")

    def test_omitted_criterion_makes_function_not_met(self):
        results = all_met("1")
        results["R4C1"] = {"met": False, "failure_mode": "omitted"}
        score = scorer.score_case("1", marking_text(results))
        self.assertEqual(score["functions"]["F6"]["result"], "not_met")

    def test_partial_criterion_makes_function_not_met(self):
        results = all_met("6")
        results["R2C3"] = {"met": False, "failure_mode": "partial"}
        score = scorer.score_case("6", marking_text(results))
        self.assertEqual(score["functions"]["F9"]["result"], "not_met")

    def test_contradicted_criterion_makes_function_not_met(self):
        results = all_met("3")
        results["R1C3"] = {"met": False, "failure_mode": "contradicted"}
        score = scorer.score_case("3", marking_text(results))
        self.assertEqual(score["functions"]["F3"]["result"], "not_met")

    def test_missing_criterion_fails_closed(self):
        results = all_met("1")
        results.pop("R1C1")
        with self.assertRaises(scorer.FunctionalScoringError):
            scorer.score_case("1", marking_text(results))

    def test_extra_criterion_fails_closed(self):
        results = all_met("1")
        results["R5C99"] = {"met": True, "failure_mode": None}
        with self.assertRaises(scorer.FunctionalScoringError):
            scorer.score_case("1", marking_text(results))

    def test_malformed_status_fails_closed(self):
        results = all_met("1")
        results["R1C1"] = {"met": True, "failure_mode": "omitted"}
        with self.assertRaises(scorer.FunctionalScoringError):
            scorer.score_case("1", marking_text(results))

    def test_aggregate_excludes_not_applicable_from_denominator(self):
        scores = {
            "1": scorer.score_case("1", marking_text(all_met("1"))),
            "2": scorer.score_case("2", marking_text(all_met("2"))),
        }
        aggregate = scorer.aggregate(scores)
        self.assertEqual(aggregate["F7"]["applicable"], 1)
        self.assertEqual(aggregate["F7"]["met"], 1)
        self.assertEqual(aggregate["F9"]["applicable"], 0)
        self.assertIsNone(aggregate["F9"]["proportion"])


if __name__ == "__main__":
    unittest.main()
