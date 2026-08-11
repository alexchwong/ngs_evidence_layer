#!/usr/bin/env python3
"""Tests for compressed private-state transport."""
import io
import json
import os
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
        with tarfile.open(self.bundle, "r:gz") as archive:
            manifest = json.load(archive.extractfile("manifest.json"))
        self.assertEqual(manifest["version"], 2)
        self.assertEqual(manifest["roots"], list(ROOT_NAMES))
        self.assertTrue(all("mtime_ns" in entry for entry in manifest["files"]))

        output = self.run_transport(
            "import", self.bundle, *self.root_arguments(self.destination)
        )
        self.assertIn("Imported 7 additions, 0 overwrites, 0 deletions", output)
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
        self.assertIn("Imported 0 additions, 0 overwrites, 0 deletions", output)
        self.assertIn("7 identical files skipped", output)

    def test_dry_run_does_not_write(self):
        self.export()
        output = self.run_transport(
            "import", self.bundle, "--dry-run", *self.root_arguments(self.destination)
        )
        self.assertIn("Would import 7 additions", output)
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

    def test_destination_only_file_requires_overwrite_and_is_deleted(self):
        self.export()
        extra = self.destination / "work" / "local-only.json"
        extra.parent.mkdir(parents=True)
        extra.write_text("old local file\n", encoding="utf-8")
        os.utime(extra, ns=(1, 1))

        output = self.run_transport(
            "import", self.bundle, *self.root_arguments(self.destination), success=False
        )
        self.assertIn("local files absent from manifest", output)
        self.assertTrue(extra.exists())

        output = self.run_transport(
            "import",
            self.bundle,
            "--overwrite",
            *self.root_arguments(self.destination),
        )
        self.assertIn("7 additions, 0 overwrites, 1 deletions", output)
        self.assertFalse(extra.exists())

    def test_overwrite_replaces_older_file_and_dry_run_does_not_mutate(self):
        self.export()
        conflict = self.destination / "work" / "paper-key" / "paper.md"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("older different\n", encoding="utf-8")
        os.utime(conflict, ns=(1, 1))

        output = self.run_transport(
            "import",
            self.bundle,
            "--overwrite",
            "--dry-run",
            *self.root_arguments(self.destination),
        )
        self.assertIn("Would import 6 additions, 1 overwrites", output)
        self.assertEqual(conflict.read_text(encoding="utf-8"), "older different\n")

        output = self.run_transport(
            "import",
            self.bundle,
            "--overwrite",
            *self.root_arguments(self.destination),
        )
        self.assertIn("Imported 6 additions, 1 overwrites", output)
        self.assertEqual(conflict.read_text(encoding="utf-8"), "# Evidence\n")

    def test_overwrite_refuses_newer_differing_file(self):
        self.export()
        conflict = self.destination / "work" / "paper-key" / "paper.md"
        conflict.parent.mkdir(parents=True)
        conflict.write_text("newer different\n", encoding="utf-8")
        future = 4_000_000_000_000_000_000
        os.utime(conflict, ns=(future, future))

        output = self.run_transport(
            "import",
            self.bundle,
            "--overwrite",
            *self.root_arguments(self.destination),
            success=False,
        )
        self.assertIn("local files are newer", output)
        self.assertIn("Remove these newer local files manually", output)
        self.assertEqual(conflict.read_text(encoding="utf-8"), "newer different\n")
        self.assertFalse((self.destination / "accept" / "paper-key.final.json").exists())

    def test_overwrite_refuses_newer_destination_only_file(self):
        self.export()
        extra = self.destination / "archive" / "local-only.json"
        extra.parent.mkdir(parents=True)
        extra.write_text("newer local file\n", encoding="utf-8")
        future = 4_000_000_000_000_000_000
        os.utime(extra, ns=(future, future))

        output = self.run_transport(
            "import",
            self.bundle,
            "--overwrite",
            *self.root_arguments(self.destination),
            success=False,
        )
        self.assertIn("local files are newer", output)
        self.assertIn(str(extra), output)
        self.assertTrue(extra.exists())

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
            "version": 2,
            "created_at": "2026-08-04T00:00:00+00:00",
            "roots": list(ROOT_NAMES),
            "files": [{
                "path": "state/work/paper/file.json",
                "size": len(content),
                "sha256": "0" * 64,
                "mtime_ns": 1,
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
            "version": 2,
            "created_at": "2026-08-04T00:00:00+00:00",
            "roots": list(ROOT_NAMES),
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