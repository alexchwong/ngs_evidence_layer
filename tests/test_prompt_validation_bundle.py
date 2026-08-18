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
}
PHASE_BUNDLE_PATHS = {
    1: ["scripts/phase_validation/phase1.py"],
    2: [
        "scripts/phase_validation/phase1.py",
        "scripts/phase_validation/phase2.py",
        "scripts/phase_validation/card_deltas.py",
        "schema/ingestion_package_schema.json",
        "schema/disease_vocabulary.json",
        "schema/card_decision_schema.json",
    ],
    4: [
        "scripts/phase_validation/phase4.py",
        "scripts/phase_validation/card_deltas.py",
        "schema/ingestion_package_schema.json",
        "schema/review_schema.json",
        "schema/disease_vocabulary.json",
        "schema/card_decision_schema.json",
    ],
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
    def test_phase_validation_bundles_include_canonical_dependencies(self):
        manifest = build_prompts.load_manifest()["assets"]
        for phase, keyword in PHASE_ASSETS.items():
            with self.subTest(phase=phase):
                spec = manifest[keyword]
                validator = f"scripts/phase_validation/phase{phase}.py"
                content = build_prompts.asset_content(keyword)
                if spec.get("type") == "bundle":
                    self.assertEqual(spec.get("paths"), PHASE_BUNDLE_PATHS[phase])
                    self.assertFalse(spec.get("globs"))
                    matches = list(FILE_RE.finditer(content))
                    self.assertEqual(
                        [match.group("path") for match in matches],
                        PHASE_BUNDLE_PATHS[phase],
                    )
                    for relative in PHASE_BUNDLE_PATHS[phase]:
                        self.assertIn(f"<!-- BEGIN VERBATIM {relative} -->", content)
                        self.assertIn(
                            (ROOT / relative).read_text(encoding="utf-8").rstrip(),
                            content,
                        )
                else:
                    self.assertEqual(spec, {"type": "file", "path": validator})
                    self.assertEqual(
                        content, (ROOT / validator).read_text(encoding="utf-8").rstrip()
                    )

    def test_phase_templates_use_phase_specific_bundle_markers(self):
        for phase, keyword in PHASE_ASSETS.items():
            template = (
                ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
            ).read_text(encoding="utf-8")
            self.assertEqual(template.count("{{" + keyword + "}}"), 1)
        phase3 = (ROOT / "prompts" / "templates" / "phase3_prompt.md").read_text(
            encoding="utf-8"
        )
        for keyword in PHASE_ASSETS.values():
            self.assertNotIn("{{" + keyword + "}}", phase3)

    def test_extracted_phase2_bundle_executes_outside_repository(self):
        prompt = build_prompts.render(2)
        with tempfile.TemporaryDirectory() as tempdir:
            temp = Path(tempdir)
            work = temp / "work"
            shutil.copytree(FIXTURE, work)
            matches = list(FILE_RE.finditer(prompt))
            bundled = {match.group("path"): match.group("content") for match in matches}
            for relative in PHASE_BUNDLE_PATHS[2]:
                target = work / "validation_bundle" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(bundled[relative], encoding="utf-8")
            script = work / "validation_bundle" / "scripts/phase_validation/phase2.py"
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
            bundled = {
                match.group("path"): match.group("content")
                for match in FILE_RE.finditer(prompt)
            }
            for relative in PHASE_BUNDLE_PATHS[4]:
                target = work / "validation_bundle" / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(bundled[relative], encoding="utf-8")
            script = work / "validation_bundle" / "scripts/phase_validation/phase4.py"
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
