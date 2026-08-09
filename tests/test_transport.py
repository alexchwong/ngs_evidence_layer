#!/usr/bin/env python3
"""Tests for compressed private-state transport."""
import io
import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "transport.py"
ROOT_NAMES = (
    "pdf", "input", "work", "quarantine", "accept", "archive", "curation"
)


class TransportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.source = self.base / "source"
        self.destination = self.base / "destination"
        self.bundle = self.base / "state.tar.gz"
        (self.source / "pdf" / "archive" / "fixture").mkdir(parents=True)
        (self.source / "pdf" / "archive" / "fixture" / "paper.pdf").write_bytes(b"%PDF fixture\n")
        (self.source / "input" / "fixture").mkdir(parents=True)
        (self.source / "input" / "fixture" / "papers.jsonl").write_text('{"status":"ingested"}\n', encoding="utf-8")
        (self.source / "work" / "paper-key").mkdir(parents=True)
        (self.source / "work" / "paper-key" / "paper.md").write_text("# Evidence\n", encoding="utf-8")
        (self.source / "quarantine" / "held-key").mkdir(parents=True)
        (self.source / "quarantine" / "held-key" / "quarantine.json").write_text(
            '{"status":"quarantined"}\n', encoding="utf-8"
        )
        (self.source / "accept").mkdir()
        (self.source / "accept" / "paper-key.final.json").write_text("{}\n", encoding="utf-8")
        (self.source / "archive" / "paper-key").mkdir(parents=True)
        (self.source / "archive" / "paper-key" / "metadata.json").write_text("{}\n", encoding="utf-8")
        (self.source / "curation").mkdir()
        (self.source / "curation" / "secondary-source-backlog.json").write_text(
            '{"sources":[]}\n', encoding="utf-8"
        )

    def tearDown(self):
        self.tmp.cleanup()

    def root_arguments(self, base):
        arguments = []
        for name in ROOT_NAMES:
            arguments.extend((f"--{name}-dir", str(base / name)))
        return arguments

    def run_transport(self, *arguments, success=True):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, arguments)],
            capture_output=True,
            text=True,
        )
        output = result.stdout + result.stderr
        if success:
            self.assertEqual(result.returncode, 0, output)
        else:
            self.assertNotEqual(result.returncode, 0, output)
        return output

    def export(self):
        return self.run_transport(
            "export", "--output", self.bundle, *self.root_arguments(self.source)
        )

    def test_round_trip_and_identical_files_are_idempotent(self):
        output = self.export()
        self.assertIn("Exported 7 files", output)
        self.assertTrue(self.bundle.is_file())

        output = self.run_transport(
            "import", self.bundle, *self.root_arguments(self.destination)
        )
        self.assertIn("Imported 7 files; 0 identical files skipped", output)
        for name in ROOT_NAMES:
            source_files = sorted(path.relative_to(self.source / name) for path in (self.source / name).rglob("*") if path.is_file())
            destination_files = sorted(path.relative_to(self.destination / name) for path in (self.destination / name).rglob("*") if path.is_file())
            self.assertEqual(destination_files, source_files)
            for relative in source_files:
                self.assertEqual(
                    (self.destination / name / relative).read_bytes(),
                    (self.source / name / relative).read_bytes(),
                )

        output = self.run_transport(
            "import", self.bundle, *self.root_arguments(self.destination)
        )
        self.assertIn("Imported 0 files; 7 identical files skipped", output)

    def test_dry_run_does_not_write(self):
        self.export()
        output = self.run_transport(
            "import", self.bundle, "--dry-run", *self.root_arguments(self.destination)
        )
        self.assertIn("Would import 7 files", output)
        self.assertFalse(self.destination.exists())

    def test_conflict_aborts_without_partial_import(self):
        self.export()
        conflict = self.destination / "work" / "paper-key" / "paper.md"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("different\n", encoding="utf-8")

        output = self.run_transport(
            "import", self.bundle, *self.root_arguments(self.destination), success=False
        )
        self.assertIn("import conflicts with existing state", output)
        self.assertEqual(conflict.read_text(encoding="utf-8"), "different\n")
        self.assertFalse((self.destination / "accept" / "paper-key.final.json").exists())

    def write_archive(self, path, manifest, members):
        with tarfile.open(path, "w:gz") as archive:
            manifest_bytes = json.dumps(manifest).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(manifest_bytes)
            archive.addfile(info, io.BytesIO(manifest_bytes))
            for name, content in members:
                info = tarfile.TarInfo(name)
                info.size = len(content)
                archive.addfile(info, io.BytesIO(content))

    def test_checksum_tampering_is_rejected(self):
        content = b"tampered"
        manifest = {
            "format": "ngs-evidence-layer-private-state",
            "version": 1,
            "created_at": "2026-08-04T00:00:00+00:00",
            "files": [{
                "path": "state/work/paper/file.json",
                "size": len(content),
                "sha256": "0" * 64,
            }],
        }
        self.write_archive(self.bundle, manifest, [("state/work/paper/file.json", content)])

        output = self.run_transport(
            "import", self.bundle, *self.root_arguments(self.destination), success=False
        )
        self.assertIn("checksum mismatch", output)
        self.assertFalse(self.destination.exists())

    def test_path_traversal_is_rejected(self):
        content = b"escape"
        manifest = {
            "format": "ngs-evidence-layer-private-state",
            "version": 1,
            "created_at": "2026-08-04T00:00:00+00:00",
            "files": [],
        }
        self.write_archive(self.bundle, manifest, [("state/work/../../escape", content)])

        output = self.run_transport(
            "import", self.bundle, *self.root_arguments(self.destination), success=False
        )
        self.assertIn("unsafe archive path", output)
        self.assertFalse((self.base / "escape").exists())


if __name__ == "__main__":
    unittest.main()