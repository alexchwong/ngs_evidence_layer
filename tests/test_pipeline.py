#!/usr/bin/env python3
"""Unit and end-to-end tests for validation, incorporation, retrieval, and render."""
import copy
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURES = ROOT / "tests" / "fixtures"
WORK_FIXTURES = FIXTURES / "work"
ALPHA = "fixture-alpha--aaaaaaaa"
BETA = "fixture-beta--bbbbbbbb"
IDS = {ALPHA: "aaaaaaaa-0000-0000-0000-000000000001", BETA: "bbbbbbbb-0000-0000-0000-000000000002"}
sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vocab = load("nel_vocab", "vocab.py")
make_key = load("nel_make_key", "make_key.py")
validation = load("nel_validation", "package_validation.py")
retrieve = load("nel_retrieve", "retrieve.py")
render = load("nel_render", "render.py")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fixture_folder(stem):
    return WORK_FIXTURES / IDS[stem]


def fixture_package(stem, final=True):
    fixture = fixture_folder(stem)
    metadata = read(fixture / "metadata.json")
    census = read(fixture / "paper.census.json")
    package = read(fixture / ("paper.final.json" if final else "paper.provisional-001.json"))
    return metadata, census, package


def write_accept(accept_dir, stem, mutate=None, accepted_at="2026-01-01T00:00:00+00:00"):
    metadata, census, package = fixture_package(stem)
    if mutate:
        mutate(metadata, census, package)
    paper_id = metadata["paper_id"]
    envelope = {
        "schema_version": "1.1", "acceptance_path": "confirmed",
        "accepted_at": accepted_at, "accepted_at_source": "confirm",
        "metadata": metadata, "final": package,
    }
    (accept_dir / f"{paper_id}.final.json").write_text(json.dumps(envelope), encoding="utf-8")
    (accept_dir / f"{paper_id}.census.json").write_text(json.dumps(census), encoding="utf-8")


def build_fixture_corpus(root):
    accept = root / "accept"
    accept.mkdir()
    for stem in (ALPHA, BETA):
        write_accept(accept, stem)
    output = root / "corpus"
    report = root / "build-report.json"
    subprocess.run([
        sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
        "--output-dir", str(output), "--report", str(report),
        "--generated-at", "2026-01-01T00:00:00+00:00",
    ], check=True, capture_output=True)
    return output / "nel.corpus.json", output / "nel.index.json"


class VocabularyAndKeyTests(unittest.TestCase):
    def test_vocabulary_schema_and_umbrellas(self):
        self.assertEqual(vocab.check_vocabulary_consistency(), [])
        self.assertEqual(vocab.missing_umbrellas(["APL"]), ["AML"])
        self.assertEqual(vocab.missing_umbrellas(["APL", "AML"]), [])

    def test_primary_key_is_deterministic(self):
        citation = {"authors": ["Dohner H"], "title": "Fixture", "journal": "Blood", "year": 2022, "volume": "140", "pages": "1345-1377"}
        self.assertEqual(make_key.build_citation(citation), make_key.build_citation(dict(citation)))

    def test_secondary_partial_citation_is_flagged(self):
        citation = make_key.build_citation({"authors": ["Falini B"], "year": 2005}, secondary=True)["citation"]
        self.assertIn("journal", citation["citation_incomplete"])


class ValidationTests(unittest.TestCase):
    def validate(self, mutate=None, source=True):
        metadata, census, package = fixture_package(ALPHA, final=False)
        if mutate:
            mutate(metadata, census, package)
        text = (fixture_folder(ALPHA) / "paper.md").read_text(encoding="utf-8") if source else None
        return validation.validate_package(package, metadata, census, text, False)

    def test_fixture_validates_and_reports_ratio(self):
        errors, _warnings, report = self.validate()
        self.assertEqual(errors, [])
        self.assertEqual(report["cards"], 8)
        self.assertEqual(report["ratio"], 2.0)

    def test_missing_umbrella_and_non_diagnosis_escalation_fail(self):
        def mutate(_metadata, _census, package):
            package["cards"][0]["diseases"] = ["APL"]
            package["cards"][2]["escalates_to"] = "AML"
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})
        errors, _warnings, _report = self.validate(mutate)
        self.assertTrue(any("umbrella" in error for error in errors), errors)
        self.assertTrue(any("diagnosis cards" in error for error in errors), errors)

    def test_pairing_and_verbatim_quote_failures(self):
        def mutate(_metadata, _census, package):
            package["quotes"].pop()
            package["quotes"][0]["quote"] = "not in source"
        errors, _warnings, _report = self.validate(mutate)
        self.assertTrue(any("no quote" in error for error in errors), errors)
        self.assertTrue(any("not found verbatim" in error for error in errors), errors)

    def test_identical_quote_is_warning_not_failure(self):
        def mutate(_metadata, _census, package):
            card = copy.deepcopy(package["cards"][0])
            card.update(card_id=package["cards"][0]["card_id"] + "-other", category="treatment", escalates_to=None)
            quote = copy.deepcopy(package["quotes"][0]); quote["card_id"] = card["card_id"]
            package["cards"].append(card); package["quotes"].append(quote)
            package["genes_covered"] = sorted({g for c in package["cards"] for g in c["genes"]})
        errors, warnings, _report = self.validate(mutate)
        self.assertEqual(errors, [])
        self.assertTrue(any("identical" in warning for warning in warnings))

    def test_disease_dependent_card_requires_disease_but_germline_does_not(self):
        def remove_disease(_metadata, _census, package):
            package["cards"][0]["diseases"] = []
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})
        errors, _warnings, _report = self.validate(remove_disease)
        self.assertTrue(any("diseases" in error and "non-empty" in error for error in errors), errors)

        def gene_only_germline(_metadata, _census, package):
            package["cards"][0]["category"] = "germline"
            package["cards"][0]["diseases"] = []
            package["cards"][0]["escalates_to"] = None
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})
        errors, _warnings, _report = self.validate(gene_only_germline)
        self.assertEqual(errors, [])

    def test_reference_list_quote_is_rejected(self):
        def mutate(_metadata, _census, package):
            package["quotes"][0]["quote"] = (
                "- 7. Beck DB, et al. Somatic mutations in UBA1. "
                "N Engl J Med. 2020;383:2628-38."
            )
        errors, _warnings, _report = self.validate(mutate, source=False)
        self.assertTrue(any("bibliographic reference-list entry" in error for error in errors), errors)

    def test_generic_category_boilerplate_is_warning(self):
        def mutate(_metadata, _census, package):
            package["cards"][0]["interpretation"] += (
                " Application remains dependent on the source-stated disease context."
            )
        errors, warnings, _report = self.validate(mutate)
        self.assertEqual(errors, [])
        self.assertTrue(any("generic category boilerplate" in warning for warning in warnings), warnings)


class IncorporationTests(unittest.TestCase):
    def test_builds_indexes_and_strips_quotes(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_path, index_path = build_fixture_corpus(Path(tmp))
            corpus, index = read(corpus_path), read(index_path)
            self.assertEqual(corpus["counts"]["cards"], 10)
            self.assertEqual(len(index["by_escalates_to"]["AML"]), 2)
            self.assertNotIn('"quote"', json.dumps(corpus))
            self.assertNotIn("provisional", corpus)

    def test_invalid_paper_is_rejected_without_blocking_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, accept = Path(tmp), Path(tmp) / "accept"; accept.mkdir()
            write_accept(accept, ALPHA)
            write_accept(accept, BETA, lambda _m, _c, p: p.update(audit=None))
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus"), "--report", str(root / "report.json"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(read(root / "corpus" / "nel.corpus.json")["counts"]["completed_papers"], 1)
            self.assertIn(IDS[BETA], read(root / "report.json")["rejected"])

    def test_duplicate_publication_key_retains_earliest_acceptance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, accept = Path(tmp), Path(tmp) / "accept"; accept.mkdir()
            write_accept(accept, ALPHA, accepted_at="2026-01-02T00:00:00+00:00")
            def duplicate(metadata, census, package):
                alpha_metadata, alpha_census, _alpha_package = fixture_package(ALPHA)
                metadata["publication_key"] = alpha_metadata["publication_key"]
                census["publication_type"] = package["publication_type"]
                census["publication_type_basis"] = package["publication_type_basis"]
                for card in package["cards"]:
                    card["card_id"] = card["card_id"].replace(
                        "fixture-2022-second-fixture-journal-2-1", alpha_metadata["publication_key"]
                    )
                for quote in package["quotes"]:
                    quote["card_id"] = quote["card_id"].replace(
                        "fixture-2022-second-fixture-journal-2-1", alpha_metadata["publication_key"]
                    )
                for result in package["audit"]["results"]:
                    result["card_id"] = result["card_id"].replace(
                        "fixture-2022-second-fixture-journal-2-1", alpha_metadata["publication_key"]
                    )
            write_accept(accept, BETA, duplicate, accepted_at="2026-01-01T00:00:00+00:00")
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus"), "--report", str(root / "report.json"),
            ], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = read(root / "report.json")
            self.assertIn(IDS[ALPHA], report["rejected"])
            self.assertEqual(read(root / "corpus" / "nel.corpus.json")["counts"]["completed_papers"], 1)

    def test_manual_missing_timestamp_is_persisted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, accept = Path(tmp), Path(tmp) / "accept"; accept.mkdir()
            write_accept(accept, ALPHA)
            path = accept / f"{IDS[ALPHA]}.final.json"
            envelope = read(path)
            envelope.pop("accepted_at"); envelope.pop("accepted_at_source")
            envelope["schema_version"] = "1.0"
            envelope["acceptance_path"] = "manual-or-unverified"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus"), "--report", str(root / "report.json"),
            ], check=True, capture_output=True)
            persisted = read(path)
            self.assertEqual(persisted["accepted_at_source"], "file-mtime")
            first = persisted["accepted_at"]
            path.touch()
            subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus2"), "--report", str(root / "report2.json"),
            ], check=True, capture_output=True)
            self.assertEqual(read(path)["accepted_at"], first)


class RetrievalAndRenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.corpus_path, cls.index_path = build_fixture_corpus(Path(cls.tmp.name))
        cls.corpus, _index, _digest = retrieve.load_corpus(cls.corpus_path, cls.index_path)
        cls.cards = retrieve.flatten(cls.corpus)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def bundle(self, genes, provisional, refined=None):
        step2 = retrieve.step2(self.cards, genes, provisional)
        refined = refined or provisional
        return {
            "step": 4, "genes": sorted(genes), "provisional_disease": provisional,
            "refined_disease": refined,
            "escalation": {"candidates": step2["escalation_candidates"], "applied": refined != provisional, "driven_by": []},
            "provenance": {"corpus_version": "1.1", "corpus_sha256": "0" * 64, "retrieved_at": "2026-01-01T00:00:00+00:00"},
            **retrieve.step4(self.cards, genes, refined, step2["diagnosis_cards"]),
        }

    def test_stale_index_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = read(self.index_path); index["corpus_sha256"] = "0" * 64
            stale = Path(tmp) / "index.json"; stale.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaises(ValueError): retrieve.load_corpus(self.corpus_path, stale)

    def test_diagnosis_escalation_and_suppression(self):
        diagnosis = retrieve.step2(self.cards, ["GENEA"], "MDS")
        self.assertEqual([item["disease"] for item in diagnosis["escalation_candidates"]], ["AML"])
        full = retrieve.step4(self.cards, ["GENEA"], "MDS", diagnosis["diagnosis_cards"])
        self.assertEqual(full["suppressed"]["by_disease"], {"AML": 3})

    def test_germline_and_unknown_gene_behavior(self):
        diagnosis = retrieve.step2(self.cards, ["GENED", "GENEZ"], "MDS")
        full = retrieve.step4(self.cards, ["GENED", "GENEZ"], "MDS", diagnosis["diagnosis_cards"])
        self.assertIn("germline", {card["category"] for card in full["retrieved"]})
        self.assertEqual([item["gene"] for item in full["not_assessed"]], ["GENEZ"])

    def test_render_is_deterministic_citable_and_quote_free(self):
        bundle = self.bundle(["GENEA", "GENEC", "GENED"], "AML")
        first, second = render.render(bundle), render.render(copy.deepcopy(bundle))
        self.assertEqual(first["text"], second["text"])
        self.assertTrue(first["references"])
        for stem in (ALPHA, BETA):
            provisional = read(fixture_folder(stem) / "paper.provisional-001.json")
            for quote in provisional["quotes"]:
                self.assertNotIn(quote["quote"], first["text"])

    def test_render_truncates_weakest_first(self):
        result = render.render(self.bundle(["GENEA", "GENEC", "GENED"], "AML"), token_budget=200)
        self.assertEqual(result["dropped"][0]["evidence_tier"], "restated secondary")


if __name__ == "__main__":
    unittest.main()