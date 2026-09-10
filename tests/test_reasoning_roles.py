import tempfile
import unittest
from pathlib import Path

import yaml

from workflows.proforma_v1 import pipeline_registry


def _doc(reasoning=None):
    roles = {}
    for role in pipeline_registry.ROLES:
        row = {"model": "main", "temperature": 0.0, "max_tokens": 4096}
        if reasoning is not None and role == "diagnosis":
            row["reasoning"] = reasoning
        roles[role] = row
    return {
        "pipeline": {"version": 1, "description": "test"},
        "provider": {
            "type": "openai-compatible",
            "base_url": "https://openrouter.ai/api/v1",
            "timeout_s": 30,
        },
        "model_aliases": {"main": "example/model"},
        "model_roles": roles,
    }


class ReasoningRoleRegistryTests(unittest.TestCase):
    def _load(self, doc):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "reasoning-test.yaml"
            path.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
            return pipeline_registry.load_yaml(path)

    def test_existing_profile_without_reasoning_defaults_unchanged(self):
        plan = self._load(_doc())
        self.assertEqual(pipeline_registry.binding(plan, "diagnosis").reasoning, "default")

    def test_reasoning_level_is_bound_per_role(self):
        plan = self._load(_doc("high"))
        self.assertEqual(pipeline_registry.binding(plan, "diagnosis").reasoning, "high")
        self.assertEqual(pipeline_registry.binding(plan, "structure").reasoning, "default")

    def test_alias_defaults_supply_inference_parameters(self):
        doc = _doc()
        doc["model_aliases"]["main"] = {
            "model": "example/model",
            "temperature": 0.25,
            "max_tokens": 12345,
            "reasoning": "medium",
        }
        for row in doc["model_roles"].values():
            row.pop("temperature", None)
            row.pop("max_tokens", None)
            row.pop("reasoning", None)
        plan = self._load(doc)
        binding = pipeline_registry.binding(plan, "diagnosis")
        self.assertEqual(binding.temperature, 0.25)
        self.assertEqual(binding.max_tokens, 12345)
        self.assertEqual(binding.reasoning, "medium")

    def test_role_override_wins_over_alias_default(self):
        doc = _doc()
        doc["model_aliases"]["main"] = {
            "model": "example/model", "temperature": 0.0, "max_tokens": 16384, "reasoning": "default"
        }
        doc["model_roles"]["diagnosis"] = {"model": "main", "max_tokens": 65536, "reasoning": "high"}
        plan = self._load(doc)
        binding = pipeline_registry.binding(plan, "diagnosis")
        self.assertEqual(binding.max_tokens, 65536)
        self.assertEqual(binding.reasoning, "high")

    def test_invalid_reasoning_level_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "reasoning must be one of"):
            self._load(_doc("ultra"))


if __name__ == "__main__":
    unittest.main()
