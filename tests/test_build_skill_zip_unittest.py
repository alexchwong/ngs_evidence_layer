import unittest
from pathlib import Path

from scripts.build_skill_zip import (
    DEFAULT_MANIFEST,
    git_output,
    read_patterns,
    resolve_manifest,
)


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent


class ReleaseManifestTests(unittest.TestCase):
    def test_release_manifest_patterns_match_tracked_files(self):
        patterns = read_patterns(DEFAULT_MANIFEST)

        resolved = resolve_manifest(patterns)

        self.assertTrue(resolved)
        self.assertIn("validation/case_functional_manifest.md", resolved)

    def test_release_manifest_includes_validation_suites_and_developer_guide(self):
        patterns = read_patterns(DEFAULT_MANIFEST)
        self.assertIn(":(glob)validation/*.md", patterns)
        self.assertTrue((REPOSITORY_ROOT / "validation" / "validation_dublin.md").is_file())
        self.assertTrue((REPOSITORY_ROOT / "validation" / "DEVEL.md").is_file())

    def test_unmatched_pattern_reports_clear_error(self):
        pattern = "validation/does-not-exist.md"

        with self.assertRaisesRegex(
            SystemExit,
            rf"^Release manifest pattern matched no tracked files: {pattern}$",
        ):
            resolve_manifest([pattern])

    def test_release_exports_all_tracked_cul_profiles_without_editor_tooling(self):
        patterns = read_patterns(DEFAULT_MANIFEST)
        resolved = resolve_manifest(patterns)
        tracked_profiles = {
            entry.decode("utf-8", errors="surrogateescape")
            for entry in git_output("ls-files", "-z", "--", "config/cul/*.json").split(b"\0")
            if entry
        }

        self.assertIn("config/cul/*.json", patterns)
        self.assertNotIn("config/cul/default.json", patterns)
        self.assertTrue(tracked_profiles)
        self.assertTrue(tracked_profiles.issubset(resolved))
        for optional_path in (
            "docs/cul.md",
            "scripts/cul.py",
            "scripts/build_card_browser.py",
            "scripts/assets/card_browser_template.html",
            "scripts/assets/corpus_user_layer_template.html",
            "scripts/assets/card_browser_cul.js",
        ):
            self.assertNotIn(optional_path, resolved)

    def test_release_globs_exclude_workflow_tests(self):
        resolved = resolve_manifest(read_patterns(DEFAULT_MANIFEST))

        self.assertFalse(
            any(
                path.startswith("workflows/terraced_v6/tests/")
                or path.startswith("workflows/proforma_v1/tests/")
                for path in resolved
            )
        )

    def test_ingestion_dependency_is_excluded_from_skill_requirements(self):
        runtime_requirements = (
            REPOSITORY_ROOT / "requirements.txt"
        ).read_text(encoding="utf-8")
        ingestion_requirements = (
            REPOSITORY_ROOT / "requirements-ingest.txt"
        ).read_text(encoding="utf-8")
        release_patterns = read_patterns(DEFAULT_MANIFEST)

        self.assertNotIn("opendataloader-pdf", runtime_requirements.lower())
        self.assertIn("-r requirements.txt", ingestion_requirements)
        self.assertIn("opendataloader-pdf", ingestion_requirements.lower())
        self.assertIn("requirements.txt", release_patterns)
        self.assertNotIn("requirements-ingest.txt", release_patterns)


if __name__ == "__main__":
    unittest.main()