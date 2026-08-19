import unittest

from scripts.build_skill_zip import DEFAULT_MANIFEST, read_patterns, resolve_manifest


class ReleaseManifestTests(unittest.TestCase):
    def test_release_manifest_patterns_match_tracked_files(self):
        patterns = read_patterns(DEFAULT_MANIFEST)

        resolved = resolve_manifest(patterns)

        self.assertTrue(resolved)
        self.assertIn("validation/case_functional_manifest.md", resolved)

    def test_unmatched_pattern_reports_clear_error(self):
        pattern = "validation/does-not-exist.md"

        with self.assertRaisesRegex(
            SystemExit,
            rf"^Release manifest pattern matched no tracked files: {pattern}$",
        ):
            resolve_manifest([pattern])


if __name__ == "__main__":
    unittest.main()