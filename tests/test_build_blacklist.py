import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import build_blacklist  # noqa: E402


class BuildBlacklistTests(unittest.TestCase):
    def test_converts_yaml_to_deterministic_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "blacklist.yaml"
            output = tmp / "blacklist.json"
            source.write_text(
                "enabled: true\n"
                "papers:\n"
                "  paper-a:\n"
                "    categories:\n"
                "      include: [diagnosis]\n",
                encoding="utf-8",
            )

            result = build_blacklist.convert(source, output)

            self.assertEqual(result, output)
            self.assertEqual(
                json.loads(output.read_text(encoding="utf-8")),
                {
                    "enabled": True,
                    "papers": {
                        "paper-a": {"categories": {"include": ["diagnosis"]}}
                    },
                },
            )
            self.assertTrue(output.read_text(encoding="utf-8").endswith("\n"))

    def test_empty_yaml_becomes_empty_object(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "blacklist.yaml"
            output = tmp / "blacklist.json"
            source.write_text("# empty policy\n", encoding="utf-8")

            build_blacklist.convert(source, output)

            self.assertEqual(output.read_text(encoding="utf-8"), "{}\n")

    def test_invalid_yaml_fails_loudly(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            source = tmp / "blacklist.yaml"
            source.write_text("papers: [\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "blacklist YAML is invalid"):
                build_blacklist.convert(source, tmp / "blacklist.json")


if __name__ == "__main__":
    unittest.main()