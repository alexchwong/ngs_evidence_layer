#!/usr/bin/env python3
"""Tests for corpus acceptance-version provenance."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS))

import backfill_acceptance_version as backfill  # noqa: E402
import confirm  # noqa: E402
import incorporate  # noqa: E402


def metadata_fixture(publication_key="fixture-2020-fixture-journal-1-1"):
    return {
        "schema_version": "1.1",
        "paper_id": "aaaaaaaa-0000-0000-0000-000000000001",
        "corpus": "fixtures",
        "stem": "fixture-alpha--aaaaaaaa",
        "publication_key": publication_key,
        "citation": {
            "authors": ["Fixture A"],
            "title": "Fixture paper",
            "journal": "Fixture Journal",
            "year": 2020,
            "volume": "1",
            "issue": "1",
            "pages": "1-10",
            "doi": "",
            "display": "Fixture A. Fixture paper. Fixture Journal. 2020;1(1):1-10.",
            "citation_incomplete": [],
        },
        "citation_source": "operator",
        "citation_resolved_at": "2026-08-02T00:00:00+00:00",
        "source_filename": "fixture.pdf",
        "source_sha256": "a" * 64,
        "markdown_sha256": "b" * 64,
        "created_at": "2026-08-02T00:00:00+00:00",
    }


def accepted_fixture(key, version=None, schema_version="1.1"):
    package = {
        "schema_version": schema_version,
        "acceptance_path": "confirmed",
        "accepted_at": "2026-08-02T00:00:00+00:00",
        "accepted_at_source": "confirm",
        "metadata": metadata_fixture(key),
        "final": {},
    }
    if version is not None:
        package["accepted_in_version"] = version
    return package


class CorpusVersioningTests(unittest.TestCase):
    def test_metadata_schema_does_not_contain_acceptance_version(self):
        schema = json.loads((ROOT / "schema" / "metadata_schema.json").read_text())
        self.assertNotIn("accepted_in_version", schema["properties"])
        self.assertEqual(schema["title"], "Publication metadata")
        self.assertIn("version_history", schema["properties"])
        self.assertIn("latest_version", schema["properties"])

    def test_accepted_schema_requires_top_level_acceptance_version(self):
        schema = json.loads(
            (ROOT / "schema" / "accepted_package_schema.json").read_text()
        )
        self.assertEqual(
            schema["properties"]["schema_version"]["enum"], ["1.2", "1.3", "1.4"]
        )
        self.assertEqual(
            schema["allOf"][0]["then"]["properties"]["schema_version"]["enum"],
            ["1.3", "1.4"],
        )
        self.assertEqual(
            schema["allOf"][1]["then"]["properties"]["schema_version"]["const"],
            "1.4",
        )
        self.assertIn("accepted_in_version", schema["required"])
        self.assertIn("accepted_in_version", schema["properties"])

    def test_confirm_stamps_accept_only_and_leaves_archived_metadata_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = "fixture-2020-fixture-journal-1-1"
            working = root / "work" / key
            working.mkdir(parents=True)
            metadata = metadata_fixture(key)
            (working / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            (working / "paper.census.json").write_text("{}", encoding="utf-8")
            (working / "paper.md").write_text("source", encoding="utf-8")
            (working / "paper.final.json").write_text(
                json.dumps({"audit": {"approved_round": 1}}), encoding="utf-8"
            )
            (working / "paper.provisional-001.json").write_text("{}", encoding="utf-8")
            (working / "paper.review-001.json").write_text("{}", encoding="utf-8")
            version_file = root / "VERSION"
            version_file.write_text("9.9.9\n", encoding="utf-8")
            args = SimpleNamespace(
                publication_key=key,
                work_dir=root / "work",
                accept_dir=root / "accept",
                archive_dir=root / "archive",
            )
            with (
                mock.patch.object(confirm, "VERSION_FILE", version_file),
                mock.patch.object(
                    confirm.validation, "validate_package", return_value=([], [], {})
                ),
                mock.patch.object(
                    confirm.final_validation,
                    "validate_phase_files",
                    return_value=([], [], {"cards": 0, "ratio": None}),
                ),
            ):
                confirm.confirm(args)

            archived_metadata = json.loads(
                (root / "archive" / key / "metadata.json").read_text()
            )
            accepted = json.loads(
                (root / "accept" / f"{key}.final.json").read_text()
            )
            self.assertNotIn("accepted_in_version", archived_metadata)
            self.assertNotIn("accepted_in_version", accepted["metadata"])
            self.assertEqual(accepted["accepted_in_version"], "9.9.9")
            self.assertEqual(accepted["schema_version"], "1.2")

    def test_confirm_overwrite_preserves_prior_archive_and_stamps_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = "fixture-2020-fixture-journal-1-1"
            working = root / "work" / key
            archive = root / "archive" / key
            accept = root / "accept"
            working.mkdir(parents=True)
            archive.mkdir(parents=True)
            accept.mkdir()
            metadata = metadata_fixture(key)
            (working / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            (working / "paper.census.json").write_text('{"generation": 2}', encoding="utf-8")
            (working / "paper.md").write_text("new source", encoding="utf-8")
            (working / "paper.final.json").write_text(
                json.dumps({"audit": {"approved_round": 1}, "generation": 2}),
                encoding="utf-8",
            )
            (working / "paper.provisional-001.json").write_text("{}", encoding="utf-8")
            (working / "paper.review-001.json").write_text("{}", encoding="utf-8")
            (archive / "metadata.json").write_text(json.dumps(metadata), encoding="utf-8")
            (archive / "paper.md").write_text("old source", encoding="utf-8")
            prior = accepted_fixture(key, version="1.0.0", schema_version="1.2")
            prior["final"] = {"generation": 1}
            (accept / f"{key}.final.json").write_text(json.dumps(prior), encoding="utf-8")
            (accept / f"{key}.census.json").write_text(
                '{"generation": 1}', encoding="utf-8"
            )
            version_file = root / "VERSION"
            version_file.write_text("2.0.0\n", encoding="utf-8")
            args = SimpleNamespace(
                publication_key=key,
                work_dir=root / "work",
                accept_dir=accept,
                archive_dir=root / "archive",
                overwrite=True,
            )
            with (
                mock.patch.object(confirm, "VERSION_FILE", version_file),
                mock.patch.object(
                    confirm.validation, "validate_package", return_value=([], [], {})
                ),
                mock.patch.object(
                    confirm.final_validation,
                    "validate_phase_files",
                    return_value=([], [], {"cards": 0, "ratio": None}),
                ),
            ):
                confirm.confirm(args)

            accepted = json.loads((accept / f"{key}.final.json").read_text())
            archived_metadata = json.loads((archive / "metadata.json").read_text())
            self.assertEqual(accepted["version_history"], ["1.0.0", "2.0.0"])
            self.assertEqual(accepted["latest_version"], "2.0.0")
            self.assertEqual(accepted["metadata"]["latest_version"], "2.0.0")
            self.assertEqual(accepted["final"]["generation"], 2)
            self.assertEqual(archived_metadata["version_history"], ["1.0.0", "2.0.0"])
            self.assertEqual(archived_metadata["latest_version"], "2.0.0")
            self.assertEqual((archive / "paper.md").read_text(), "new source")
            self.assertEqual(
                (archive / "versions" / "1.0.0" / "paper.md").read_text(),
                "old source",
            )
            self.assertEqual(
                json.loads((accept / f"{key}.census.json").read_text())["generation"],
                2,
            )
            self.assertFalse(working.exists())

    def test_confirm_collision_still_fails_without_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            key = "fixture-2020-fixture-journal-1-1"
            working = root / "work" / key
            working.mkdir(parents=True)
            (working / "metadata.json").write_text(
                json.dumps(metadata_fixture(key)), encoding="utf-8"
            )
            (working / "paper.census.json").write_text("{}", encoding="utf-8")
            (working / "paper.md").write_text("source", encoding="utf-8")
            (working / "paper.final.json").write_text(
                json.dumps({"audit": {"approved_round": 1}}), encoding="utf-8"
            )
            (working / "paper.provisional-001.json").write_text("{}", encoding="utf-8")
            (working / "paper.review-001.json").write_text("{}", encoding="utf-8")
            archive = root / "archive" / key
            archive.mkdir(parents=True)
            args = SimpleNamespace(
                publication_key=key,
                work_dir=root / "work",
                accept_dir=root / "accept",
                archive_dir=root / "archive",
                overwrite=False,
            )
            with (
                mock.patch.object(
                    confirm.validation, "validate_package", return_value=([], [], {})
                ),
                mock.patch.object(
                    confirm.final_validation,
                    "validate_phase_files",
                    return_value=([], [], {"cards": 0, "ratio": None}),
                ),
            ):
                with self.assertRaisesRegex(ValueError, "destination already exists"):
                    confirm.confirm(args)
            self.assertTrue(working.is_dir())

    def test_backfill_stamps_legacy_accept_as_0_1_5(self):
        with tempfile.TemporaryDirectory() as tmp:
            accept_dir = Path(tmp) / "accept"
            accept_dir.mkdir()
            key = "fixture-2020-fixture-journal-1-1"
            path = accept_dir / f"{key}.final.json"
            path.write_text(json.dumps(accepted_fixture(key)), encoding="utf-8")
            with (
                mock.patch.object(backfill.validation, "validate_metadata", return_value=[]),
                mock.patch.object(backfill.validation, "schema_errors", return_value=[], create=True),
            ):
                first = backfill.backfill(accept_dir)
                second = backfill.backfill(accept_dir)
            self.assertEqual(first["stamped"], 1)
            self.assertEqual(second["stamped"], 0)
            updated = json.loads(path.read_text())
            self.assertEqual(updated["accepted_in_version"], "0.1.5")
            self.assertEqual(updated["schema_version"], "1.2")
            self.assertNotIn("accepted_in_version", updated["metadata"])

    def test_backfill_preserves_existing_version_and_migrates_prior_nested_design(self):
        key = "fixture-2020-fixture-journal-1-1"
        package = accepted_fixture(key)
        package["metadata"]["accepted_in_version"] = "0.1.6"
        with (
            mock.patch.object(backfill.validation, "validate_metadata", return_value=[]),
            mock.patch.object(backfill.validation, "schema_errors", return_value=[], create=True),
        ):
            updated, changed, version = backfill.migrated_package(package, key)
        self.assertTrue(changed)
        self.assertEqual(version, "0.1.6")
        self.assertEqual(updated["accepted_in_version"], "0.1.6")
        self.assertNotIn("accepted_in_version", updated["metadata"])

    def test_incorporate_adds_acceptance_version_to_index(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            accept_dir = root / "accept"
            accept_dir.mkdir()
            key = "fixture-2020-fixture-journal-1-1"
            final_path = accept_dir / f"{key}.final.json"
            census_path = accept_dir / f"{key}.census.json"
            final_path.write_text("{}", encoding="utf-8")
            census_path.write_text("{}", encoding="utf-8")
            metadata = metadata_fixture(key)
            package = {
                "publication_type": "guideline",
                "extraction_date": "2026-08-02",
                "extraction_model": "fixture-model",
                "genes_covered": [],
                "diseases_covered": [],
                "census_entries": 0,
                "cards": [],
                "audit": {},
            }
            envelope = {
                "schema_version": "1.2",
                "acceptance_path": "confirmed",
                "accepted_at": "2026-08-02T00:00:00+00:00",
                "accepted_at_source": "confirm",
                "accepted_in_version": "0.1.6",
                "metadata": metadata,
                "final": package,
            }
            args = SimpleNamespace(
                accept_dir=accept_dir,
                generated_at="2026-08-08T00:00:00+00:00",
            )
            with (
                mock.patch.object(incorporate, "normalize_accepted_at"),
                mock.patch.object(
                    incorporate,
                    "load_pair",
                    return_value=(envelope, {"entries": []}, [], {"ratio": None}),
                ),
            ):
                _corpus, index, _report = incorporate.build(args)
            self.assertEqual(index["index_version"], "1.3")
            self.assertEqual(
                index["papers"][key]["accepted_in_version"], "0.1.6"
            )
            self.assertEqual(index["by_accepted_in_version"], {"0.1.6": [key]})


if __name__ == "__main__":
    unittest.main()
