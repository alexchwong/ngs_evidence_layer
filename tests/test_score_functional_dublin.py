import json
import tempfile
import unittest
from pathlib import Path

from validation.scripts import score_functional_dublin as scorer


def marking_text(results):
    return "## Case test\n\n```json\n" + json.dumps({"criterion_results": results}) + "\n```\n"


def all_met(spec, case_id):
    return {
        criterion_id: {"met": True, "failure_mode": None}
        for criterion_id in scorer._criterion_ids(spec, case_id)
    }


class DublinFunctionalSpecificationTests(unittest.TestCase):
    def setUp(self):
        self.spec = scorer.load_spec()

    def test_spec_document_defines_exactly_f1_to_f9(self):
        self.assertEqual(set(self.spec.functions), {f"F{i}" for i in range(1, 10)})
        self.assertIn("IPSS-M", self.spec.functions["F9"])
        self.assertIn("CPSS-Mol", self.spec.functions["F9"])

    def test_mapping_matches_every_canonical_dublin_criterion_exactly_once(self):
        scorer.validate_mapping(self.spec)
        for case_id in self.spec.case_criteria_to_function:
            canonical = set(scorer._criterion_ids(self.spec, case_id))
            mapped = self.spec.case_criteria_to_function[case_id]
            self.assertEqual(set(mapped), canonical)
            self.assertTrue(set(mapped.values()).issubset(set(self.spec.functions)))

    def test_expected_functional_applicability(self):
        expected = {
            "F1": {"1","2","3","6","7","8","10"},
            "F2": {"1","2","3","4","5","9"},
            "F3": {"3","5","8"},
            "F4": {"1","3","6","9"},
            "F5": {"1","2","9"},
            "F6": {"1","2","3"},
            "F7": {"1","4","7"},
            "F8": {"1","4","7"},
            "F9": {"4","5","6","7","8","10"},
        }
        actual = {f: set() for f in self.spec.functions}
        for case_id, mapping in self.spec.case_criteria_to_function.items():
            for function in set(mapping.values()):
                actual[function].add(case_id)
        self.assertEqual(actual, expected)

    def test_score_uses_mapping_from_document_not_python_constant(self):
        source = self.spec.source.read_text(encoding="utf-8")
        payload = json.loads(scorer.JSON_BLOCK_RE.findall(source)[0])
        payload["case_criteria_to_function"]["1"]["R1C1"] = "F2"
        payload["case_criteria_to_function"]["1"]["R1C2"] = "F1"
        altered = scorer.JSON_BLOCK_RE.sub(
            "```json\n" + json.dumps(payload, indent=2) + "\n```",
            source,
            count=1,
        )
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "spec.md"
            path.write_text(altered, encoding="utf-8")
            spec = scorer.load_spec(path)
            scorer.validate_mapping(spec)
            results = all_met(spec, "1")
            results["R1C1"] = {"met": False, "failure_mode": "omitted"}
            score = scorer.score_case("1", marking_text(results), spec)
            self.assertEqual(score["functions"]["F2"]["result"], "not_met")
            self.assertEqual(score["functions"]["F1"]["result"], "met")


class DublinFunctionalScoringTests(unittest.TestCase):
    def setUp(self):
        self.spec = scorer.load_spec()

    def test_all_met_scores_applicable_functions_met(self):
        score = scorer.score_case("1", marking_text(all_met(self.spec, "1")), self.spec)
        self.assertEqual(score["functions"]["F1"]["result"], "met")
        self.assertEqual(score["functions"]["F8"]["result"], "met")
        self.assertEqual(score["functions"]["F9"]["result"], "not_applicable")

    def test_omitted_criterion_makes_function_not_met(self):
        results = all_met(self.spec, "1")
        results["R4C1"] = {"met": False, "failure_mode": "omitted"}
        score = scorer.score_case("1", marking_text(results), self.spec)
        self.assertEqual(score["functions"]["F6"]["result"], "not_met")

    def test_partial_criterion_makes_function_not_met(self):
        results = all_met(self.spec, "6")
        results["R2C3"] = {"met": False, "failure_mode": "partial"}
        score = scorer.score_case("6", marking_text(results), self.spec)
        self.assertEqual(score["functions"]["F9"]["result"], "not_met")

    def test_contradicted_criterion_makes_function_not_met(self):
        results = all_met(self.spec, "3")
        results["R1C3"] = {"met": False, "failure_mode": "contradicted"}
        score = scorer.score_case("3", marking_text(results), self.spec)
        self.assertEqual(score["functions"]["F3"]["result"], "not_met")

    def test_missing_criterion_fails_closed(self):
        results = all_met(self.spec, "1")
        results.pop("R1C1")
        with self.assertRaises(scorer.FunctionalScoringError):
            scorer.score_case("1", marking_text(results), self.spec)

    def test_extra_criterion_fails_closed(self):
        results = all_met(self.spec, "1")
        results["R5C99"] = {"met": True, "failure_mode": None}
        with self.assertRaises(scorer.FunctionalScoringError):
            scorer.score_case("1", marking_text(results), self.spec)

    def test_malformed_status_fails_closed(self):
        results = all_met(self.spec, "1")
        results["R1C1"] = {"met": True, "failure_mode": "omitted"}
        with self.assertRaises(scorer.FunctionalScoringError):
            scorer.score_case("1", marking_text(results), self.spec)

    def test_aggregate_excludes_not_applicable_from_denominator(self):
        scores = {
            "1": scorer.score_case("1", marking_text(all_met(self.spec, "1")), self.spec),
            "2": scorer.score_case("2", marking_text(all_met(self.spec, "2")), self.spec),
        }
        aggregate = scorer.aggregate(scores, self.spec)
        self.assertEqual(aggregate["F7"]["applicable"], 1)
        self.assertEqual(aggregate["F7"]["met"], 1)
        self.assertEqual(aggregate["F9"]["applicable"], 0)
        self.assertIsNone(aggregate["F9"]["proportion"])


if __name__ == "__main__":
    unittest.main()
