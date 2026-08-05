#!/usr/bin/env python3
"""CLI tests for `scripts/retrieve.py diagnosis`."""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RETRIEVE = ROOT / "scripts" / "retrieve.py"
CORPUS = ROOT / "output" / "corpus" / "nel.corpus.json"
INDEX = ROOT / "output" / "corpus" / "nel.index.json"


def run(*arguments, success=True, cwd=None):
    result = subprocess.run(
        [sys.executable, str(RETRIEVE), *map(str, arguments)],
        capture_output=True, text=True, cwd=cwd,
    )
    output = result.stdout + result.stderr
    if success:
        if result.returncode != 0:
            raise AssertionError(f"unexpected failure:\n{output}")
    else:
        if result.returncode == 0:
            raise AssertionError(f"expected failure but succeeded:\n{output}")
    return output, result.returncode


def write_case_input(path, disease="myeloid neoplasm, unspecified", genes=None, facts=None):
    document = {
        "provisional_disease": disease,
        "genes": genes or ["SF3B1"],
        "case_facts": facts or [{"fact_id": "F1", "type": "variant", "gene": "SF3B1"}],
    }
    path.write_text(json.dumps(document), encoding="utf-8")


class RetrieveDiagnosisCaseInputTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.case_input = self.dir / "case-input.json"
        self.output = self.dir / "step2.json"

    def tearDown(self):
        self.tmp.cleanup()

    def result(self):
        return json.loads(self.output.read_text(encoding="utf-8"))

    def run_case(self, *extra, success=True, cwd=None):
        return run(
            "diagnosis", "--case-input", self.case_input, *extra,
            "--output", self.output, success=success, cwd=cwd,
        )

    def test_loads_all_fields_from_valid_case_input(self):
        facts = [
            {"fact_id": "F-SF3B1", "type": "variant", "gene": "SF3B1", "vaf_percent": 30},
            {"fact_id": "F-CYTO", "type": "workflow_assumption", "finding": "normal cytogenetics assumed"},
        ]
        write_case_input(self.case_input, "MDS", ["SF3B1"], facts)
        self.run_case()
        result = self.result()
        self.assertEqual(result["provisional_disease"], "MDS")
        self.assertEqual(result["genes"], ["SF3B1"])
        self.assertEqual(len(result["case_facts"]), 2)
        self.assertTrue(any(card["card_id"].endswith("-C0009") for card in result["diagnosis_cards"]))

    def test_default_corpus_and_index_paths_are_repository_root_safe(self):
        write_case_input(self.case_input)
        self.run_case(cwd=self.tmp.name)
        result = self.result()
        self.assertEqual(Path(result["corpus"]["path"]).resolve(), CORPUS.resolve())
        self.assertEqual(Path(result["corpus"]["index"]).resolve(), INDEX.resolve())

    def test_explicit_genes_override_case_input(self):
        write_case_input(self.case_input, genes=["SF3B1"])
        output, _ = self.run_case("--genes", "NPM1")
        self.assertIn("overriding case-input genes from --genes", output)
        self.assertEqual(self.result()["genes"], ["NPM1"])
        self.assertTrue(any(card["card_id"].endswith("-C0012") for card in self.result()["diagnosis_cards"]))

    def test_explicit_provisional_disease_override(self):
        write_case_input(self.case_input, disease="myeloid neoplasm, unspecified")
        output, _ = self.run_case("--provisional-disease", "MDS")
        self.assertIn(
            "overriding case-input provisional-disease from --provisional-disease", output
        )
        self.assertEqual(self.result()["provisional_disease"], "MDS")

    def test_explicit_case_facts_override(self):
        write_case_input(self.case_input)
        override_facts = self.dir / "override-facts.json"
        override_facts.write_text(
            json.dumps([{"fact_id": "F-OVR", "type": "test"}]), encoding="utf-8"
        )
        output, _ = self.run_case("--case-facts", override_facts)
        self.assertIn("overriding case-input case-facts from --case-facts", output)
        self.assertEqual(self.result()["case_facts"], [{"fact_id": "F-OVR", "type": "test"}])

    def test_explicit_corpus_and_index_override(self):
        write_case_input(self.case_input)
        self.run_case("--corpus", CORPUS, "--index", INDEX)
        result = self.result()
        self.assertEqual(Path(result["corpus"]["path"]).resolve(), CORPUS.resolve())

    def test_legacy_invocation_still_works(self):
        facts = self.dir / "facts.json"
        facts.write_text(
            json.dumps([{"fact_id": "F1", "type": "variant", "gene": "SF3B1"}]),
            encoding="utf-8",
        )
        run(
            "diagnosis",
            "--genes", "SF3B1",
            "--provisional-disease", "myeloid neoplasm, unspecified",
            "--case-facts", facts,
            "--corpus", CORPUS, "--index", INDEX,
            "--output", self.output,
        )
        result = self.result()
        self.assertEqual(result["genes"], ["SF3B1"])
        self.assertTrue(result["diagnosis_cards"])

    def test_missing_genes_fails(self):
        document = {
            "provisional_disease": "MDS",
            "case_facts": [{"fact_id": "F1", "type": "variant", "gene": "SF3B1"}],
        }
        self.case_input.write_text(json.dumps(document), encoding="utf-8")
        output, _ = self.run_case(success=False)
        self.assertIn("genes", output.lower())

    def test_missing_provisional_disease_fails(self):
        document = {
            "genes": ["SF3B1"],
            "case_facts": [{"fact_id": "F1", "type": "variant", "gene": "SF3B1"}],
        }
        self.case_input.write_text(json.dumps(document), encoding="utf-8")
        output, _ = self.run_case(success=False)
        self.assertIn("provisional_disease", output)

    def test_missing_case_facts_fails(self):
        document = {
            "provisional_disease": "MDS",
            "genes": ["SF3B1"],
        }
        self.case_input.write_text(json.dumps(document), encoding="utf-8")
        output, _ = self.run_case(success=False)
        self.assertIn("case_facts", output)

    def test_invalid_disease_value_fails(self):
        write_case_input(self.case_input, disease="not a real disease")
        output, _ = self.run_case(success=False)
        self.assertIn("disease vocabulary", output)

    def test_non_array_genes_fails(self):
        write_case_input(self.case_input, genes="SF3B1")
        output, _ = self.run_case(success=False)
        self.assertIn("genes", output.lower())

    def test_empty_gene_value_fails(self):
        write_case_input(self.case_input, genes=[""])
        output, _ = self.run_case(success=False)
        self.assertIn("gene", output.lower())

    def test_duplicate_normalised_genes_fail(self):
        write_case_input(self.case_input, genes=["SF3B1", "sf3b1"])
        output, _ = self.run_case(success=False)
        self.assertIn("duplicate", output.lower())

    def test_duplicate_fact_ids_fail(self):
        facts = [
            {"fact_id": "F1", "type": "variant", "gene": "SF3B1"},
            {"fact_id": "F1", "type": "morphology"},
        ]
        write_case_input(self.case_input, facts=facts)
        output, _ = self.run_case(success=False)
        self.assertIn("fact", output.lower())

    def test_malformed_json_fails(self):
        self.case_input.write_text("{ not json", encoding="utf-8")
        output, _ = self.run_case(success=False)
        self.assertIn("json", output.lower())

    def test_extra_top_level_fields_fail(self):
        document = {
            "provisional_disease": "MDS",
            "genes": ["SF3B1"],
            "case_facts": [],
            "extra": True,
        }
        self.case_input.write_text(json.dumps(document), encoding="utf-8")
        output, _ = self.run_case(success=False)
        self.assertIn("exactly", output.lower())

    def test_stale_index_is_refused(self):
        stale = self.dir / "stale-index.json"
        stale.write_text(json.dumps({"corpus_sha256": "0" * 64}), encoding="utf-8")
        write_case_input(self.case_input)
        output, _ = self.run_case(
            "--corpus", CORPUS, "--index", stale, success=False
        )


if __name__ == "__main__":
    unittest.main()