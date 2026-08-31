import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import nel




class ConfigBootstrapTests(unittest.TestCase):
    def test_initialize_user_settings_copies_template_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            config = root / "config"
            config.mkdir()
            template = config / "settings.json.template"
            settings = config / "settings.json"
            template.write_text('{"schema_version": 1, "pipeline": "self"}\n', encoding="utf-8")
            with patch.object(nel, "CONFIG_DIR", config), patch.object(nel, "SETTINGS_TEMPLATE_PATH", template), patch.object(nel, "SETTINGS_PATH", settings):
                self.assertTrue(nel._initialize_user_settings())
                self.assertEqual(settings.read_bytes(), template.read_bytes())
                settings.write_text('{"custom": true}\n', encoding="utf-8")
                self.assertFalse(nel._initialize_user_settings())
                self.assertEqual(settings.read_text(encoding="utf-8"), '{"custom": true}\n')



class LegacyFacadeTests(unittest.TestCase):
    def test_legacy_config_uses_workflow_local_settings_and_pipelines(self):
        settings, template, pipelines = nel._workflow_config_paths(nel.LEGACY_WORKFLOW)
        self.assertEqual(settings, nel.ROOT / "workflows" / "terraced_v6" / "settings.json")
        self.assertEqual(template, nel.ROOT / "workflows" / "terraced_v6" / "settings.json.template")
        self.assertEqual(pipelines, nel.ROOT / "workflows" / "terraced_v6" / "pipelines")

    def test_legacy_setup_freezes_legacy_workflow_without_root_pipeline_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runs = root / "runs"
            latest = runs / "LATEST"
            unavailable_root_pipelines = root / "canonical-pipelines-not-used"
            with patch.object(nel, "RUNS_DIR", runs), patch.object(nel, "LATEST_PATH", latest), patch.object(nel, "PIPELINES_DIR", unavailable_root_pipelines):
                code = nel.main([
                    "setup", "--legacy", "--mode", "nel-demo", "--example", "1",
                    "--pipeline", "self", "--run-id", "legacy-demo",
                ])
            self.assertEqual(code, 0)
            manifest = json.loads((runs / "legacy-demo" / "run-config" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["workflow"], "terraced-v6")
            self.assertEqual(manifest["pipeline"], "self")
            frozen = runs / "legacy-demo" / "run-config" / "pipelines" / "self.yaml"
            self.assertEqual(frozen.read_bytes(), (nel.LEGACY_PIPELINES_DIR / "self.yaml").read_bytes())

    def test_canonical_pipeline_validation_rejects_legacy_role_shape(self):
        from workflows.proforma_v1 import pipeline_registry
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            pipelines = Path(tmp) / "pipelines"
            pipelines.mkdir()
            doc = yaml.safe_load((nel.PIPELINES_DIR / "lmstudio.yaml").read_text(encoding="utf-8"))
            doc["model_roles"].pop("evidence_adjudication")
            (pipelines / "lmstudio.yaml").write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
            try:
                _step, _self_executor, registry = nel._configure_workflow(
                    nel.CANONICAL_WORKFLOW,
                    settings_path=nel.SETTINGS_TEMPLATE_PATH,
                    pipelines_dir=pipelines,
                )
                with self.assertRaisesRegex(ValueError, "model_roles must map exactly"):
                    registry.load("lmstudio")
            finally:
                pipeline_registry.configure()

    def test_canonical_setup_ignores_invalid_unselected_pipeline(self):
        from workflows.proforma_v1 import pipeline_registry
        import yaml

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            pipelines = root / "pipelines"
            pipelines.mkdir()
            runs = root / "runs"
            latest = runs / "LATEST"

            valid = (nel.PIPELINES_DIR / "lmstudio.yaml").read_text(encoding="utf-8")
            (pipelines / "lmstudio.yaml").write_text(valid, encoding="utf-8")
            stale = yaml.safe_load(valid)
            stale["model_roles"].pop("evidence_adjudication")
            (pipelines / "openrouter.yaml").write_text(
                yaml.safe_dump(stale, sort_keys=False), encoding="utf-8"
            )

            try:
                with patch.object(nel, "PIPELINES_DIR", pipelines), patch.object(nel, "RUNS_DIR", runs), patch.object(nel, "LATEST_PATH", latest):
                    code = nel.main([
                        "setup", "--mode", "nel-demo", "--example", "6",
                        "--pipeline", "lmstudio", "--run-id", "selected-pipeline-only",
                    ])
                self.assertEqual(code, 0)
                manifest = json.loads(
                    (runs / "selected-pipeline-only" / "run-config" / "manifest.json").read_text(encoding="utf-8")
                )
                self.assertEqual(manifest["workflow"], "proforma-v1")
                self.assertEqual(manifest["pipeline"], "lmstudio")
            finally:
                pipeline_registry.configure()


class RunInventoryTests(unittest.TestCase):
    def _run(self, root: Path, pipeline: str) -> Path:
        run = root / "run"
        run.mkdir()
        (run / "case.md").write_text("case\n", encoding="utf-8")
        (run / "workflow.json").write_text(
            json.dumps({
                "schema_version": 1,
                "workflow_id": "terraced-v6",
                "mode": "ngs-report",
                "model_profile": pipeline,
            }),
            encoding="utf-8",
        )
        config = run / "run-config"
        config.mkdir()
        (config / "manifest.json").write_text(
            json.dumps({"workflow": "terraced-v6", "pipeline": pipeline, "mode": "ngs-report"}),
            encoding="utf-8",
        )
        return run

    def _artifact(self, run: Path, number: int, group: str, name: str) -> None:
        directory = run / "intermediates" / f"{number:03d}_{group}"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / name).write_text("x: y\n", encoding="utf-8")

    def test_setup_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            self.assertEqual(nel.inspect_run(run)["label"], "Setup only")

    def test_self_diagnosis_advances_to_ptbg(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            self._artifact(run, 4, "diagnosis", "diagnosis-final.yaml")
            status = nel.inspect_run(run)
            self.assertEqual(status["label"], "At PTBG")
            self.assertEqual(status["stage"], "ptbg")

    def test_self_who2_canonical_group_advances_to_ptbg(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            self._artifact(run, 4, "diagnosis_who5_pass_2", "who5.yaml")
            status = nel.inspect_run(run)
            self.assertEqual(status["label"], "At PTBG")
            self.assertEqual(status["stage"], "ptbg")

    def test_external_diagnosis_advances_to_prognosis(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "lmstudio")
            self._artifact(run, 4, "diagnosis", "diagnosis-final.yaml")
            status = nel.inspect_run(run)
            self.assertEqual(status["label"], "At prognosis")
            self.assertEqual(status["stage"], "prognosis")

    def test_complete_is_report_final(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            (run / "report-final.md").write_text("report\n", encoding="utf-8")
            status = nel.inspect_run(run)
            self.assertTrue(status["complete"])
            self.assertEqual(status["label"], "Complete")

    def test_run_workflow_prefers_frozen_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            run = self._run(Path(tmp), "self")
            (run / "workflow.json").write_text(
                json.dumps({"workflow_id": "proforma-v1", "model_profile": "self"}),
                encoding="utf-8",
            )
            self.assertEqual(nel._run_workflow(run), "terraced-v6")

    def test_canonical_executor_modules_are_proforma(self):
        step, self_executor, registry = nel._workflow_modules(nel.CANONICAL_WORKFLOW)
        self.assertEqual(step.WORKFLOW_ID, "proforma-v1")
        self.assertTrue(self_executor.__name__.startswith("workflows.proforma_v1"))
        self.assertTrue(registry.__name__.startswith("workflows.proforma_v1"))

    def test_legacy_executor_modules_remain_available(self):
        step, self_executor, registry = nel._workflow_modules(nel.LEGACY_WORKFLOW)
        self.assertEqual(step.WORKFLOW_ID, "terraced-v6")
        self.assertTrue(self_executor.__name__.startswith("workflows.terraced_v6"))
        self.assertTrue(registry.__name__.startswith("workflows.terraced_v6"))

    def test_rejects_path_like_run_id(self):
        with self.assertRaises(nel.CLIError):
            nel._validate_run_id("../outside")


if __name__ == "__main__":
    unittest.main()
