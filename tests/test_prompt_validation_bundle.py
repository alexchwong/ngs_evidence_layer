#!/usr/bin/env python3
"""Tests for the prompt-embedded validation dependency bundle."""
import importlib.util
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
FIXTURE = (
    ROOT
    / "tests"
    / "fixtures"
    / "work"
    / "aaaaaaaa-0000-0000-0000-000000000001"
)


def load_build_prompts():
    spec = importlib.util.spec_from_file_location(
        "nel_build_prompts", SCRIPTS / "build_prompts.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


build_prompts = load_build_prompts()
FILE_RE = re.compile(
    r"<!-- BEGIN VERBATIM (?P<path>[^ ]+) -->\n"
    r"```(?:python|json)\n(?P<content>.*?)\n```\n"
    r"<!-- END VERBATIM (?P=path) -->",
    re.DOTALL,
)


class PromptValidationBundleTests(unittest.TestCase):
    def test_bundle_contains_canonical_validator_and_dependencies(self):
        bundle = build_prompts.validation_bundle()
        expected = [
            ROOT / "scripts" / "final_validation.py",
            ROOT / "scripts" / "package_validation.py",
            ROOT / "scripts" / "vocab.py",
            *sorted((ROOT / "schema").glob("*.json")),
        ]
        for path in expected:
            relative = path.relative_to(ROOT).as_posix()
            self.assertIn(f"<!-- BEGIN VERBATIM {relative} -->", bundle)
            self.assertIn(path.read_text(encoding="utf-8").rstrip(), bundle)

    def test_phase_prompts_use_bundle_marker(self):
        for phase in (1, 2, 3, 4):
            template = (
                ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
            ).read_text(encoding="utf-8")
            self.assertIn("{{PHASE_VALIDATION_BUNDLE}}", template)
            self.assertNotIn("{{PHASE_VALIDATION_SCRIPT}}", template)

    def test_extracted_phase2_bundle_executes_outside_repository(self):
        prompt = build_prompts.render(2)
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            work = temp / "work"
            shutil.copytree(FIXTURE, work)
            bundle_root = work / "validation_bundle"
            matches = list(FILE_RE.finditer(prompt))
            self.assertGreater(len(matches), 3)
            for match in matches:
                destination = bundle_root / match.group("path")
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(match.group("content"), encoding="utf-8")

            result = subprocess.run(
                [
                    sys.executable,
                    str(bundle_root / "scripts" / "final_validation.py"),
                    "--phase",
                    "2",
                    "--metadata",
                    "metadata.json",
                    "--census",
                    "paper.census.json",
                    "--source",
                    "paper.md",
                    "--provisional",
                    "paper.provisional-001.json",
                ],
                cwd=work,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
