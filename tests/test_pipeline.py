#!/usr/bin/env python3
"""End-to-end and unit tests, standard library only.

  python3 -m unittest discover -s tests -v

The fixtures use invented gene symbols (GENEA, GENEB, ...) and an invented
classifier. That is deliberate: a test fixture full of real gene names and
plausible thresholds is one careless copy away from being read as evidence.
"""
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
ALPHA = "fixture-alpha--aaaaaaaa"
BETA = "fixture-beta--bbbbbbbb"

sys.path.insert(0, str(SCRIPTS))


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


vocab = load("nel_vocab", "vocab.py")
make_key = load("nel_make_key", "make_key.py")
validate_cards = load("nel_validate_cards", "validate_cards.py")
retrieve = load("nel_retrieve", "retrieve.py")
render = load("nel_render", "render.py")


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def fixture_paths(stem):
    return {
        "cards": FIXTURES / "papers" / f"{stem}.cards.json",
        "quotes": FIXTURES / "quotes" / f"{stem}.quotes.json",
        "census": FIXTURES / "census" / f"{stem}.census.json",
        "source": FIXTURES / "markdown" / f"{stem}.md",
        "audit": FIXTURES / "audit" / f"{stem}.audit.json",
    }


class VocabularyTests(unittest.TestCase):
    def test_schema_enum_matches_vocabulary_file(self):
        self.assertEqual(vocab.check_vocabulary_consistency(), [])

    def test_umbrella_gaps_are_reported(self):
        self.assertEqual(vocab.missing_umbrellas(["APL"]), ["AML"])
        self.assertEqual(vocab.missing_umbrellas(["APL", "AML"]), [])
        self.assertEqual(vocab.missing_umbrellas(["ET"]), ["MPN-U"])


class KeyTests(unittest.TestCase):
    def test_primary_key_is_deterministic(self):
        citation = {
            "authors": ["Dohner H", "Wei AH"], "title": "Fixture title",
            "journal": "Blood", "year": 2022, "volume": "140", "pages": "1345-1377",
        }
        first = make_key.build_citation(citation)
        second = make_key.build_citation(dict(citation))
        self.assertEqual(first["publication_key"], second["publication_key"])
        self.assertEqual(first["publication_key"], "dohner-2022-blood-140-1345")

    def test_primary_requires_authors_title_year(self):
        with self.assertRaises(ValueError):
            make_key.build_citation({"journal": "Blood", "year": 2022})

    def test_secondary_tolerates_a_partial_reference(self):
        result = make_key.build_citation({"authors": ["Falini B"], "year": 2005},
                                         secondary=True)
        citation = result["citation"]
        self.assertIn("Falini B", citation["display"])
        # Everything the publication's reference list did not supply is named,
        # never patched over.
        self.assertIn("journal", citation["citation_incomplete"])
        self.assertIn("pages", citation["citation_incomplete"])

    def test_secondary_needs_at_least_one_element(self):
        with self.assertRaises(ValueError):
            make_key.build_citation({}, secondary=True)


class ValidationTests(unittest.TestCase):
    def validate_variant(self, mutate, stem=ALPHA):
        """Apply a mutation to the fixture card file and validate the result."""
        paths = fixture_paths(stem)
        document = read(paths["cards"])
        mutate(document)
        with tempfile.TemporaryDirectory() as tmp:
            card_path = Path(tmp) / f"{stem}.cards.json"
            card_path.write_text(json.dumps(document), encoding="utf-8")
            _doc, errors, warnings, report = validate_cards.validate(
                card_path, paths["quotes"], paths["census"], paths["source"]
            )
        return errors, warnings, report

    def test_fixtures_validate_clean(self):
        for stem in (ALPHA, BETA):
            with self.subTest(stem=stem):
                paths = fixture_paths(stem)
                _doc, errors, _warnings, report = validate_cards.validate(
                    paths["cards"], paths["quotes"], paths["census"], paths["source"]
                )
                self.assertEqual(errors, [], f"{stem}: {errors}")
                self.assertIsNotNone(report["ratio"])

    def test_extraction_ratio_is_reported(self):
        paths = fixture_paths(ALPHA)
        _doc, _errors, _warnings, report = validate_cards.validate(
            paths["cards"], paths["quotes"], paths["census"], paths["source"]
        )
        self.assertEqual(report["census_entries"], 4)
        self.assertEqual(report["cards"], 8)
        self.assertEqual(report["genes_with_no_card"], [])

    def test_uncarded_census_gene_is_named(self):
        def drop_germline(document):
            document["cards"] = [
                card for card in document["cards"] if card["category"] != "germline"
            ]
        _errors, _warnings, report = self.validate_variant(drop_germline)
        self.assertIn("GENED", report["genes_with_no_card"])
        self.assertIn(
            {"gene": "GENED", "category": "germline"},
            report["gene_category_pairs_with_no_card"],
        )

    def test_missing_umbrella_tag_is_an_error(self):
        def tag_apl_only(document):
            document["diseases_covered"].append("APL")
            document["cards"][0]["diseases"] = ["APL"]
        errors, _warnings, _report = self.validate_variant(tag_apl_only)
        self.assertTrue(any("umbrella" in error for error in errors), errors)

    def test_escalates_to_outside_diagnosis_is_an_error(self):
        def escalate_a_prognosis_card(document):
            for card in document["cards"]:
                if card["category"] == "prognosis":
                    card["escalates_to"] = "AML"
                    break
        errors, _warnings, _report = self.validate_variant(escalate_a_prognosis_card)
        self.assertTrue(any("escalates_to" in error for error in errors), errors)

    def test_card_without_a_quote_is_rejected(self):
        def add_unquoted_card(document):
            card = copy.deepcopy(document["cards"][0])
            card["card_id"] = document["publication_key"] + "-genea-dx-999"
            document["cards"].append(card)
        errors, _warnings, _report = self.validate_variant(add_unquoted_card)
        self.assertTrue(any("no quote" in error for error in errors), errors)

    def test_quote_absent_from_source_is_rejected(self):
        paths = fixture_paths(ALPHA)
        quotes = read(paths["quotes"])
        quotes["quotes"][0]["quote"] = "GENEA mutation defines nothing whatsoever."
        with tempfile.TemporaryDirectory() as tmp:
            quote_path = Path(tmp) / f"{ALPHA}.quotes.json"
            quote_path.write_text(json.dumps(quotes), encoding="utf-8")
            _doc, errors, _warnings, _report = validate_cards.validate(
                paths["cards"], quote_path, paths["census"], paths["source"]
            )
        self.assertTrue(any("not found in the normalised source" in e for e in errors), errors)

    def test_identical_quote_text_across_roles_is_a_review_warning(self):
        paths = fixture_paths(ALPHA)
        cards = read(paths["cards"])
        quotes = read(paths["quotes"])
        shared_card = copy.deepcopy(cards["cards"][0])
        shared_card["card_id"] = cards["publication_key"] + "-genea-tx-009"
        shared_card["category"] = "treatment"
        shared_card["escalates_to"] = None
        shared_card["interpretation"] = (
            "FIXTURE. In this setting, GENEA has a distinct treatment implication "
            "stated by the shared passage; no treatment line is specified."
        )
        shared_quote = copy.deepcopy(quotes["quotes"][0])
        shared_quote["card_id"] = shared_card["card_id"]
        cards["cards"].append(shared_card)
        quotes["quotes"].append(shared_quote)

        with tempfile.TemporaryDirectory() as tmp:
            card_path = Path(tmp) / f"{ALPHA}.cards.json"
            quote_path = Path(tmp) / f"{ALPHA}.quotes.json"
            card_path.write_text(json.dumps(cards), encoding="utf-8")
            quote_path.write_text(json.dumps(quotes), encoding="utf-8")
            _doc, errors, warnings, _report = validate_cards.validate(
                card_path, quote_path, paths["census"], paths["source"]
            )

        self.assertEqual(errors, [])
        duplicate_warnings = [warning for warning in warnings if "quote is identical" in warning]
        self.assertEqual(len(duplicate_warnings), 1, warnings)
        self.assertIn("different categories", duplicate_warnings[0])
        self.assertIn("may be legitimate", duplicate_warnings[0])

    def test_multiple_quote_records_for_one_card_remain_an_error(self):
        paths = fixture_paths(ALPHA)
        quotes = read(paths["quotes"])
        quotes["quotes"].append(copy.deepcopy(quotes["quotes"][0]))

        with tempfile.TemporaryDirectory() as tmp:
            quote_path = Path(tmp) / f"{ALPHA}.quotes.json"
            quote_path.write_text(json.dumps(quotes), encoding="utf-8")
            _doc, errors, _warnings, _report = validate_cards.validate(
                paths["cards"], quote_path, paths["census"], paths["source"]
            )

        self.assertTrue(any("more than one quote for the same card" in e for e in errors), errors)

    def test_table_quote_survives_markdown_folding(self):
        # A quote lifted from an intact Markdown table must still match the source
        # once pipes and alignment rows are folded away.
        paths = fixture_paths(ALPHA)
        quotes = read(paths["quotes"])
        table_quotes = [q for q in quotes["quotes"] if "|" in q["quote"]]
        self.assertTrue(table_quotes, "fixture should exercise the table path")
        source = validate_cards.normalise(
            paths["source"].read_text(encoding="utf-8"), markdown=True
        )
        for entry in table_quotes:
            self.assertIn(validate_cards.normalise(entry["quote"], markdown=True), source)

    def test_census_count_must_match_the_census_file(self):
        def misdeclare(document):
            document["census_entries"] = 99
        errors, _warnings, _report = self.validate_variant(misdeclare)
        self.assertTrue(any("census_entries" in error for error in errors), errors)

    def test_disposition_must_cite_a_rule_id(self):
        def break_disposition(document):
            for card in document["cards"]:
                if "negative fact" in card["interpretation"]:
                    card["interpretation"] = (
                        "FIXTURE. GENEC had no independent effect "
                        "(negative fact; remove in final pass per the usual rule)."
                    )
                    break
        errors, _warnings, _report = self.validate_variant(break_disposition)
        self.assertTrue(any("rule ID" in error for error in errors), errors)

    def test_quotes_are_required(self):
        paths = fixture_paths(ALPHA)
        _doc, errors, _warnings, _report = validate_cards.validate(
            paths["cards"], None, paths["census"], paths["source"]
        )
        self.assertTrue(any("--quotes is required" in error for error in errors), errors)


class CorpusBuildTests(unittest.TestCase):
    def write_accepted_packages(self, out, audited=True, mutate_audit=None):
        phase1_dir = out / "phase1"
        package_dir = out / ("phase3" if audited else "phase2")
        phase1_dir.mkdir()
        package_dir.mkdir()
        for stem in (ALPHA, BETA):
            census = read(fixture_paths(stem)["census"])
            cards = read(fixture_paths(stem)["cards"])
            quotes = read(fixture_paths(stem)["quotes"])
            package = dict(cards)
            package.pop("audit_model", None)
            package["schema_version"] = "3.0"
            package["quotes"] = quotes["quotes"]
            package["audited"] = audited
            package["audit"] = None
            if audited:
                audit = read(fixture_paths(stem)["audit"])
                package["audit"] = {
                    "audit_date": audit["audit_date"],
                    "audit_model": audit["audit_model"],
                    "extraction_model_reviewed": package["extraction_model"],
                    "results": audit["results"],
                }
                if mutate_audit:
                    mutate_audit(stem, package)
            (phase1_dir / f"{stem}.phase1.json").write_text(
                json.dumps(census), encoding="utf-8"
            )
            phase = 3 if audited else 2
            (package_dir / f"{stem}.phase{phase}.json").write_text(
                json.dumps(package), encoding="utf-8"
            )
        return phase1_dir, package_dir

    def build(self, extra=(), audited=True, mutate_audit=None, expect_success=True):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "reports").mkdir()
            phase1_dir, package_dir = self.write_accepted_packages(
                out, audited=audited, mutate_audit=mutate_audit
            )
            phase = 3 if audited else 2
            command = [
                sys.executable, str(SCRIPTS / "build_corpus.py"),
                "--input-index", str(FIXTURES / "index" / "papers.jsonl"),
                "--markdown-dir", str(FIXTURES / "markdown"),
                "--phase1-dir", str(phase1_dir),
                "--package-dir", str(package_dir),
                "--after-phase", str(phase),
                "--reports-dir", str(out / "reports"),
                "--output-dir", str(out / "corpus"),
                *extra,
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            if expect_success:
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                return read(out / "corpus" / "nel.corpus.json"), read(
                    out / "corpus" / "nel.index.json"
                )
            self.assertNotEqual(result.returncode, 0, result.stdout)
            return result.stdout + result.stderr, None

    def test_corpus_builds_and_indexes(self):
        corpus, index = self.build()
        self.assertEqual(corpus["counts"]["completed_papers"], 2)
        self.assertEqual(corpus["counts"]["cards"], 10)
        self.assertIn("GENEA", index["by_gene"])
        self.assertIn("AML", index["by_escalates_to"])
        self.assertEqual(len(index["by_escalates_to"]["AML"]), 2)

    def test_corpus_contains_no_quote_text(self):
        corpus, _index = self.build()
        serialised = json.dumps(corpus)
        self.assertNotIn("quote", serialised.replace("quote_file_present", ""))
        quote_text = read(fixture_paths(ALPHA)["quotes"])["quotes"][0]["quote"]
        self.assertNotIn(quote_text, serialised)

    def test_unaudited_publication_is_refused(self):
        output, _ = self.build(audited=False, expect_success=False)
        self.assertIn("accepted package is not audited", output)

    def test_audit_by_the_authoring_model_is_refused(self):
        def use_authoring_model(_stem, package):
            package["audit"]["audit_model"] = package["extraction_model"]

        output, _ = self.build(mutate_audit=use_authoring_model, expect_success=False)
        self.assertIn("must differ from the authoring model", output)

    def test_failed_audit_verdict_blocks_the_card(self):
        def fail_first_card(stem, package):
            if stem == ALPHA:
                package["audit"]["results"][0]["verdict"] = "fail"
                package["audit"]["results"][0]["reason"] = "interpretation exceeds its quote"

        output, _ = self.build(mutate_audit=fail_first_card, expect_success=False)
        self.assertIn("audit verdict is 'fail'", output)


class RetrievalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        out = Path(cls.tmp.name)
        (out / "reports").mkdir()
        phase1_dir, package_dir = CorpusBuildTests().write_accepted_packages(out)
        subprocess.run([
            sys.executable, str(SCRIPTS / "build_corpus.py"),
            "--input-index", str(FIXTURES / "index" / "papers.jsonl"),
            "--markdown-dir", str(FIXTURES / "markdown"),
            "--phase1-dir", str(phase1_dir),
            "--package-dir", str(package_dir),
            "--after-phase", "3",
            "--reports-dir", str(out / "reports"),
            "--output-dir", str(out / "corpus"),
        ], check=True, capture_output=True)
        cls.corpus_path = out / "corpus" / "nel.corpus.json"
        cls.index_path = out / "corpus" / "nel.index.json"
        cls.corpus, _index, _digest = retrieve.load_corpus(cls.corpus_path, cls.index_path)
        cls.cards = retrieve.flatten(cls.corpus)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_stale_index_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = read(self.index_path)
            index["corpus_sha256"] = "0" * 64
            stale = Path(tmp) / "stale.index.json"
            stale.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaises(ValueError):
                retrieve.load_corpus(self.corpus_path, stale)

    def test_diagnosis_ignores_the_disease_filter(self):
        result = retrieve.step2(self.cards, ["GENEB"], "AML")
        # The GENEB diagnosis card is tagged MDS. A diagnosis query on an AML case
        # must still see it, because the gene may point away from the marrow label.
        self.assertEqual(len(result["diagnosis_cards"]), 1)
        self.assertEqual(result["diagnosis_cards"][0]["diseases"], ["MDS"])

    def test_escalation_candidates_are_a_closed_set(self):
        result = retrieve.step2(self.cards, ["GENEA"], "MDS")
        self.assertEqual([item["disease"] for item in result["escalation_candidates"]], ["AML"])
        self.assertEqual(len(result["escalation_candidates"][0]["card_ids"]), 2)

    def test_no_escalation_candidate_when_already_at_that_disease(self):
        result = retrieve.step2(self.cards, ["GENEA"], "AML")
        self.assertEqual(result["escalation_candidates"], [])

    def test_two_classifiers_coexist(self):
        result = retrieve.step2(self.cards, ["GENEA"], "MDS")
        keys = {card["publication_key"] for card in result["diagnosis_cards"]}
        self.assertEqual(len(keys), 2)
        thresholds = [card["interpretation"] for card in result["diagnosis_cards"]]
        self.assertTrue(any("at least 20 per cent" in text for text in thresholds))
        self.assertTrue(any("any blast count" in text for text in thresholds))

    def test_suppressed_cards_are_counted_not_dropped(self):
        step2 = retrieve.step2(self.cards, ["GENEA"], "MDS")
        result = retrieve.step4(self.cards, ["GENEA"], "MDS", step2["diagnosis_cards"])
        self.assertEqual(result["suppressed"]["by_disease"], {"AML": 3})
        self.assertTrue(result["suppressed"]["cards"])

    def test_germline_retrieves_on_gene_alone(self):
        step2 = retrieve.step2(self.cards, ["GENED"], "MDS")
        result = retrieve.step4(self.cards, ["GENED"], "MDS", step2["diagnosis_cards"])
        categories = {card["category"] for card in result["retrieved"]}
        self.assertEqual(categories, {"germline"})
        self.assertEqual(result["not_assessed"], [])

    def test_unknown_gene_is_named_individually(self):
        step2 = retrieve.step2(self.cards, ["GENEA", "GENEZ"], "AML")
        result = retrieve.step4(self.cards, ["GENEA", "GENEZ"], "AML", step2["diagnosis_cards"])
        self.assertEqual([item["gene"] for item in result["not_assessed"]], ["GENEZ"])


class RenderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        RetrievalTests.setUpClass()
        cls.cards = RetrievalTests.cards
        cls.corpus_path = RetrievalTests.corpus_path
        cls._owner = RetrievalTests

    @classmethod
    def tearDownClass(cls):
        RetrievalTests.tearDownClass()

    def bundle(self, genes, provisional, refined=None):
        step2 = retrieve.step2(self.cards, genes, provisional)
        refined = refined or provisional
        result = retrieve.step4(self.cards, genes, refined, step2["diagnosis_cards"])
        return {
            "step": 4,
            "genes": sorted(gene.upper() for gene in genes),
            "provisional_disease": provisional,
            "refined_disease": refined,
            "escalation": {"candidates": step2["escalation_candidates"],
                           "applied": refined != provisional, "driven_by": []},
            "provenance": {"corpus_version": "1.0", "corpus_sha256": "0" * 64,
                           "retrieved_at": "2026-01-01T00:00:00+00:00"},
            **result,
        }

    def test_render_is_deterministic(self):
        bundle = self.bundle(["GENEA", "GENEC", "GENED"], "AML")
        first = render.render(bundle)["text"]
        second = render.render(copy.deepcopy(bundle))["text"]
        self.assertEqual(first, second)

    def test_categories_are_ordered(self):
        text = render.render(self.bundle(["GENEA", "GENEC", "GENED"], "AML"))["text"]
        positions = [
            text.index(render.CATEGORY_HEADINGS[category])
            for category in ("diagnosis", "prognosis", "biomarker", "germline")
        ]
        self.assertEqual(positions, sorted(positions))

    def test_identical_interpretations_collapse_and_pool_citations(self):
        text = render.render(self.bundle(["GENEA"], "AML"))["text"]
        marker = "validated fixture follow-up marker"
        self.assertEqual(text.count(marker), 1)
        line = next(line for line in text.splitlines() if marker in line)
        collapsed = text[text.index(line):text.index(line) + 400]
        self.assertIn("[1,2]", collapsed)

    def test_no_quote_text_reaches_the_render(self):
        text = render.render(self.bundle(["GENEA", "GENEB", "GENEC", "GENED"], "AML"))["text"]
        for stem in (ALPHA, BETA):
            for entry in read(fixture_paths(stem)["quotes"])["quotes"]:
                self.assertNotIn(entry["quote"], text)

    def test_secondary_citation_gets_its_own_number(self):
        result = render.render(self.bundle(["GENEC"], "AML"))
        displays = [reference["display"] for reference in result["references"]]
        self.assertTrue(any("An earlier fixture series" in display for display in displays))
        kinds = [reference["kind"] for reference in result["references"]]
        self.assertIn("secondary", kinds)

    def test_incomplete_citation_is_flagged_not_patched(self):
        text = render.render(self.bundle(["GENEC"], "AML"))["text"]
        # The flag wraps across lines, so match the part that cannot break.
        self.assertIn("incomplete in source", text)

    def test_not_assessed_gene_is_named_in_the_block(self):
        text = render.render(self.bundle(["GENEA", "GENEZ"], "AML"))["text"]
        self.assertIn("GENEZ", text)

    def test_truncation_drops_the_weakest_tier_and_renumbers(self):
        bundle = self.bundle(["GENEA", "GENEC", "GENED"], "AML")
        full = render.render(bundle)
        cut = render.render(copy.deepcopy(bundle), token_budget=200)
        self.assertLess(cut["cards_rendered"], full["cards_rendered"])
        self.assertEqual(cut["dropped"][0]["evidence_tier"], "restated secondary")
        # The orphaned secondary reference goes with it, and the list renumbers.
        self.assertLess(len(cut["references"]), len(full["references"]))
        numbers = [reference["number"] for reference in cut["references"]]
        self.assertEqual(numbers, list(range(1, len(numbers) + 1)))

    def test_over_budget_block_warns_rather_than_dropping_guideline_criteria(self):
        result = render.render(self.bundle(["GENEA"], "AML"), token_budget=10)
        self.assertTrue(result["over_budget"])
        self.assertIn("WARNING", result["text"])
        self.assertIn("guideline criterion", "".join(
            card["evidence_tier"] for card in self.bundle(["GENEA"], "AML")["retrieved"]
        ))


if __name__ == "__main__":
    unittest.main()
