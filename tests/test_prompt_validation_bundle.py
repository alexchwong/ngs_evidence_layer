#!/usr/bin/env python3
"""Tests for phase-specific self-contained prompt validation bundles."""
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
    ROOT / "tests" / "fixtures" / "work" / "aaaaaaaa-0000-0000-0000-000000000001"
)
PHASE_ASSETS = {
    1: "PHASE1_VALIDATION_BUNDLE",
    2: "PHASE2_VALIDATION_BUNDLE",
    4: "PHASE4_VALIDATION_BUNDLE",
    5: "PHASE5_VALIDATION_BUNDLE",
}


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
    def test_each_asset_contains_only_its_canonical_phase_validator(self):
        manifest = build_prompts.load_manifest()["assets"]
        for phase, keyword in PHASE_ASSETS.items():
            with self.subTest(phase=phase):
                spec = manifest[keyword]
                relative = f"scripts/phase_validation/phase{phase}.py"
                path = ROOT / relative
                content = build_prompts.asset_content(keyword)
                if spec.get("type") == "bundle":
                    self.assertEqual(spec.get("paths"), [relative])
                    self.assertFalse(spec.get("globs"))
                    self.assertIn(f"<!-- BEGIN VERBATIM {relative} -->", content)
                    self.assertEqual(len(list(FILE_RE.finditer(content))), 1)
                else:
                    self.assertEqual(spec, {"type": "file", "path": relative})
                    self.assertEqual(content, path.read_text(encoding="utf-8").rstrip())
                self.assertIn(path.read_text(encoding="utf-8").rstrip(), content)

    def test_phase_templates_use_phase_specific_bundle_markers(self):
        for phase, keyword in PHASE_ASSETS.items():
            template = (
                ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
            ).read_text(encoding="utf-8")
            self.assertEqual(template.count("{{" + keyword + "}}"), 1)
        phase3 = (ROOT / "prompts" / "templates" / "phase3_prompt.md").read_text(
            encoding="utf-8"
        )
        phase5_review = (
            ROOT / "prompts" / "templates" / "phase5_review_prompt.md"
        ).read_text(encoding="utf-8")
        for keyword in PHASE_ASSETS.values():
            self.assertNotIn("{{" + keyword + "}}", phase3)
            self.assertNotIn("{{" + keyword + "}}", phase5_review)

    def test_extracted_phase2_bundle_executes_outside_repository(self):
        prompt = build_prompts.render(2)
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            work = temp / "work"
            shutil.copytree(FIXTURE, work)
            matches = [
                match for match in FILE_RE.finditer(prompt)
                if match.group("path") == "scripts/phase_validation/phase2.py"
            ]
            self.assertEqual(len(matches), 1)
            script = work / "validation_bundle" / matches[0].group("path")
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(matches[0].group("content"), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--metadata", "metadata.json",
                    "--census", "paper.census.json",
                    "--source", "paper.md",
                    "--provisional", "paper.provisional-001.json",
                ],
                cwd=work,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

    def test_extracted_phase4_bundle_validates_review_outside_repository(self):
        prompt = build_prompts.render(4)
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            work = temp / "work"
            shutil.copytree(FIXTURE, work)
            match = next(
                match for match in FILE_RE.finditer(prompt)
                if match.group("path") == "scripts/phase_validation/phase4.py"
            )
            script = work / "validation_bundle" / match.group("path")
            script.parent.mkdir(parents=True, exist_ok=True)
            script.write_text(match.group("content"), encoding="utf-8")
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--review-only",
                    "--provisional", "paper.provisional-001.json",
                    "--review", "paper.review-001.json",
                ],
                cwd=work,
                text=True,
                capture_output=True,
            )
            self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
