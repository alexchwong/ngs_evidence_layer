#!/usr/bin/env python3
"""Tests for deterministic PDF identity, index storage, and citation repair."""
import csv
import importlib.util
import io
import json
import sys
import tempfile
import unittest
import uuid
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))


def load(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


index_store = load("index_store")
parse = load("parse_pdfs")
citations = load("citations")


def record(paper_id="aaaaaaaa-0000-0000-0000-000000000001", status="citation-pending"):
    return {
        "id": paper_id, "markdown_path": f"markdown/paper--{paper_id[:8]}.md",
        "source_filename": "paper.pdf", "sha256": "a" * 64, "status": status,
        "citation": {}, "citation_source": None, "citation_resolved_at": None,
        "publication_key": None,
        "parse": {
            "parser": "opendataloader-pdf", "parser_version": "2.0", "parsed_at": "2026-01-01T00:00:00+00:00",
            "markdown_sha256": "b" * 64, "archived_pdf": "", "doi_detected": "",
            "table_warnings": [], "error": "no DOI detected",
        },
    }


class IdentityAndCrossrefTests(unittest.TestCase):
    def test_uuid_and_stem_are_stable(self):
        first = parse.paper_uuid("a" * 64)
        self.assertEqual(first, parse.paper_uuid("a" * 64))
        self.assertEqual(str(uuid.UUID(first)), first)
        self.assertTrue(f"{parse.safe_stem('A paper')}--{first[:8]}".endswith(f"--{first[:8]}"))

    def test_crossref_mapping_uses_injected_fetch(self):
        payload = {"message": {
            "author": [{"family": "Khoury", "given": "John D"}],
            "title": ["A title"], "container-title": ["Journal"],
            "issued": {"date-parts": [[2022]]}, "volume": "1", "issue": "2", "page": "3-4",
        }}
        citation = parse.crossref_citation("10.1/test", "a@example.org", lambda _url, _headers: payload)
        self.assertEqual(citation["authors"], ["Khoury JD"])
        self.assertEqual(citation["year"], 2022)

    def test_incomplete_crossref_record_is_pending_error(self):
        with self.assertRaisesRegex(ValueError, "lacks required"):
            parse.crossref_citation("10.1/test", "a@example.org", lambda _url, _headers: {"message": {}})

    def test_table_integrity_warning(self):
        markdown = "| A | B |\n|---|---|\n| one | two | three |\n"
        self.assertTrue(parse.table_warnings(markdown))


class IndexAndManualCitationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.input = Path(self.tmp.name) / "input"
        self.corpus = "fixture"

    def tearDown(self):
        self.tmp.cleanup()

    def test_jsonl_csv_round_trip_and_csv_overwrite(self):
        rows = [record()]
        index_store.write(self.corpus, rows, self.input)
        jsonl, csv_path = index_store.index_paths(self.corpus, self.input)
        self.assertTrue(jsonl.is_file())
        csv_path.write_text("operator edit", encoding="utf-8")
        index_store.write(self.corpus, index_store.load(self.corpus, self.input), self.input)
        self.assertIn("id,status,source_filename", csv_path.read_text(encoding="utf-8"))

    def test_manual_export_and_no_doi_apply(self):
        rows = [record()]
        markdown = self.input / self.corpus / rows[0]["markdown_path"]
        markdown.parent.mkdir(parents=True)
        markdown.write_text("# Fixture title\nBody", encoding="utf-8")
        index_store.write(self.corpus, rows, self.input)
        output = Path(self.tmp.name) / "manual.csv"
        args = Namespace(corpus=self.corpus, input_dir=self.input, output=output)
        citations.manual_export(args, rows)
        with output.open(newline="", encoding="utf-8") as handle:
            exported = list(csv.DictReader(handle))
        self.assertEqual(exported[0]["paper_id"], rows[0]["id"])
        self.assertEqual(exported[0]["title"], "")
        exported[0].update(authors="Fixture A; Fixture B", title="Fixture title", year="2020")
        stream = io.StringIO(newline="")
        writer = csv.DictWriter(stream, fieldnames=citations.MANUAL_FIELDS, lineterminator="\n")
        writer.writeheader(); writer.writerows(exported)
        output.write_text(stream.getvalue(), encoding="utf-8")
        citations.manual_apply(Namespace(corpus=self.corpus, input_dir=self.input, csv=output), rows)
        applied = index_store.load(self.corpus, self.input)[0]
        self.assertEqual(applied["status"], "ingested")
        self.assertEqual(applied["citation_source"], "operator")
        self.assertEqual(applied["citation"]["authors"], ["Fixture A", "Fixture B"])

    def test_manual_apply_is_batch_atomic(self):
        rows = [record()]
        index_store.write(self.corpus, rows, self.input)
        path = Path(self.tmp.name) / "bad.csv"
        path.write_text(
            ",".join(citations.MANUAL_FIELDS) + "\n" +
            f"unknown,Fixture A,Title,,2020,,,,\n", encoding="utf-8"
        )
        with self.assertRaises(ValueError):
            citations.manual_apply(Namespace(corpus=self.corpus, input_dir=self.input, csv=path), rows)
        self.assertEqual(index_store.load(self.corpus, self.input)[0]["status"], "citation-pending")

    def test_title_similarity(self):
        self.assertGreaterEqual(citations.similarity("The fixture title", "Fixture title"), 0.6)
        self.assertLess(citations.similarity("Unrelated paper", "Fixture title"), 0.6)


if __name__ == "__main__":
    unittest.main()