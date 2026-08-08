#!/usr/bin/env python3
"""Tests for filename-derived corpus publication keys."""
import hashlib
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import citations
import fanout
import make_key
import parse_pdfs


class FilenamePublicationKeyTests(unittest.TestCase):
    def test_source_filename_defines_publication_key(self):
        self.assertEqual(
            make_key.build_source_key("2020_Kraft_Germline Variants.pdf"),
            "2020-kraft-germline-variants",
        )

    def test_primary_citation_can_use_source_filename_key(self):
        citation = {
            "authors": ["Kraft IL"], "title": "Completely Different Bibliographic Title",
            "journal": "Blood", "year": 2020, "volume": "136", "pages": "2498-2506",
        }
        built = make_key.build_citation(
            citation, source_filename="2020_kraft_germline_variants.pdf"
        )
        self.assertEqual(built["publication_key"], "2020-kraft-germline-variants")

    def test_citation_repair_does_not_rename_source(self):
        record = {
            "source_filename": "2026_george_ddx41_germline_somatic_classification.pdf"
        }
        self.assertEqual(
            citations.source_publication_key(record),
            "2026-george-ddx41-germline-somatic-classification",
        )

    def test_parse_rejects_normalized_filename_collision(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "Paper One.pdf"
            source.write_bytes(b"new paper")
            records = [{
                "source_filename": "Paper-One.pdf",
                "sha256": hashlib.sha256(b"different paper").hexdigest(),
            }]
            with self.assertRaisesRegex(ValueError, "rename one source PDF"):
                parse_pdfs.source_key_collision(
                    source, hashlib.sha256(source.read_bytes()).hexdigest(), records
                )

    def test_parse_dry_run_reports_filename_key(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "2020_kraft_germline_variants.pdf"
            source.write_bytes(b"fixture")
            args = Namespace(
                force=False, allow_reparse=False, dry_run=True,
                work_dir=Path(temporary) / "work",
                accept_dir=Path(temporary) / "accept",
                archive_dir=Path(temporary) / "archive",
            )
            _records, outcome = parse_pdfs.parse_one(source, args, [])
            self.assertIn("(2020-kraft-germline-variants)", outcome)

    def test_fanout_recomputes_key_from_original_filename(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "paper--aaaaaaaa.md"
            source.write_text("fixture", encoding="utf-8")
            record = {
                "id": "aaaaaaaa-0000-0000-0000-000000000001",
                "source_filename": "2020_kraft_germline_variants.pdf",
                "sha256": "a" * 64,
                "citation_source": "operator",
                "citation_resolved_at": "2026-08-08T00:00:00+00:00",
                "citation": {
                    "authors": ["Kraft IL"], "title": "A title", "journal": "Blood",
                    "year": 2020, "volume": "136", "issue": "22", "pages": "2498-2506",
                    "doi": "10.1182/blood.2020006910",
                },
            }
            metadata = fanout.metadata_for(
                record, "fixture", source, "2026-08-08T00:00:00+00:00"
            )
            self.assertEqual(
                metadata["publication_key"], "2020-kraft-germline-variants"
            )


if __name__ == "__main__":
    unittest.main()
