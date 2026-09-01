from __future__ import annotations

import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
ROLES = {
    "structure", "diagnosis", "ptbg", "evidence_match", "evidence_audit",
    "evidence_adjudication", "report_write", "preservation_check", "syntax_repair",
}


class BatchPipelineConfigTests(unittest.TestCase):
    def test_lmstudio_is_serial(self):
        doc = yaml.safe_load((ROOT / "config/pipelines/lmstudio.yaml").read_text(encoding="utf-8"))
        self.assertEqual(doc["execution"]["max_parallel_cases"], 1)
        self.assertEqual(set(doc["model_roles"]), ROLES)

    def test_openrouter_default_is_four(self):
        doc = yaml.safe_load((ROOT / "config/pipelines/openrouter.yaml").read_text(encoding="utf-8"))
        self.assertEqual(doc["execution"]["max_parallel_cases"], 4)
        self.assertEqual(set(doc["model_roles"]), ROLES)


if __name__ == "__main__":
    unittest.main()
