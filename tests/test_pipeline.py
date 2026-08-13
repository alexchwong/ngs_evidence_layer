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
    publication_key = metadata["publication_key"]
    envelope = {
        "schema_version": "1.2", "acceptance_path": "confirmed",
        "accepted_at": accepted_at, "accepted_at_source": "confirm",
        "accepted_in_version": "0.1.5",
        "metadata": metadata, "final": package,
    }
    (accept_dir / f"{publication_key}.final.json").write_text(json.dumps(envelope), encoding="utf-8")
    (accept_dir / f"{publication_key}.census.json").write_text(json.dumps(census), encoding="utf-8")


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
    ], check=True, capture_output=True, cwd=root)
    return output / "nel.corpus.json", output / "nel.index.json"


class VocabularyAndKeyTests(unittest.TestCase):
    def test_vocabulary_schema_and_umbrellas(self):
        self.assertEqual(vocab.check_vocabulary_consistency(), [])
        self.assertEqual(vocab.disease_ancestors(["APL"]), ["AML"])
        self.assertEqual(vocab.disease_ancestors(["MDS/AML"]), ["MDS", "AML"])
        self.assertEqual(
            vocab.disease_ancestors(["CMML"]),
            ["MDS", "MDS/MPN", "MPN"],
        )
        self.assertEqual(
            vocab.disease_ancestors(["MDS/MPN-U"]),
            ["MDS", "MDS/MPN", "MPN"],
        )
        self.assertEqual(vocab.disease_ancestors(["CML"]), ["MPN"])
        self.assertEqual(vocab.disease_ancestors(["JMML"]), ["MPN"])
        self.assertEqual(
            vocab.disease_ancestors(["BPDCN"]),
            ["histiocytic/dendritic neoplasm"],
        )
        self.assertEqual(vocab.disease_ancestors(["acute leukaemia of ambiguous lineage"]), [])
        self.assertEqual(vocab.disease_ancestors(["haematological malignancy, other"]), [])
        self.assertEqual(
            vocab.disease_ancestors(["CLL/SLL"]),
            ["lymphoid neoplasm", "B-cell lymphoid neoplasm", "mature B-cell neoplasm", "small lymphocytic proliferation"],
        )
        self.assertEqual(
            vocab.disease_ancestors(["B-ALL"]),
            ["lymphoid neoplasm", "acute lymphoblastic leukaemia/lymphoma", "B-cell lymphoid neoplasm", "precursor B-cell neoplasm"],
        )
        self.assertFalse(any(disease.startswith("B-ALL with ") for disease in vocab.DISEASES))
        self.assertEqual(
            vocab.disease_ancestors(["nodal TFH cell lymphoma, angioimmunoblastic-type"]),
            ["lymphoid neoplasm", "T-cell/NK-cell lymphoid neoplasm", "mature T-cell/NK-cell neoplasm", "nodal TFH cell lymphoma"],
        )

    def test_source_disease_aliases_resolve_reviewed_full_names(self):
        self.assertEqual(vocab.canonical_source_disease("clonal haematopoiesis"), "CHIP")
        self.assertEqual(vocab.canonical_source_disease("clonal hematopoiesis"), "CHIP")
        self.assertEqual(vocab.canonical_source_disease("primary myelofibrosis"), "PMF")
        self.assertEqual(vocab.canonical_source_disease("essential thrombocythaemia"), "ET")
        self.assertEqual(vocab.canonical_source_disease("polycythaemia vera"), "PV")
        self.assertEqual(vocab.canonical_source_disease("acute myeloid leukaemia"), "AML")
        self.assertEqual(vocab.canonical_source_disease("Clonal Haematopoiesis"), "CHIP")
        self.assertEqual(vocab.canonical_source_disease("  CHIP  "), "CHIP")
        self.assertEqual(vocab.canonical_source_disease("chronic lymphocytic leukaemia"), "CLL/SLL")
        self.assertEqual(vocab.canonical_source_disease("B-lymphoblastic leukaemia/lymphoma with BCR::ABL1 fusion"), "B-ALL")
        self.assertEqual(vocab.canonical_source_disease("B-lymphoblastic leukemia/lymphoma with KMT2A rearrangement"), "B-ALL")
        self.assertEqual(vocab.canonical_source_disease("Waldenström macroglobulinaemia"), "IgM LPL/WM")
        self.assertEqual(vocab.canonical_source_disease("multiple myeloma"), "plasma cell myeloma")
        self.assertEqual(vocab.canonical_source_disease("angioimmunoblastic T-cell lymphoma"), "nodal TFH cell lymphoma, angioimmunoblastic-type")
        self.assertEqual(vocab.canonical_source_disease("extranodal NK/T-cell lymphoma, nasal-type"), "extranodal NK/T-cell lymphoma")

    def test_source_disease_aliases_do_not_enable_nearest_term_mapping(self):
        self.assertIsNone(vocab.canonical_source_disease("age-related clonal haematopoiesis"))
        self.assertIsNone(vocab.canonical_source_disease("primary myelofibrotic neoplasm"))
        self.assertIsNone(vocab.canonical_source_disease("B-cell prolymphocytic leukaemia"))
        self.assertIsNone(vocab.canonical_source_disease("high-grade B-cell lymphoma with MYC and BCL2 and/or BCL6 rearrangements"))
        self.assertIsNone(vocab.canonical_source_disease(None))

    def test_source_disease_aliases_have_one_canonical_owner(self):
        disease_vocabulary = json.loads(
            (ROOT / "schema" / "disease_vocabulary.json").read_text(encoding="utf-8")
        )
        self.assertNotIn("source_disease_aliases", disease_vocabulary)
        self.assertGreater(len(vocab.SOURCE_DISEASE_ALIASES), 2)

    def test_umbrella_cycle_is_rejected(self):
        original = copy.deepcopy(vocab.UMBRELLA)
        try:
            vocab.UMBRELLA["MDS"] = ["MDS/AML"]
            with self.assertRaisesRegex(ValueError, "disease umbrella cycle"):
                vocab.disease_ancestors(["MDS/AML"])
        finally:
            vocab.UMBRELLA.clear()
            vocab.UMBRELLA.update(original)

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

    def test_incorrect_derived_ancestors_fail(self):
        def mutate(_metadata, _census, package):
            package["cards"][0]["diseases"] = ["APL"]
            package["cards"][0]["disease_ancestors"] = []
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})
        errors, _warnings, _report = self.validate(mutate)
        self.assertTrue(any("disease_ancestors" in error and "AML" in error for error in errors), errors)

    def test_package_separates_exact_disease_from_transitive_ancestors(self):
        def exact_cmml(_metadata, _census, package):
            package["cards"][0]["diseases"] = ["CMML"]
            package["cards"][0]["disease_ancestors"] = ["MDS", "MDS/MPN", "MPN"]
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})

        errors, _warnings, _report = self.validate(exact_cmml)
        self.assertEqual(errors, [])

    def test_transitive_ancestor_order_is_not_significant(self):
        def permuted_cmml(_metadata, _census, package):
            package["cards"][0]["diseases"] = ["CMML"]
            package["cards"][0]["disease_ancestors"] = ["MDS/MPN", "MDS", "MPN"]
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})

        errors, _warnings, _report = self.validate(permuted_cmml)
        self.assertEqual(errors, [])

    def test_missing_or_extra_transitive_ancestor_fails(self):
        def missing_cmml(_metadata, _census, package):
            package["cards"][0]["diseases"] = ["CMML"]
            package["cards"][0]["disease_ancestors"] = ["MDS", "MDS/MPN"]
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})

        errors, _warnings, _report = self.validate(missing_cmml)
        self.assertTrue(any("disease_ancestors" in error for error in errors), errors)

        def extra_cmml(_metadata, _census, package):
            package["cards"][0]["diseases"] = ["CMML"]
            package["cards"][0]["disease_ancestors"] = ["MDS", "MDS/MPN", "MPN", "AML"]
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})

        errors, _warnings, _report = self.validate(extra_cmml)
        self.assertTrue(any("disease_ancestors" in error for error in errors), errors)

    def test_pairing_and_verbatim_fragment_failures(self):
        def mutate(_metadata, _census, package):
            package["evidence"].pop()
            package["evidence"][0]["fragments"][0]["quote"] = "not in source"
        errors, _warnings, _report = self.validate(mutate)
        self.assertTrue(any("no evidence bundle" in error for error in errors), errors)
        self.assertTrue(any("not found verbatim" in error for error in errors), errors)

    def test_identical_evidence_is_warning_not_failure(self):
        def mutate(_metadata, _census, package):
            card = copy.deepcopy(package["cards"][0])
            card.update(card_id=package["cards"][0]["card_id"] + "-other", category="treatment")
            evidence = copy.deepcopy(package["evidence"][0]); evidence["card_id"] = card["card_id"]
            package["cards"].append(card); package["evidence"].append(evidence)
            package["genes_covered"] = sorted({g for c in package["cards"] for g in c["genes"]})
        errors, warnings, _report = self.validate(mutate)
        self.assertEqual(errors, [])
        self.assertTrue(any("identical" in warning for warning in warnings))

    def test_composite_and_table_evidence_validate(self):
        def mutate(_metadata, _census, package):
            package["evidence"][0] = {
                "card_id": package["cards"][0]["card_id"],
                "evidence_type": "composite_text",
                "fragments": [
                    {"fragment_id": "F01", "role": "scope_heading", "quote": "Entity definition", "locator": "Section 1 heading"},
                    {"fragment_id": "F02", "role": "claim", "quote": "GENEA mutation defines Fixture Entity One when the blast count is at least 20 per cent; a blast count of 10 to 19 per cent is assigned to Fixture Entity Two. The criterion is defeated where a fixture-defining fusion is present.", "locator": "Section 1"},
                ],
                "support_map": {"disease": ["F01"], "gene": ["F02"], "role": ["F02"], "qualifier": ["F02"]},
            }
            package["evidence"][2] = {
                "card_id": package["cards"][2]["card_id"],
                "evidence_type": "table_relation",
                "fragments": [
                    {"fragment_id": "F01", "role": "row_header", "quote": "GENEA", "locator": "Section 2, row GENEA"},
                    {"fragment_id": "F02", "role": "column_header", "quote": "Effect", "locator": "Section 2, column 2"},
                    {"fragment_id": "F03", "role": "cell", "quote": "favourable in the fixture cohort", "locator": "Section 2, row GENEA column 2"},
                    {"fragment_id": "F04", "role": "column_header", "quote": "Adjustment", "locator": "Section 2, column 3"},
                    {"fragment_id": "F05", "role": "cell", "quote": "multivariable-adjusted for age and blast count", "locator": "Section 2, row GENEA column 3"},
                ],
                "support_map": {"gene": ["F01"], "role": ["F02", "F03"], "effect": ["F03"], "qualifier": ["F04", "F05"]},
                "table_relations": [
                    {"value_fragment_id": "F03", "header_fragment_ids": ["F01", "F02"], "qualifier_fragment_ids": []},
                    {"value_fragment_id": "F05", "header_fragment_ids": ["F01", "F04"], "qualifier_fragment_ids": []},
                ],
            }
        errors, _warnings, _report = self.validate(mutate)
        self.assertEqual(errors, [])

    def test_dangling_support_and_invalid_table_link_fail(self):
        def dangling(_metadata, _census, package):
            package["evidence"][0]["support_map"]["gene"] = ["F99"]
        errors, _warnings, _report = self.validate(dangling)
        self.assertTrue(any("support_map references unknown" in error for error in errors), errors)

        def invalid_table(_metadata, _census, package):
            item = package["evidence"][2]
            item["evidence_type"] = "table_relation"
            item["fragments"].append({"fragment_id": "F02", "role": "cell", "quote": "GENEA", "locator": "Section 2"})
            item["table_relations"] = [{"value_fragment_id": "F02", "header_fragment_ids": ["F01"], "qualifier_fragment_ids": []}]
        errors, _warnings, _report = self.validate(invalid_table)
        self.assertTrue(any("table header F01 has invalid role claim" in error for error in errors), errors)

    def test_disease_dependent_card_requires_disease_but_germline_does_not(self):
        def remove_disease(_metadata, _census, package):
            package["cards"][0]["diseases"] = []
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})
        errors, _warnings, _report = self.validate(remove_disease)
        self.assertTrue(any("diseases" in error and "non-empty" in error for error in errors), errors)

        def gene_only_germline(_metadata, _census, package):
            package["cards"][0]["category"] = "germline"
            package["cards"][0]["diseases"] = []
            package["diseases_covered"] = sorted({d for card in package["cards"] for d in card["diseases"]})
        errors, _warnings, _report = self.validate(gene_only_germline)
        self.assertEqual(errors, [])

    def test_reference_list_fragment_is_rejected(self):
        def mutate(_metadata, _census, package):
            package["evidence"][0]["fragments"][0]["quote"] = (
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

    def test_zero_card_provisional_and_final_packages_validate(self):
        metadata, census, provisional = fixture_package(ALPHA, final=False)
        provisional.update(
            genes_covered=[], diseases_covered=[], cards=[], evidence=[]
        )
        errors, warnings, report = validation.validate_package(
            provisional, metadata, census, source_text=None, require_final=False
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(report["cards"], 0)
        self.assertEqual(report["census_claims"], len(census["entries"]))

        final = copy.deepcopy(provisional)
        final["paper_nickname"] = "Fixture Classifier 2020"
        final["publication_type_verified_by_phase3"] = True
        final["audit"] = {
            "audit_date": "2026-01-02",
            "audit_model": "fixture-audit-model",
            "extraction_model_reviewed": provisional["extraction_model"],
            "approved_round": provisional["round"],
            "publication_type_verdict": {
                "verdict": "pass", "verified_by_phase3": True,
            },
            "results": [],
        }
        errors, warnings, report = validation.validate_package(
            final, metadata, census, source_text=None, require_final=True
        )
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])
        self.assertEqual(report["cards"], 0)
        self.assertEqual(validation.validate_final_against_provisional(final, provisional), [])


class ReviewValidationTests(unittest.TestCase):
    def setUp(self):
        _metadata, _census, self.provisional = fixture_package(ALPHA, final=False)
        self.card_id = self.provisional["cards"][0]["card_id"]
        card_results = [
            {"card_id": card["card_id"], "verdict": "pass"}
            for card in self.provisional["cards"]
        ]
        card_results[0] = {
            "card_id": self.card_id,
            "verdict": "fail",
            "details": {
                "failure_type": "unsupported_assertion",
                "reason": "The interpretation exceeds the paired evidence.",
                "defensibility": (
                    "The card would be defensible only if narrowed to the "
                    "source-stated claim."
                ),
                "suggested_action": {
                    "category": "rewrite_interpretation",
                    "detail": "Narrow the interpretation to the source-stated claim.",
                },
            },
        }
        self.review = {
            "schema_version": "5.0",
            "paper_id": self.provisional["paper_id"],
            "round": self.provisional["round"],
            "review_date": "2026-01-02",
            "reviewer_model": "fixture-audit-model",
            "extraction_model_reviewed": self.provisional["extraction_model"],
            "result": "review_complete",
            "audit": {
                "publication_type_verdict": {
                    "package_value": self.provisional["publication_type"],
                    "auditor_value": self.provisional["publication_type"],
                    "verdict": "pass",
                    "verified_by_phase3": True,
                    "basis": "The package value is supported by the paper.",
                },
                "cards_total": len(self.provisional["cards"]),
                "cards_passed": len(self.provisional["cards"]) - 1,
                "cards_failed": 1,
            },
            "card_results": card_results,
        }

    def test_complete_review_validates(self):
        self.assertEqual(validation.validate_review(self.review, self.provisional), [])

    def test_pass_omits_details_and_failure_requires_complete_details(self):
        passing_result = self.review["card_results"][1]
        passing_result["details"] = copy.deepcopy(self.review["card_results"][0]["details"])
        self.assertTrue(validation.validate_review(self.review, self.provisional))

        passing_result.pop("details")
        self.review["card_results"][0]["details"].pop("defensibility")
        self.assertTrue(validation.validate_review(self.review, self.provisional))

    def test_quote_failure_requires_reviewed_quote_restatement(self):
        details = self.review["card_results"][0]["details"]
        details["failure_type"] = "quote_error"
        self.assertTrue(validation.validate_review(self.review, self.provisional))

        details["quote_restatement"] = "The quote as read in the provisional card."
        self.assertEqual(validation.validate_review(self.review, self.provisional), [])

        details["failure_type"] = "unsupported_assertion"
        self.assertTrue(validation.validate_review(self.review, self.provisional))

    def test_cross_artefact_identity_and_count_mismatches_fail(self):
        self.review["paper_id"] = "bbbbbbbb-0000-0000-0000-000000000002"
        self.review["round"] += 1
        self.review["reviewer_model"] = self.provisional["extraction_model"]
        self.review["extraction_model_reviewed"] = "wrong-model"
        self.review["audit"]["cards_total"] -= 1
        self.review["audit"]["cards_passed"] -= 1
        self.review["audit"]["cards_failed"] = 0
        errors = validation.validate_review(self.review, self.provisional)
        for phrase in (
            "paper_id", "round", "extraction_model_reviewed", "must differ",
            "cards_total", "cards_passed", "cards_failed",
        ):
            self.assertTrue(any(phrase in error for error in errors), (phrase, errors))

    def test_review_requires_complete_unique_ordered_card_coverage(self):
        mutations = {
            "omitted": lambda results: results.pop(),
            "duplicate": lambda results: results.__setitem__(1, copy.deepcopy(results[0])),
            "unknown": lambda results: results[0].update(card_id="unknown-card"),
            "reordered": lambda results: results.reverse(),
        }
        expected = {
            "omitted": "omits provisional cards",
            "duplicate": "duplicate card IDs",
            "unknown": "unknown provisional cards",
            "reordered": "preserve provisional card order",
        }
        for name, mutate in mutations.items():
            with self.subTest(name=name):
                review = copy.deepcopy(self.review)
                mutate(review["card_results"])
                review["audit"]["cards_passed"] = sum(
                    result["verdict"] == "pass" for result in review["card_results"]
                )
                review["audit"]["cards_failed"] = sum(
                    result["verdict"] == "fail" for result in review["card_results"]
                )
                errors = validation.validate_review(review, self.provisional)
                self.assertTrue(any(expected[name] in error for error in errors), errors)

    def test_publication_value_mismatches_fail(self):
        self.review["audit"]["publication_type_verdict"]["package_value"] = "primary study"
        self.review["audit"]["publication_type_verdict"]["auditor_value"] = "narrative review"
        errors = validation.validate_review(self.review, self.provisional)
        self.assertTrue(any("package_value" in error and "provisional" in error for error in errors), errors)
        self.assertTrue(any("must retain" in error for error in errors), errors)

    def test_publication_type_only_failure_is_valid(self):
        verdict = self.review["audit"]["publication_type_verdict"]
        verdict.update(auditor_value="primary study", verdict="fail", verified_by_phase3=False)
        self.review["card_results"] = [
            {"card_id": card["card_id"], "verdict": "pass"}
            for card in self.provisional["cards"]
        ]
        self.review["audit"]["cards_passed"] = len(self.provisional["cards"])
        self.review["audit"]["cards_failed"] = 0
        self.assertEqual(validation.validate_review(self.review, self.provisional), [])

    def test_all_pass_review_is_valid(self):
        self.review["card_results"] = [
            {"card_id": card["card_id"], "verdict": "pass"}
            for card in self.provisional["cards"]
        ]
        self.review["audit"]["cards_passed"] = len(self.provisional["cards"])
        self.review["audit"]["cards_failed"] = 0
        self.assertEqual(validation.validate_review(self.review, self.provisional), [])

    def test_review_validation_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            review_path = Path(tmp) / "paper.review-001.json"
            provisional_path = Path(tmp) / "paper.provisional-001.json"
            review_path.write_text(json.dumps(self.review), encoding="utf-8")
            provisional_path.write_text(json.dumps(self.provisional), encoding="utf-8")
            command = [
                sys.executable, str(SCRIPTS / "validate_review.py"),
                "--review", str(review_path), "--provisional", str(provisional_path),
            ]
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertIn("OK: review matches provisional package", result.stdout)

            self.review["card_results"][0]["details"].pop("suggested_action")
            review_path.write_text(json.dumps(self.review), encoding="utf-8")
            result = subprocess.run(command, capture_output=True, text=True)
            self.assertNotEqual(result.returncode, 0)


class IncorporationTests(unittest.TestCase):
    def test_builds_indexes_and_strips_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            corpus_path, index_path = build_fixture_corpus(Path(tmp))
            corpus, index = read(corpus_path), read(index_path)
            self.assertEqual(corpus["corpus_version"], "1.2")
            self.assertEqual(corpus["schema_version"], "3.1")
            self.assertEqual(index["index_version"], "1.4")
            self.assertEqual(corpus["counts"]["cards"], 10)
            self.assertNotIn("by_escalates_to", index)
            self.assertNotIn("escalates_to", json.dumps(index))
            self.assertNotIn('"evidence"', json.dumps(corpus))
            self.assertNotIn('"fragments"', json.dumps(corpus))
            self.assertNotIn('"quote"', json.dumps(corpus))
            self.assertNotIn("provisional", corpus)

    def test_indexes_transitive_ancestors_without_widening_exact_card_scope(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, accept = Path(tmp), Path(tmp) / "accept"
            accept.mkdir()

            def exact_cmml(_metadata, _census, package):
                card = package["cards"][0]
                card["diseases"] = ["CMML"]
                card["disease_ancestors"] = ["MDS", "MDS/MPN", "MPN"]
                package["diseases_covered"] = sorted(
                    {disease for item in package["cards"] for disease in item["diseases"]}
                )

            write_accept(accept, ALPHA, exact_cmml)
            output = root / "corpus"
            subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"),
                "--accept-dir", str(accept), "--output-dir", str(output),
                "--report", str(root / "report.json"),
            ], check=True, capture_output=True, cwd=root)

            corpus, index = read(output / "nel.corpus.json"), read(output / "nel.index.json")
            card_id = fixture_package(ALPHA)[2]["cards"][0]["card_id"]
            corpus_card = next(
                card
                for publication in corpus["publications"]
                for card in publication["document"]["cards"]
                if card["card_id"] == card_id
            )
            self.assertEqual(corpus_card["diseases"], ["CMML"])
            self.assertEqual(corpus_card["disease_ancestors"], ["MDS", "MDS/MPN", "MPN"])
            self.assertEqual(index["cards"][card_id]["diseases"], ["CMML"])
            for disease in ("CMML", "MDS", "MDS/MPN", "MPN"):
                self.assertIn(card_id, index["by_disease"][disease])

    def test_invalid_paper_is_rejected_without_blocking_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, accept = Path(tmp), Path(tmp) / "accept"; accept.mkdir()
            write_accept(accept, ALPHA)
            write_accept(accept, BETA, lambda _m, _c, p: p.update(audit=None))
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus"), "--report", str(root / "report.json"),
            ], capture_output=True, text=True, cwd=root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(read(root / "corpus" / "nel.corpus.json")["counts"]["completed_papers"], 1)
            beta_key = fixture_package(BETA)[0]["publication_key"]
            self.assertIn(beta_key, read(root / "report.json")["rejected"])

    def test_accepted_filename_must_match_publication_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, accept = Path(tmp), Path(tmp) / "accept"; accept.mkdir()
            write_accept(accept, ALPHA)
            key = fixture_package(ALPHA)[0]["publication_key"]
            (accept / f"{key}.final.json").rename(accept / "wrong-name.final.json")
            (accept / f"{key}.census.json").rename(accept / "wrong-name.census.json")
            result = subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus"), "--report", str(root / "report.json"),
            ], capture_output=True, text=True, cwd=root)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            report = read(root / "report.json")
            self.assertIn("wrong-name", report["rejected"])
            self.assertIn("publication_key", report["rejected"]["wrong-name"][0])
            self.assertEqual(read(root / "corpus" / "nel.corpus.json")["counts"]["completed_papers"], 0)

    def test_manual_missing_timestamp_is_persisted_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root, accept = Path(tmp), Path(tmp) / "accept"; accept.mkdir()
            write_accept(accept, ALPHA)
            key = fixture_package(ALPHA)[0]["publication_key"]
            path = accept / f"{key}.final.json"
            envelope = read(path)
            envelope.pop("accepted_at"); envelope.pop("accepted_at_source")
            envelope["schema_version"] = "1.0"
            envelope["acceptance_path"] = "manual-or-unverified"
            path.write_text(json.dumps(envelope), encoding="utf-8")
            subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus"), "--report", str(root / "report.json"),
            ], check=True, capture_output=True, cwd=root)
            persisted = read(path)
            self.assertEqual(persisted["accepted_at_source"], "file-mtime")
            first = persisted["accepted_at"]
            path.touch()
            subprocess.run([
                sys.executable, str(SCRIPTS / "incorporate.py"), "--accept-dir", str(accept),
                "--output-dir", str(root / "corpus2"), "--report", str(root / "report2.json"),
            ], check=True, capture_output=True, cwd=root)
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

    def test_paper_nickname_survives_incorporation_and_flattening(self):
        alpha_cards = [
            card for card in self.cards
            if card["publication_key"] == fixture_package(ALPHA)[0]["publication_key"]
        ]
        self.assertTrue(alpha_cards)
        self.assertEqual(
            {card["paper_nickname"] for card in alpha_cards},
            {"Fixture Classifier 2020"},
        )

    def bundle(self, genes, provisional, refined=None):
        refined = refined or provisional
        facts = [{"fact_id": "F1", "type": "test", "value": "supplied"}]
        step2 = retrieve.step2(self.cards, genes, provisional, facts)
        diagnosis_ids = [card["card_id"] for card in step2["diagnosis_cards"]]
        adjudication = {
            "status": "criteria_met",
            "provisional_disease": provisional,
            "refined_disease": refined,
            "downstream_filter_disease": refined,
            "diagnostic_label": None,
            "driven_by": diagnosis_ids[:1],
            "criterion_assessment": ([{
                "criterion": "fixture criterion",
                "required": True,
                "status": "met",
                "card_ids": diagnosis_ids[:1],
                "case_fact_ids": ["F1"],
            }] if diagnosis_ids else []),
            "reason": "Fixture adjudication.",
        }
        return {
            "step": 4, "genes": sorted(genes), "provisional_disease": provisional,
            "refined_disease": refined,
            "diagnostic_adjudication": adjudication,
            "provenance": {"corpus_version": "1.1", "corpus_sha256": "0" * 64, "retrieved_at": "2026-01-01T00:00:00+00:00"},
            **retrieve.step4(self.cards, genes, refined, step2["diagnosis_cards"]),
        }

    def test_stale_index_is_refused(self):
        with tempfile.TemporaryDirectory() as tmp:
            index = read(self.index_path); index["corpus_sha256"] = "0" * 64
            stale = Path(tmp) / "index.json"; stale.write_text(json.dumps(index), encoding="utf-8")
            with self.assertRaises(ValueError): retrieve.load_corpus(self.corpus_path, stale)

    def test_diagnosis_cards_are_not_gated_by_legacy_escalation_metadata(self):
        diagnosis = retrieve.step2(self.cards, ["GENEA"], "MDS")
        self.assertNotIn("escalation_candidates", diagnosis)
        self.assertIn("AML", diagnosis["allowed_refined_diseases"])
        full = retrieve.step4(self.cards, ["GENEA"], "MDS", diagnosis["diagnosis_cards"])
        self.assertEqual(full["suppressed"]["by_disease"], {"AML": 5, "MDS/AML": 1})

    def test_taxonomic_ancestors_do_not_broaden_clinical_retrieval(self):
        card = {
            "card_id": "classifier-C1000", "category": "prognosis", "genes": ["TET2"],
            "diseases": ["CMML"], "disease_ancestors": ["MDS", "MDS/MPN", "MPN"],
            "evidence_tier": "multivariable-adjusted", "interpretation": "CMML-specific evidence.",
            "locator": "fixture", "publication_key": "classifier", "publication_year": 2026,
            "citation_display": "Classifier fixture", "citation_incomplete": [],
            "secondary_citation": None,
        }
        for parent in ("MDS", "MDS/MPN", "MPN"):
            with self.subTest(parent=parent):
                result = retrieve.step4([card], ["TET2"], parent, [])
                self.assertEqual(result["retrieved"], [])
                self.assertEqual(result["suppressed"]["count"], 1)

        result = retrieve.step4([card], ["TET2"], "CMML", [])
        self.assertEqual([item["card_id"] for item in result["retrieved"]], ["classifier-C1000"])
        self.assertEqual(result["suppressed"]["count"], 0)

    def test_sf3b1_adjudication_changes_downstream_filter_to_mds(self):
        diagnosis_card = {
            "card_id": "classifier-C0001", "category": "diagnosis", "genes": ["SF3B1"],
            "diseases": ["MDS"], "evidence_tier": "guideline criterion",
            "interpretation": "The classifier permits MDS-SF3B1 when its stated molecular, ring-sideroblast, and exclusion criteria are met.",
            "locator": "fixture", "publication_key": "classifier", "publication_year": 2026,
            "citation_display": "Classifier fixture", "citation_incomplete": [],
            "secondary_citation": None,
        }
        mds_card = {
            **diagnosis_card, "card_id": "classifier-C0002", "category": "prognosis",
            "interpretation": "MDS downstream evidence.",
        }
        aml_card = {
            **diagnosis_card, "card_id": "classifier-C0003", "category": "treatment",
            "diseases": ["AML"], "interpretation": "AML downstream evidence.",
        }
        facts = [
            {"fact_id": "F-SF3B1", "type": "variant", "gene": "SF3B1", "vaf_percent": 30},
            {"fact_id": "F-RS", "type": "morphology", "ring_sideroblast_percent": 7},
        ]
        step2 = retrieve.step2(
            [diagnosis_card, mds_card, aml_card], ["SF3B1"],
            "myeloid neoplasm, unspecified", facts,
        )
        adjudication = {
            "status": "criteria_met",
            "provisional_disease": "myeloid neoplasm, unspecified",
            "refined_disease": "MDS",
            "downstream_filter_disease": "MDS",
            "diagnostic_label": "MDS-SF3B1",
            "driven_by": ["classifier-C0001"],
            "criterion_assessment": [
                {"criterion": "SF3B1 criterion", "required": True, "status": "met",
                 "card_ids": ["classifier-C0001"], "case_fact_ids": ["F-SF3B1"]},
                {"criterion": "ring sideroblast criterion", "required": True, "status": "met",
                 "card_ids": ["classifier-C0001"], "case_fact_ids": ["F-RS"]},
            ],
            "reason": "Both source-stated criteria are met by supplied facts.",
        }
        retrieve.validate_adjudication(step2, adjudication)
        full = retrieve.step4(
            [diagnosis_card, mds_card, aml_card], ["SF3B1"],
            adjudication["downstream_filter_disease"], step2["diagnosis_cards"],
        )
        retrieved_ids = {card["card_id"] for card in full["retrieved"]}
        self.assertIn("classifier-C0002", retrieved_ids)
        self.assertNotIn("classifier-C0003", retrieved_ids)

        bundle = {
            "step": 4, "genes": ["SF3B1"],
            "provisional_disease": step2["provisional_disease"], "refined_disease": "MDS",
            "diagnostic_adjudication": adjudication,
            "provenance": {"corpus_version": "test", "corpus_sha256": "0" * 64,
                           "retrieved_at": "2026-01-01T00:00:00+00:00"},
            **full,
        }
        rendered = render.render(bundle)["text"]
        self.assertIn("Downstream filter disease (adjudicated major category): MDS", rendered)
        self.assertIn("Source-supported diagnostic label: MDS-SF3B1", rendered)

    def test_adjudication_fails_closed_for_unknown_or_hallucinated_evidence(self):
        facts = [{"fact_id": "F-SF3B1", "type": "variant", "gene": "SF3B1"}]
        card = {
            "card_id": "classifier-C0001", "category": "diagnosis", "genes": ["SF3B1"],
            "diseases": ["MDS"], "evidence_tier": "guideline criterion",
            "interpretation": "Fixture criterion.", "locator": "fixture",
        }
        step2 = retrieve.step2([card], ["SF3B1"], "myeloid neoplasm, unspecified", facts)
        adjudication = {
            "status": "criteria_met", "provisional_disease": "myeloid neoplasm, unspecified",
            "refined_disease": "MDS", "downstream_filter_disease": "MDS",
            "diagnostic_label": "MDS-SF3B1", "driven_by": ["classifier-C0001"],
            "criterion_assessment": [{
                "criterion": "ring sideroblast criterion", "required": True, "status": "unknown",
                "card_ids": ["classifier-C0001"], "case_fact_ids": [],
            }],
            "reason": "Ring sideroblast percentage was not supplied.",
        }
        with self.assertRaisesRegex(ValueError, "every required criterion"):
            retrieve.validate_adjudication(step2, adjudication)

        adjudication["criterion_assessment"][0].update(
            status="met", case_fact_ids=["F-HALLUCINATED"]
        )
        with self.assertRaisesRegex(ValueError, "unsupplied case fact"):
            retrieve.validate_adjudication(step2, adjudication)

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
            for evidence in provisional["evidence"]:
                for fragment in evidence["fragments"]:
                    self.assertNotIn(fragment["quote"], first["text"])

    def test_render_truncates_weakest_first(self):
        result = render.render(self.bundle(["GENEA", "GENEC", "GENED"], "AML"), token_budget=200)
        self.assertEqual(result["dropped"][0]["evidence_tier"], "restated secondary")


if __name__ == "__main__":
    unittest.main()