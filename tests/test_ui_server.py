"""Unit tests for the local browser interface server.

The tests exercise the server in-process. Only one test shells out to nel.py;
it is skipped when the runtime dependencies are unavailable.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ui import server  # noqa: E402


def _has_runtime_deps() -> bool:
    try:
        import jsonschema  # noqa: F401
        import yaml  # noqa: F401
    except ImportError:
        return False
    return True


HAS_DEPS = _has_runtime_deps()
requires_deps = unittest.skipUnless(HAS_DEPS, "jsonschema and PyYAML are required")


def _valid_payload(name="ui-test", roles=None):
    roles = roles if roles is not None else server.roles()
    return {
        "name": name,
        "description": "test profile",
        "provider": {
            "base_url": "https://openrouter.ai/api/v1",
            "base_url_env": "NEL_OPENROUTER_BASE_URL",
            "api_key_env": "OPENROUTER_API_KEY",
            "timeout_s": "900",
            "api_key_required": True,
        },
        "aliases": [
            {"alias": "fast", "model": "qwen/qwen3-coder-next",
             "routing": {"order": "groq, cerebras", "only": "", "ignore": "",
                         "allow_fallbacks": False, "require_parameters": None}},
            {"alias": "plain", "model": "openai/gpt-oss-20b", "routing": {}},
        ],
        "roles": {role: {"model": "fast", "temperature": "0.0", "max_tokens": "16384"}
                  for role in roles},
    }


# ---------------------------------------------------------------- token/HTTP

@requires_deps
class TokenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        server.Handler.token = "test-token-value"
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()

    def _get(self, path, token=None):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}")
        if token is not None:
            request.add_header("X-NEL-Token", token)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return response.status, response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            return exc.code, exc.read().decode("utf-8")

    def test_api_rejects_missing_token(self):
        status, _ = self._get("/api/bootstrap")
        self.assertEqual(status, 403)

    def test_api_rejects_wrong_token(self):
        status, _ = self._get("/api/bootstrap", token="wrong")
        self.assertEqual(status, 403)

    def test_bootstrap_with_token(self):
        status, body = self._get("/api/bootstrap", token=server.Handler.token)
        self.assertEqual(status, 200)
        doc = json.loads(body)
        for key in ("pipelines", "roles", "stages", "modes", "examples", "validation"):
            self.assertIn(key, doc)
        self.assertEqual(doc["workflow"], "proforma-v1")

    def test_page_rejects_missing_query_token(self):
        status, _ = self._get("/")
        self.assertEqual(status, 403)

    def test_page_injects_token(self):
        status, body = self._get(f"/?t={server.Handler.token}")
        self.assertEqual(status, 200)
        self.assertNotIn("__NEL_TOKEN__", body)
        self.assertIn(server.Handler.token, body)

    def test_asset_rejects_separators(self):
        status, _ = self._get("/assets/../server.py")
        self.assertIn(status, (403, 404))

    def test_unknown_api_endpoint(self):
        status, _ = self._get("/api/nope", token=server.Handler.token)
        self.assertEqual(status, 404)


# ------------------------------------------------------------------- paths

class PathTests(unittest.TestCase):
    def test_safe_child_allows_nested(self):
        base = ROOT / "runs"
        self.assertEqual(
            server.safe_child(base, "intermediates/001_x/case.json"),
            (base / "intermediates" / "001_x" / "case.json").resolve(),
        )

    def test_safe_child_refuses_escape(self):
        with self.assertRaises(server.UIError):
            server.safe_child(ROOT / "runs", "../../etc/passwd")

    def test_check_run_id_accepts_and_trims(self):
        self.assertEqual(server.check_run_id("  20260101T000000Z-demo-1 "), "20260101T000000Z-demo-1")

    def test_check_run_id_rejects(self):
        for bad in ["", "LATEST", "../evil", "has space", "-leading", ".", ".."]:
            with self.subTest(bad=bad), self.assertRaises(server.UIError):
                server.check_run_id(bad)

    def test_generated_run_id_is_valid(self):
        for label in ["case", "demo-1", "validate-1A", "a b/c"]:
            with self.subTest(label=label):
                server.check_run_id(server.generated_run_id(label))


# --------------------------------------------------------------- discovery

@requires_deps
class DiscoveryTests(unittest.TestCase):
    def test_validation_suites_present(self):
        cases = server.validation_cases()
        self.assertIn("nel-validate", cases)
        self.assertIn("nel-validate-function", cases)
        self.assertIn("1A", cases["nel-validate"])
        self.assertIn("1A", cases["nel-validate-function"])

    def test_brief_suite_numeric(self):
        cases = server.validation_cases()
        self.assertTrue(cases.get("nel-validate-brief"))
        for case_id in cases["nel-validate-brief"]:
            self.assertTrue(case_id.isdigit(), case_id)

    def test_dual_suite_present(self):
        self.assertTrue(server.validation_cases().get("nel-validate-dual"))

    def test_demo_examples(self):
        examples = server.demo_examples()
        self.assertTrue(examples)
        self.assertEqual(examples[0], 1)

    def test_self_hidden(self):
        names = [row["name"] for row in server.list_pipelines()]
        self.assertNotIn("self", names)
        self.assertIn("openrouter", names)

    def test_default_pipeline_falls_back_off_self(self):
        name, note = server.default_pipeline()
        self.assertNotIn(name, server.HIDDEN_PIPELINES)
        if name:
            self.assertIn(name, [row["name"] for row in server.list_pipelines()])
        settings = ROOT / "config" / "settings.json"
        if settings.is_file():
            configured = json.loads(settings.read_text(encoding="utf-8")).get("pipeline")
            if configured in server.HIDDEN_PIPELINES:
                self.assertTrue(note)

    def test_modes_include_dual(self):
        self.assertIn("nel-validate-dual", server.modes())

    def test_roles_include_adjudication(self):
        self.assertIn("evidence_adjudication", server.roles())

    def test_cul_profiles(self):
        self.assertIn("default", server.cul_profiles())


# ------------------------------------------------------------- composition

@requires_deps
class CompositionTests(unittest.TestCase):
    def test_document_validates(self):
        name, doc = server.compose_pipeline(_valid_payload())
        self.assertEqual(name, "ui-test")
        server.validate_pipeline(doc)

    def test_scalar_alias_without_routing(self):
        _name, doc = server.compose_pipeline(_valid_payload())
        self.assertEqual(doc["model_aliases"]["plain"], "openai/gpt-oss-20b")

    def test_order_split_into_list(self):
        _name, doc = server.compose_pipeline(_valid_payload())
        routing = doc["model_aliases"]["fast"]["provider"]
        self.assertEqual(routing["order"], ["groq", "cerebras"])

    def test_false_boolean_preserved_and_unset_omitted(self):
        _name, doc = server.compose_pipeline(_valid_payload())
        routing = doc["model_aliases"]["fast"]["provider"]
        self.assertIs(routing["allow_fallbacks"], False)
        self.assertNotIn("require_parameters", routing)

    def test_missing_role_rejected_by_name(self):
        payload = _valid_payload()
        payload["roles"].pop("evidence_adjudication")
        with self.assertRaises(server.UIError) as ctx:
            server.compose_pipeline(payload)
        self.assertIn("evidence_adjudication", str(ctx.exception))

    def test_unknown_role_rejected_by_name(self):
        payload = _valid_payload()
        payload["roles"]["not_a_role"] = {"model": "fast", "temperature": "0", "max_tokens": "10"}
        with self.assertRaises(server.UIError) as ctx:
            server.compose_pipeline(payload)
        self.assertIn("not_a_role", str(ctx.exception))

    def test_role_naming_unknown_option_rejected(self):
        payload = _valid_payload()
        payload["roles"]["structure"]["model"] = "missing"
        with self.assertRaises(server.UIError):
            server.compose_pipeline(payload)

    def test_missing_base_url_rejected(self):
        payload = _valid_payload()
        payload["provider"]["base_url"] = ""
        with self.assertRaises(server.UIError):
            server.compose_pipeline(payload)

    def test_zero_max_tokens_rejected(self):
        payload = _valid_payload()
        payload["roles"]["structure"]["max_tokens"] = "0"
        with self.assertRaises(server.UIError):
            server.compose_pipeline(payload)

    def test_non_numeric_max_tokens_rejected(self):
        payload = _valid_payload()
        payload["roles"]["structure"]["max_tokens"] = "lots"
        with self.assertRaises(server.UIError):
            server.compose_pipeline(payload)

    def test_form_text_numbers_accepted(self):
        payload = _valid_payload()
        payload["provider"]["timeout_s"] = "900"
        payload["roles"]["structure"]["max_tokens"] = "65536"
        payload["roles"]["structure"]["temperature"] = "0.2"
        _name, doc = server.compose_pipeline(payload)
        self.assertEqual(doc["provider"]["timeout_s"], 900)
        self.assertEqual(doc["model_roles"]["structure"]["max_tokens"], 65536)
        self.assertAlmostEqual(doc["model_roles"]["structure"]["temperature"], 0.2)

    def test_shipped_name_refused(self):
        payload = _valid_payload(name="openrouter")
        with self.assertRaises(server.UIError):
            server.compose_pipeline(payload)

    def test_save_refuses_existing_without_overwrite(self):
        directory = Path(tempfile.mkdtemp())
        original = server.PIPELINE_DIR
        server.PIPELINE_DIR = directory
        try:
            _name, doc = server.compose_pipeline(_valid_payload())
            server.save_pipeline("ui-test", doc)
            with self.assertRaises(server.UIError):
                server.save_pipeline("ui-test", doc)
            server.save_pipeline("ui-test", doc, overwrite=True)
            body = (directory / "ui-test.yaml").read_text(encoding="utf-8")
            self.assertIn("Never store an API key", body)
        finally:
            server.PIPELINE_DIR = original
            shutil.rmtree(directory, ignore_errors=True)


# ---------------------------------------------------------- JSON extraction

class JsonExtractionTests(unittest.TestCase):
    def test_object_after_diagnostic_line(self):
        text = "[retrieve] blacklist excluded 3 cards\n{\"ok\": true, \"errors\": []}\n"
        self.assertEqual(server.extract_json(text), {"ok": True, "errors": []})

    def test_bare_array_after_noise(self):
        text = "some noise\n[{\"run_id\": \"a\"}]\n"
        self.assertEqual(server.extract_json(text), [{"run_id": "a"}])

    def test_absent_json_raises(self):
        with self.assertRaises(server.UIError):
            server.extract_json("no json here at all")


# ------------------------------------------------------------------ console

class ConsoleTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.original = server.CONSOLE_DIR
        server.CONSOLE_DIR = self.directory

    def tearDown(self):
        server.CONSOLE_DIR = self.original
        shutil.rmtree(self.directory, ignore_errors=True)

    def test_tail_returns_only_new_bytes(self):
        path = server.console_path("run1")
        path.write_bytes(b"first\n")
        first = server.read_console("run1", 0)
        self.assertEqual(first["text"], "first\n")
        with open(path, "ab") as handle:
            handle.write(b"second\n")
        second = server.read_console("run1", first["offset"])
        self.assertEqual(second["text"], "second\n")

    def test_offset_past_end_restarts(self):
        path = server.console_path("run2")
        path.write_bytes(b"abc\n")
        doc = server.read_console("run2", 999)
        self.assertEqual(doc["text"], "abc\n")
        self.assertEqual(doc["offset"], 4)

    def test_missing_log_is_empty(self):
        doc = server.read_console("run3", 0)
        self.assertEqual(doc, {"offset": 0, "text": "", "size": 0})


# ------------------------------------------------------------------- usage

@requires_deps
class UsageTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.original = server.RUNS_DIR
        server.RUNS_DIR = self.directory

    def tearDown(self):
        server.RUNS_DIR = self.original
        shutil.rmtree(self.directory, ignore_errors=True)

    def _ledger(self, run_id, calls):
        logs = self.directory / run_id / "logs"
        logs.mkdir(parents=True, exist_ok=True)
        (logs / "model-usage.json").write_text(
            json.dumps({"schema_version": 2, "calls": calls}), encoding="utf-8"
        )

    def test_totals_and_cost(self):
        self._ledger("r1", [
            {"call_index": 1, "operation": "structure", "logical_operation": "structure",
             "call_kind": "model", "provider": "openrouter", "duration_ms": 1200,
             "usage": {"prompt_tokens": 10, "completion_tokens": 5,
                       "total_tokens": 15, "cost_usd": 0.001}},
        ])
        doc = server.usage("r1")
        self.assertTrue(doc["available"])
        self.assertEqual(doc["summary"]["totals"]["total_tokens"], 15)
        self.assertTrue(doc["summary"]["cost"]["complete"])

    def test_cost_absent_marks_incomplete(self):
        self._ledger("r2", [
            {"call_index": 1, "operation": "structure", "logical_operation": "structure",
             "call_kind": "model", "provider": "lmstudio", "duration_ms": 1,
             "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}},
        ])
        doc = server.usage("r2")
        self.assertIsNone(doc["summary"]["cost"]["amount"])
        self.assertFalse(doc["summary"]["cost"]["complete"])

    def test_missing_ledger(self):
        (self.directory / "r3").mkdir(parents=True, exist_ok=True)
        self.assertFalse(server.usage("r3")["available"])


# ----------------------------------------------------------- runs lifecycle

@requires_deps
class LifecycleTests(unittest.TestCase):
    def setUp(self):
        self.directory = Path(tempfile.mkdtemp())
        self.console = Path(tempfile.mkdtemp())
        self.cases = Path(tempfile.mkdtemp())
        self.originals = (server.RUNS_DIR, server.CONSOLE_DIR, server.CASE_DIR,
                          server.LATEST_PATH)
        server.RUNS_DIR = self.directory
        server.CONSOLE_DIR = self.console
        server.CASE_DIR = self.cases
        server.LATEST_PATH = self.directory / "LATEST"

    def tearDown(self):
        (server.RUNS_DIR, server.CONSOLE_DIR, server.CASE_DIR,
         server.LATEST_PATH) = self.originals
        for path in (self.directory, self.console, self.cases):
            shutil.rmtree(path, ignore_errors=True)

    def _make_run(self, run_id="r1"):
        run = self.directory / run_id
        (run / "intermediates" / "001_structured_case").mkdir(parents=True)
        (run / "model_steps" / "001_structure").mkdir(parents=True)
        (run / "logs").mkdir(parents=True)
        (run / "run-config").mkdir(parents=True)
        (run / "case.md").write_text("clinical text\n", encoding="utf-8")
        (run / "report-final.md").write_text("# Report\n", encoding="utf-8")
        (run / "intermediates" / "001_structured_case" / "case.json").write_text("{}", encoding="utf-8")
        (run / "run-config" / "manifest.json").write_text(
            json.dumps({"pipeline": "lmstudio", "workflow": "proforma-v1"}), encoding="utf-8")
        server.LATEST_PATH.write_text(run_id + "\n", encoding="utf-8")
        return run

    def test_delete_removes_run_and_clears_latest(self):
        self._make_run("r1")
        server.console_path("r1").write_bytes(b"log\n")
        server.action_delete({"run_id": "r1"})
        self.assertFalse((self.directory / "r1").exists())
        self.assertFalse(server.console_path("r1").exists())
        self.assertFalse(server.LATEST_PATH.exists())

    def test_delete_missing_run(self):
        with self.assertRaises(server.UIError):
            server.action_delete({"run_id": "nope"})

    def test_archive_removes_working_files_and_keeps_report(self):
        run = self._make_run("r2")
        result = server.action_archive({"run_id": "r2"})
        self.assertEqual(sorted(result["removed"]),
                         ["case.md", "intermediates", "model_steps"])
        self.assertFalse((run / "case.md").exists())
        self.assertFalse((run / "intermediates").exists())
        self.assertTrue((run / "report-final.md").is_file())
        self.assertTrue((run / "run-config" / "manifest.json").is_file())
        self.assertTrue(server.is_archived("r2"))

    def test_archive_twice_refused(self):
        self._make_run("r3")
        server.action_archive({"run_id": "r3"})
        with self.assertRaises(server.UIError):
            server.action_archive({"run_id": "r3"})

    def test_run_refuses_archived(self):
        self._make_run("r4")
        server.action_archive({"run_id": "r4"})
        with self.assertRaises(server.UIError):
            server.action_run({"run_id": "r4"})

    def test_files_listing_is_relative_and_sorted(self):
        self._make_run("r5")
        paths = [row["path"] for row in server.run_files("r5")]
        self.assertIn("intermediates/001_structured_case/case.json", paths)
        self.assertEqual(paths, sorted(paths))

    def test_read_run_file_contained(self):
        self._make_run("r6")
        doc = server.read_run_file("r6", "case.md")
        self.assertEqual(doc["text"], "clinical text\n")
        with self.assertRaises(server.UIError):
            server.read_run_file("r6", "../../etc/passwd")

    def test_sweep_case_files(self):
        server.case_path("orphan").write_text("stale\n", encoding="utf-8")
        self.assertEqual(server.sweep_case_files(), 1)
        self.assertFalse(server.case_path("orphan").exists())


# --------------------------------------------------------------- admission

class AdmissionTests(unittest.TestCase):
    class _FakeChild:
        def __init__(self, run_id, phase, exclusive):
            self.run_id = run_id
            self.phase = phase
            self.exclusive = exclusive
            self.active = True

    def setUp(self):
        self.registry = server.Registry()

    def _seed(self, run_id, phase="run", exclusive=False):
        self.registry._children[run_id] = self._FakeChild(run_id, phase, exclusive)

    def test_local_run_blocks_everything(self):
        self._seed("local", exclusive=True)
        with self.assertRaises(server.UIError) as ctx:
            self.registry._admit("other", False, "run")
        self.assertIn("local", str(ctx.exception))

    def test_local_run_refused_beside_remote(self):
        self._seed("remote", exclusive=False)
        with self.assertRaises(server.UIError):
            self.registry._admit("local", True, "run")

    def test_remote_runs_admitted_up_to_limit(self):
        for index in range(server.REMOTE_RUN_LIMIT):
            self._seed(f"r{index}", exclusive=False)
        with self.assertRaises(server.UIError):
            self.registry._admit("one-too-many", False, "run")

    def test_setup_exempt_from_limit(self):
        for index in range(server.REMOTE_RUN_LIMIT):
            self._seed(f"r{index}", exclusive=False)
        self.registry._admit("a-setup", False, "setup")

    def test_same_run_twice_refused(self):
        self._seed("r1", exclusive=False)
        with self.assertRaises(server.UIError):
            self.registry._admit("r1", False, "run")


# ----------------------------------------------------------------- secrets

class SecretTests(unittest.TestCase):
    def tearDown(self):
        server.SECRETS.pop("NEL_TEST_KEY", None)

    def test_secret_reaches_child_env_without_mutating_os_environ(self):
        server.SECRETS["NEL_TEST_KEY"] = "value"
        env = server.child_env()
        self.assertEqual(env["NEL_TEST_KEY"], "value")
        self.assertEqual(env["PYTHONUNBUFFERED"], "1")
        self.assertNotIn("NEL_TEST_KEY", os.environ)

    def test_empty_secret_is_not_injected(self):
        server.SECRETS["NEL_TEST_KEY"] = ""
        self.assertNotIn("NEL_TEST_KEY", server.child_env())


@requires_deps
class ConfigCheckSecretTests(unittest.TestCase):
    """A held session key must satisfy the profile's required-key check."""

    def tearDown(self):
        server.SECRETS.pop("OPENROUTER_API_KEY", None)

    @unittest.skipIf(os.environ.get("OPENROUTER_API_KEY"), "a real key is already in the environment")
    def test_key_satisfies_required_check(self):
        without = server.config_check("openrouter")
        self.assertTrue(
            any("OPENROUTER_API_KEY" in str(error) for error in without.get("errors", [])),
            f"expected a missing-key error, got {without.get('errors')}",
        )
        server.SECRETS["OPENROUTER_API_KEY"] = "test-key-not-used-for-a-request"
        with_key = server.config_check("openrouter")
        self.assertFalse(
            any("OPENROUTER_API_KEY" in str(error) for error in with_key.get("errors", [])),
            f"key was not injected; errors: {with_key.get('errors')}",
        )


if __name__ == "__main__":
    unittest.main()
