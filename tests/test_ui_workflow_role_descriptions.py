from pathlib import Path
import unittest

from workflows.proforma_v1 import pipeline_registry
from workflows.proforma_v1.engine import workflow_compiler
from workflows.proforma_v1.engine.workflow_loader import load as load_workflow
from ui import workflow_server

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / "workflows" / "proforma_v1" / "workflow"


class WorkflowRoleDescriptionTests(unittest.TestCase):
    def test_shipped_workflows_describe_every_workflow_model_role(self):
        for name in ("default", "default_reviewed", "default_reviewed_v2", "reasoning"):
            path = WORKFLOW_DIR / f"{name}.yaml"
            workflow_compiler.compile_workflow(path)
            doc = load_workflow(path)
            descriptions = (doc.get("presentation") or {}).get("model_roles") or {}
            referenced = {
                str(step.get("role"))
                for step in (doc.get("steps") or {}).values()
                if isinstance(step, dict) and step.get("role")
            }
            for policy in (doc.get("evidence_policies") or {}).values():
                if not isinstance(policy, dict):
                    continue
                for phase in ("assignment", "audit", "adjudication"):
                    row = policy.get(phase) or {}
                    if isinstance(row, dict) and row.get("role"):
                        referenced.add(str(row["role"]))
            self.assertLessEqual(referenced, set(descriptions), name)
            self.assertIn("syntax_repair", descriptions)
            self.assertIn("marking", descriptions)

    def test_workflow_bootstrap_metadata_distinguishes_used_roles(self):
        rows = {row["id"]: row for row in workflow_server.workflow_definitions()}
        self.assertNotIn("reasoning_audit", rows["default"]["model_roles"])
        self.assertNotIn("reasoning_adjudication", rows["default"]["model_roles"])
        self.assertIn("reasoning_audit", rows["default_reviewed_v2"]["model_roles"])
        self.assertIn("reasoning_adjudication", rows["default_reviewed_v2"]["model_roles"])
        self.assertIn("dissent_summary", rows["reasoning"]["model_roles"])
        self.assertEqual(
            set(pipeline_registry.ROLES) - set(rows["default"]["model_roles"]),
            {"reasoning_audit", "reasoning_adjudication"},
        )

if __name__ == "__main__":
    unittest.main()
