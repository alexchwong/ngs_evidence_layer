"""Local browser interface server for the canonical proforma-v1 workflow.

The server is a client of the root ``nel.py`` command line interface. It never
imports workflow execution code: every mutating operation is a subprocess whose
exact command line is echoed into the console pane. Three repository modules are
imported, all read-only:

* ``workflows.proforma_v1.pipeline_registry`` for the role list and profile validation
* ``validation.scripts.bundled_cases`` for demo and validation case discovery
* ``scripts.model_usage`` for token, duration and cost summarisation

Binding is the literal loopback address; there is no host option.
"""
from __future__ import annotations

import base64
import json
import os
import re
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, parse_qs

ROOT = Path(__file__).resolve().parent.parent
UI_DIR = ROOT / "ui"
ASSET_DIR = UI_DIR / "assets"
RUNS_DIR = ROOT / "runs"
LATEST_PATH = RUNS_DIR / "LATEST"
STATE_DIR = ROOT / ".nel-ui"
CONSOLE_DIR = STATE_DIR / "console"
CASE_DIR = STATE_DIR / "cases"
PIPELINE_DIR = ROOT / "config" / "pipelines"
SETTINGS_PATH = ROOT / "config" / "settings.json"
CUL_DIR = ROOT / "config" / "cul"
VERSION_PATH = ROOT / "release" / "VERSION"
WORKFLOW_JSON = ROOT / "workflows" / "proforma_v1" / "workflow.json"

WORKFLOW_ID = "proforma-v1"
WORKFLOW_PACKAGE = "workflows.proforma_v1"

HIDDEN_PIPELINES = {"self"}
SHIPPED_PIPELINES = {"self", "lmstudio", "openrouter"}
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1", "0.0.0.0"}
REMOTE_RUN_LIMIT = 4

ROUTING_LIST_FIELDS = ("order", "only", "ignore")
ROUTING_BOOL_FIELDS = ("allow_fallbacks", "require_parameters")

STAGES = (
    ("setup", "Setup"),
    ("diagnosis", "Diagnosis"),
    ("prognosis", "Prognosis"),
    ("treatment", "Treatment"),
    ("biomarker", "Biomarker"),
    ("germline", "Germline"),
    ("evidence_review", "Evidence"),
    ("report_synthesis", "Report"),
    ("complete", "Done"),
)

RUN_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
MAX_FILE_BYTES = 512 * 1024
MAX_BODY_BYTES = 4 * 1024 * 1024
NEL_TIMEOUT = 180
CATALOGUE_TIMEOUT = 15
ARCHIVE_MARKER = "ARCHIVED.json"

BIND_HOST = "127.0.0.1"


class UIError(RuntimeError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = str(message)
        self.status = int(status)


# --------------------------------------------------------------------------
# repository inspection
# --------------------------------------------------------------------------

def _ensure_root_on_path() -> None:
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))


_ROLES_CACHE: tuple[str, ...] | None = None


def roles() -> tuple[str, ...]:
    """Authoritative role list, taken from the workflow's own registry."""
    global _ROLES_CACHE
    if _ROLES_CACHE is None:
        _ensure_root_on_path()
        from workflows.proforma_v1 import pipeline_registry
        _ROLES_CACHE = tuple(pipeline_registry.ROLES)
    return _ROLES_CACHE


def _registry():
    _ensure_root_on_path()
    from workflows.proforma_v1 import pipeline_registry
    return pipeline_registry


def version() -> str:
    try:
        value = VERSION_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return "unknown"
    return value or "unknown"


def modes() -> list[str]:
    try:
        doc = json.loads(WORKFLOW_JSON.read_text(encoding="utf-8"))
        value = doc.get("supported_modes")
    except (OSError, json.JSONDecodeError, TypeError):
        return ["ngs-report"]
    if not isinstance(value, list) or not value:
        return ["ngs-report"]
    return [str(item) for item in value if isinstance(item, str) and item]


def pipeline_path(name: str) -> Path:
    name = str(name or "").strip()
    if not RUN_ID_RE.fullmatch(name):
        raise UIError(
            "profile names may use only letters, numbers, '.', '_' and '-', "
            "and must start with a letter or number"
        )
    return PIPELINE_DIR / f"{name}.yaml"


def read_pipeline(name: str) -> dict[str, Any]:
    import yaml
    path = pipeline_path(name)
    if not path.is_file():
        raise UIError(f"no such profile: {name}", 404)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise UIError(f"profile {name} is not a YAML mapping")
    return doc


def list_pipelines() -> list[dict[str, Any]]:
    import yaml
    rows: list[dict[str, Any]] = []
    if not PIPELINE_DIR.is_dir():
        return rows
    for path in sorted(PIPELINE_DIR.glob("*.yaml")):
        name = path.stem
        if name in HIDDEN_PIPELINES:
            continue
        try:
            doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
            if not isinstance(doc, dict):
                raise ValueError("profile is not a YAML mapping")
            meta = doc.get("pipeline") or {}
            provider = doc.get("provider") or {}
            rows.append({
                "name": name,
                "description": str(meta.get("description") or ""),
                "api_key_env": str(provider.get("api_key_env") or ""),
                "api_key_required": bool(provider.get("api_key_required")),
                "base_url": str(provider.get("base_url") or ""),
                "shipped": name in SHIPPED_PIPELINES,
                "readable": True,
            })
        except Exception as exc:
            rows.append({
                "name": name,
                "description": f"unreadable: {exc}",
                "api_key_env": "",
                "api_key_required": False,
                "base_url": "",
                "shipped": name in SHIPPED_PIPELINES,
                "readable": False,
            })
    return rows


def default_pipeline() -> tuple[str, str]:
    """Return (name, note). Falls back off a hidden or missing configured default."""
    configured = ""
    try:
        doc = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        configured = str(doc.get("pipeline") or "")
    except (OSError, json.JSONDecodeError, TypeError, AttributeError):
        configured = ""
    visible = [row["name"] for row in list_pipelines() if row["readable"]]
    if configured and configured in visible:
        return configured, ""
    if not visible:
        return "", "no usable profile found in config/pipelines"
    if configured:
        return visible[0], (
            f"config/settings.json selects {configured!r}, which this interface "
            f"cannot drive; showing {visible[0]!r} instead"
        )
    return visible[0], "config/settings.json names no pipeline"


def _bundled():
    _ensure_root_on_path()
    from validation.scripts import bundled_cases
    return bundled_cases


def validation_cases() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    try:
        bundled = _bundled()
        supported = set(modes())
        for mode in sorted(bundled.validation_modes()):
            if mode not in supported:
                continue
            try:
                out[mode] = list(bundled.list_case_ids(mode))
            except Exception:
                out[mode] = []
    except Exception:
        return {}
    return out


def demo_examples() -> list[int]:
    try:
        bundled = _bundled()
        if "nel-demo" not in set(modes()):
            return []
        values = []
        for case_id in bundled.list_case_ids("nel-demo"):
            try:
                values.append(int(case_id))
            except (TypeError, ValueError):
                continue
        return values
    except Exception:
        return []


def cul_profiles() -> list[str]:
    if not CUL_DIR.is_dir():
        return []
    names = sorted(path.stem for path in CUL_DIR.glob("*.json")
                   if path.stem not in {"settings"})
    if "default" in names:
        names.remove("default")
        names.insert(0, "default")
    return names


def env_status() -> dict[str, bool]:
    out: dict[str, bool] = {}
    for row in list_pipelines():
        name = row.get("api_key_env") or ""
        if name:
            out[name] = bool(os.environ.get(name, "").strip() or SECRETS.get(name, "").strip())
    return out


# --------------------------------------------------------------------------
# secrets
# --------------------------------------------------------------------------

SECRETS: dict[str, str] = {}


def child_env() -> dict[str, str]:
    env = dict(os.environ)
    env.update({k: v for k, v in SECRETS.items() if v})
    env["PYTHONUNBUFFERED"] = "1"
    return env


# --------------------------------------------------------------------------
# identifiers and path containment
# --------------------------------------------------------------------------

def slug(value: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value or "").strip()).strip("-._")
    return value or "run"


def generated_run_id(label: str) -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{slug(label)}"


def check_run_id(value: Any) -> str:
    value = str(value or "").strip()
    if not value:
        raise UIError("a run identifier is required")
    if value in {".", "..", "LATEST"}:
        raise UIError(f"reserved run identifier: {value}")
    if not RUN_ID_RE.fullmatch(value):
        raise UIError(
            "run identifiers may use only letters, numbers, '.', '_' and '-', "
            "and must start with a letter or number"
        )
    return value


def run_dir(run_id: str) -> Path:
    return RUNS_DIR / check_run_id(run_id)


def console_path(run_id: str) -> Path:
    CONSOLE_DIR.mkdir(parents=True, exist_ok=True)
    return CONSOLE_DIR / f"{check_run_id(run_id)}.log"


def case_path(run_id: str) -> Path:
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    return CASE_DIR / f"{check_run_id(run_id)}.md"


def safe_child(base: Path, relative: str) -> Path:
    base = Path(base).resolve()
    candidate = (base / str(relative or "")).resolve()
    if candidate != base and base not in candidate.parents:
        raise UIError("path is outside the run directory", 403)
    return candidate


def sweep_case_files() -> int:
    """Remove case files left behind by an interrupted server."""
    if not CASE_DIR.is_dir():
        return 0
    removed = 0
    for path in CASE_DIR.glob("*.md"):
        try:
            path.unlink()
            removed += 1
        except OSError:
            pass
    return removed


# --------------------------------------------------------------------------
# child process registry
# --------------------------------------------------------------------------

class _Child:
    def __init__(self, proc, run_id: str, phase: str, exclusive: bool, cleanup):
        self.proc = proc
        self.run_id = run_id
        self.phase = phase
        self.exclusive = exclusive
        self.cleanup = list(cleanup or [])
        self.returncode: int | None = None
        self.started_at = time.time()

    @property
    def active(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def snapshot(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "phase": self.phase,
            "exclusive": self.exclusive,
            "active": self.active,
            "returncode": None if self.active else self.returncode,
            "started_at": self.started_at,
        }


class Registry:
    """Concurrent runs, with local providers serialised.

    A run whose provider resolves to a loopback address (LM Studio) is
    exclusive: nothing else may run beside it, in either direction. Remote runs
    are capped. Setup is exempt from the cap because it never calls a model, but
    it is not exempt from exclusivity because it runs a configuration check.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._children: dict[str, _Child] = {}

    def _active(self) -> list[_Child]:
        return [c for c in self._children.values() if c.active]

    def get(self, run_id: str) -> _Child | None:
        return self._children.get(run_id)

    def is_active(self, run_id: str) -> bool:
        child = self._children.get(run_id)
        return bool(child and child.active)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            children = [c.snapshot() for c in self._children.values()]
        active = [c for c in children if c["active"]]
        return {
            "children": children,
            "active_count": len(active),
            "exclusive": any(c["exclusive"] for c in active),
            "remote_limit": REMOTE_RUN_LIMIT,
        }

    def _admit(self, run_id: str, exclusive: bool, phase: str) -> None:
        active = self._active()
        if run_id in {c.run_id for c in active}:
            raise UIError(f"run {run_id} is already active", 409)
        blocker = next((c for c in active if c.exclusive), None)
        if blocker is not None:
            raise UIError(
                f"run {blocker.run_id} uses a local provider and runs alone; "
                "wait for it to finish or stop it",
                409,
            )
        if exclusive and active:
            names = ", ".join(sorted(c.run_id for c in active))
            raise UIError(
                "this profile uses a local provider and must run alone; "
                f"currently active: {names}",
                409,
            )
        if not exclusive and phase == "run":
            remote = [c for c in active if c.phase == "run"]
            if len(remote) >= REMOTE_RUN_LIMIT:
                raise UIError(
                    f"the concurrent run limit of {REMOTE_RUN_LIMIT} is reached; "
                    "wait for one to finish",
                    409,
                )

    def start(self, argv: list[str], *, run_id: str, phase: str,
              exclusive: bool, cleanup=None) -> dict[str, Any]:
        with self._lock:
            self._admit(run_id, exclusive, phase)
            path = console_path(run_id)
            handle = open(path, "ab")
            printable = " ".join(["nel.py", *argv[3:]])
            handle.write(f"\n$ python {printable}\n".encode("utf-8"))
            handle.flush()
            try:
                proc = subprocess.Popen(
                    argv, cwd=str(ROOT), stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT, env=child_env(), bufsize=0,
                )
            except OSError as exc:
                handle.close()
                raise UIError(f"could not start nel.py: {exc}", 500) from exc
            child = _Child(proc, run_id, phase, exclusive, cleanup)
            self._children[run_id] = child
            thread = threading.Thread(
                target=self._pump, args=(child, handle), daemon=True
            )
            thread.start()
            return child.snapshot()

    def _pump(self, child: _Child, handle) -> None:
        try:
            while True:
                chunk = child.proc.stdout.read(1)
                if not chunk:
                    break
                handle.write(chunk)
                handle.flush()
        except (OSError, ValueError):
            pass
        finally:
            code = child.proc.wait()
            child.returncode = code
            try:
                handle.write(
                    f"\n[nel-ui] {child.phase} finished with exit code {code}\n".encode("utf-8")
                )
                handle.flush()
                handle.close()
            except (OSError, ValueError):
                pass
            for path in child.cleanup:
                try:
                    Path(path).unlink()
                except OSError:
                    pass

    def stop(self, run_id: str) -> dict[str, Any]:
        child = self._children.get(run_id)
        if child is None or not child.active:
            return {"stopped": False, "detail": f"run {run_id} is not active"}
        try:
            child.proc.send_signal(signal.SIGTERM)
        except OSError as exc:
            return {"stopped": False, "detail": f"could not signal the process: {exc}"}
        try:
            child.proc.wait(timeout=8)
            return {"stopped": True, "detail": f"run {run_id} stopped; it can be resumed"}
        except subprocess.TimeoutExpired:
            pass
        try:
            child.proc.kill()
            child.proc.wait(timeout=8)
            return {"stopped": True, "detail": f"run {run_id} killed; it can be resumed"}
        except Exception as exc:
            return {"stopped": False, "detail": f"process did not exit: {exc}"}

    def stop_all(self) -> None:
        for run_id in list(self._children):
            try:
                self.stop(run_id)
            except Exception:
                pass


REGISTRY = Registry()


# --------------------------------------------------------------------------
# invoking nel.py
# --------------------------------------------------------------------------

def nel(*args: str, timeout: int = NEL_TIMEOUT):
    argv = [sys.executable, "-u", str(ROOT / "nel.py"), *[str(a) for a in args]]
    try:
        return subprocess.run(
            argv, cwd=str(ROOT), env=child_env(), stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise UIError(
            f"nel.py {' '.join(str(a) for a in args)} did not finish within {timeout}s",
            504,
        ) from exc
    except OSError as exc:
        raise UIError(f"could not run nel.py: {exc}", 500) from exc


def extract_json(text: str) -> Any:
    decoder = json.JSONDecoder()
    for index, char in enumerate(text or ""):
        if char not in "[{":
            continue
        try:
            return decoder.raw_decode(text, index)[0]
        except json.JSONDecodeError:
            continue
    raise UIError("nel.py did not return JSON; see the console pane for its output", 500)


def nel_json(*args: str, timeout: int = NEL_TIMEOUT) -> Any:
    result = nel(*args, timeout=timeout)
    return extract_json(result.stdout)


# --------------------------------------------------------------------------
# provider catalogue
# --------------------------------------------------------------------------

def _get_json(url: str, api_key: str) -> Any:
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    with urllib.request.urlopen(request, timeout=CATALOGUE_TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8", errors="replace"))


def _ids(document: Any) -> list[str]:
    rows = document.get("data") if isinstance(document, dict) else document
    if not isinstance(rows, list):
        return []
    out = set()
    for row in rows:
        if isinstance(row, dict):
            value = row.get("id") or row.get("slug") or row.get("name")
        else:
            value = row
        if isinstance(value, str) and value.strip():
            out.add(value.strip())
    return sorted(out)


def provider_catalogue(base_url: str, api_key: str) -> dict[str, Any]:
    base = str(base_url or "").rstrip("/")
    notes: list[str] = []
    models: list[str] = []
    providers: list[str] = []
    if not base:
        return {"models": [], "providers": [], "notes": ["enter a base URL first"]}
    try:
        models = _ids(_get_json(f"{base}/models", api_key))
        if not models:
            notes.append("the endpoint returned no model list; type the model ID by hand")
    except Exception as exc:
        notes.append(f"could not list models from {base}/models ({exc}); type the model ID by hand")
    if "openrouter" in base.lower():
        try:
            providers = _ids(_get_json(f"{base}/providers", api_key))
        except Exception as exc:
            notes.append(f"could not list providers ({exc}); type provider slugs by hand")
    return {"models": models, "providers": providers, "notes": notes}


# --------------------------------------------------------------------------
# profile composition
# --------------------------------------------------------------------------

def _positive_int(value: Any, fallback: int | None, label: str) -> int:
    text = str(value if value is not None else "").strip()
    if not text:
        if fallback is None:
            raise UIError(f"{label} is required")
        return fallback
    try:
        number = int(float(text))
    except (TypeError, ValueError) as exc:
        raise UIError(f"{label} must be a number; got {text!r}") from exc
    if number <= 0:
        raise UIError(f"{label} must be greater than zero; got {text!r}")
    return number


def _float(value: Any, fallback: float, label: str) -> float:
    text = str(value if value is not None else "").strip()
    if not text:
        return fallback
    try:
        return float(text)
    except (TypeError, ValueError) as exc:
        raise UIError(f"{label} must be a number; got {text!r}") from exc


def _routing(raw: Any) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if not isinstance(raw, dict):
        return out
    for field in ROUTING_LIST_FIELDS:
        items = [part.strip() for part in str(raw.get(field) or "").split(",")]
        items = [part for part in items if part]
        if items:
            out[field] = items
    for field in ROUTING_BOOL_FIELDS:
        value = raw.get(field)
        if isinstance(value, bool):
            out[field] = value
    return out


def compose_pipeline(payload: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    name = str(payload.get("name") or "").strip()
    pipeline_path(name)  # validates the stem
    if name in SHIPPED_PIPELINES:
        raise UIError(
            f"{name} is a profile shipped with the repository and is read-only; "
            "save under a new name"
        )
    provider_in = payload.get("provider") or {}
    base_url = str(provider_in.get("base_url") or "").strip()
    if not base_url:
        raise UIError("a base URL is required, for example http://localhost:1234/v1")

    aliases_in = payload.get("aliases") or []
    if not isinstance(aliases_in, list) or not aliases_in:
        raise UIError("add at least one model option")
    aliases: dict[str, Any] = {}
    for index, row in enumerate(aliases_in, start=1):
        if not isinstance(row, dict):
            raise UIError(f"model option {index} is malformed")
        alias = str(row.get("alias") or "").strip()
        model = str(row.get("model") or "").strip()
        if not alias:
            raise UIError(f"model option {index} needs a name")
        if not model:
            raise UIError(f"model option {alias!r} needs a model ID")
        if alias in aliases:
            raise UIError(f"model option {alias!r} is defined twice")
        routing = _routing(row.get("routing"))
        aliases[alias] = {"model": model, "provider": routing} if routing else model

    roles_in = payload.get("roles") or {}
    if not isinstance(roles_in, dict):
        raise UIError("role assignments are malformed")
    expected = set(roles())
    given = {str(k) for k in roles_in}
    missing = sorted(expected - given)
    extra = sorted(given - expected)
    if missing:
        raise UIError(f"role assignment is missing: {', '.join(missing)}")
    if extra:
        raise UIError(
            f"role assignment names roles this workflow does not have: {', '.join(extra)}"
        )
    model_roles: dict[str, Any] = {}
    for role in roles():
        row = roles_in.get(role) or {}
        if not isinstance(row, dict):
            raise UIError(f"role {role} is malformed")
        alias = str(row.get("model") or "").strip()
        if alias not in aliases:
            raise UIError(f"role {role} names model option {alias!r}, which is not defined")
        model_roles[role] = {
            "model": alias,
            "temperature": _float(row.get("temperature"), 0.0, f"role {role} temperature"),
            "max_tokens": _positive_int(row.get("max_tokens"), None, f"role {role} max_tokens"),
        }

    provider: dict[str, Any] = {
        "type": "openai-compatible",
        "base_url": base_url,
        "timeout_s": _positive_int(provider_in.get("timeout_s"), 900, "timeout"),
        "api_key_required": bool(provider_in.get("api_key_required")),
    }
    base_url_env = str(provider_in.get("base_url_env") or "").strip()
    if base_url_env:
        provider["base_url_env"] = base_url_env
    api_key_env = str(provider_in.get("api_key_env") or "").strip()
    if api_key_env:
        provider["api_key_env"] = api_key_env
    if provider["api_key_required"] and not api_key_env:
        raise UIError("a profile that requires an API key must name the environment variable")

    doc = {
        "pipeline": {
            "version": 1,
            "description": str(payload.get("description") or "").strip()
                           or f"Proforma-v1 profile {name}.",
        },
        "provider": provider,
        "model_aliases": aliases,
        "model_roles": model_roles,
    }
    return name, doc


def validate_pipeline(doc: dict[str, Any]) -> None:
    import tempfile
    import yaml
    registry = _registry()
    handle = tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False, encoding="utf-8")
    try:
        yaml.safe_dump(doc, handle, sort_keys=False, allow_unicode=True)
        handle.close()
        registry.load_yaml(Path(handle.name))
    except Exception as exc:
        raise UIError(f"the profile would be rejected by nel.py: {exc}") from exc
    finally:
        try:
            os.unlink(handle.name)
        except OSError:
            pass


HEADER = (
    "# Written by the NEL browser interface.\n"
    "# model_aliases names the model options; model_roles assigns one option to\n"
    "# each proforma-v1 role. Never store an API key in this file: the key is read\n"
    "# from the environment variable named by provider.api_key_env.\n"
)


def save_pipeline(name: str, doc: dict[str, Any], overwrite: bool = False) -> Path:
    import yaml
    validate_pipeline(doc)
    path = pipeline_path(name)
    if name in SHIPPED_PIPELINES:
        raise UIError(f"{name} is shipped with the repository and is read-only", 403)
    if path.exists() and not overwrite:
        raise UIError(
            f"a profile named {name} already exists; choose a new name or confirm the overwrite",
            409,
        )
    PIPELINE_DIR.mkdir(parents=True, exist_ok=True)
    body = yaml.safe_dump(doc, sort_keys=False, allow_unicode=True)
    path.write_text(HEADER + body, encoding="utf-8")
    return path


# --------------------------------------------------------------------------
# provider locality
# --------------------------------------------------------------------------

def resolved_base_url(name: str) -> str:
    doc = read_pipeline(name)
    provider = doc.get("provider") or {}
    env_name = str(provider.get("base_url_env") or "")
    if env_name:
        override = SECRETS.get(env_name) or os.environ.get(env_name) or ""
        if override.strip():
            return override.strip()
    return str(provider.get("base_url") or "")


def is_local_pipeline(name: str) -> bool:
    """A profile pointing at loopback runs alone: one local model, one caller."""
    try:
        host = (urlparse(resolved_base_url(name)).hostname or "").lower()
    except Exception:
        return False
    return host in LOCAL_HOSTS


# --------------------------------------------------------------------------
# actions
# --------------------------------------------------------------------------

def action_setup(payload: dict[str, Any]) -> dict[str, Any]:
    pipeline = str(payload.get("pipeline") or "").strip()
    if not pipeline:
        raise UIError("choose a provider profile before preparing a run")
    if pipeline in HIDDEN_PIPELINES:
        raise UIError(
            f"the {pipeline!r} profile hands each step to a session model and cannot be "
            "driven from this interface; choose a provider profile"
        )
    if pipeline not in {row["name"] for row in list_pipelines() if row["readable"]}:
        raise UIError(f"no usable profile named {pipeline}", 404)

    mode = str(payload.get("mode") or "").strip()
    if mode not in set(modes()):
        raise UIError(f"unsupported mode {mode!r}; choose one of: {', '.join(modes())}")

    label = mode
    args: list[str] = []
    case_text = ""
    if mode == "ngs-report":
        case_text = str(payload.get("case_text") or "")
        if not case_text.strip():
            raise UIError("paste the clinical case before preparing a run")
        label = "case"
    elif mode == "nel-demo":
        example = payload.get("example")
        if example in (None, ""):
            raise UIError("choose a demo example before preparing a run")
        args += ["--example", str(int(example))]
        label = f"demo-{int(example)}"
    else:
        case_id = str(payload.get("case_id") or "").strip()
        if not case_id:
            raise UIError("choose a validation case before preparing a run")
        args += ["--case-id", case_id]
        label = f"{mode.removeprefix('nel-')}-{case_id}"

    cul = str(payload.get("cul") or "").strip()
    if cul:
        args += ["--cul", cul]

    supplied = str(payload.get("run_id") or "").strip()
    run_id = check_run_id(supplied) if supplied else generated_run_id(label)
    if run_dir(run_id).exists():
        raise UIError(f"a run named {run_id} already exists; choose another identifier", 409)

    cleanup: list[Path] = []
    if mode == "ngs-report":
        path = case_path(run_id)
        text = case_text if case_text.endswith("\n") else case_text + "\n"
        path.write_text(text, encoding="utf-8")
        args += ["--case", str(path)]
        cleanup.append(path)

    argv = [
        sys.executable, "-u", str(ROOT / "nel.py"), "setup",
        "--mode", mode, "--pipeline", pipeline, "--run-id", run_id, *args,
    ]
    try:
        return REGISTRY.start(
            argv, run_id=run_id, phase="setup",
            exclusive=is_local_pipeline(pipeline), cleanup=cleanup,
        )
    except UIError:
        for path in cleanup:
            try:
                path.unlink()
            except OSError:
                pass
        raise


def action_run(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = check_run_id(payload.get("run_id"))
    path = run_dir(run_id)
    if not path.is_dir():
        raise UIError(f"run not found: {run_id}", 404)
    if (path / ARCHIVE_MARKER).is_file():
        raise UIError(f"run {run_id} is archived; its working files were removed", 409)
    manifest = run_manifest(run_id)
    pipeline = str(manifest.get("pipeline") or "")
    exclusive = bool(pipeline) and is_local_pipeline_safe(pipeline)
    argv = [sys.executable, "-u", str(ROOT / "nel.py"), "run", "--run-id", run_id]
    return REGISTRY.start(argv, run_id=run_id, phase="run", exclusive=exclusive)


def is_local_pipeline_safe(name: str) -> bool:
    try:
        return is_local_pipeline(name)
    except UIError:
        # The profile may have been renamed since setup. The run itself uses its
        # frozen copy; assume exclusive, which is the conservative choice.
        return True


def _clear_latest_if(run_id: str) -> None:
    try:
        current = LATEST_PATH.read_text(encoding="utf-8").strip()
    except OSError:
        return
    if current == run_id:
        try:
            LATEST_PATH.unlink()
        except OSError:
            pass


def action_delete(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = check_run_id(payload.get("run_id"))
    if REGISTRY.is_active(run_id):
        raise UIError(f"run {run_id} is active; stop it before deleting", 409)
    path = run_dir(run_id)
    if not path.is_dir():
        raise UIError(f"run not found: {run_id}", 404)
    shutil.rmtree(path)
    for extra in (console_path(run_id), case_path(run_id)):
        try:
            extra.unlink()
        except OSError:
            pass
    _clear_latest_if(run_id)
    return {"deleted": run_id}


ARCHIVE_TARGETS = ("case.md", "intermediates", "model_steps")


def action_archive(payload: dict[str, Any]) -> dict[str, Any]:
    run_id = check_run_id(payload.get("run_id"))
    if REGISTRY.is_active(run_id):
        raise UIError(f"run {run_id} is active; stop it before archiving", 409)
    path = run_dir(run_id)
    if not path.is_dir():
        raise UIError(f"run not found: {run_id}", 404)
    if (path / ARCHIVE_MARKER).is_file():
        raise UIError(f"run {run_id} is already archived", 409)
    removed: list[str] = []
    for name in ARCHIVE_TARGETS:
        target = path / name
        if target.is_dir():
            shutil.rmtree(target)
            removed.append(name)
        elif target.is_file():
            target.unlink()
            removed.append(name)
    marker = {
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "removed": removed,
        "retained": "report-final.md, report-final.json, logs/, run-config/",
        "note": "Working files were removed. The report restates clinical findings.",
    }
    (path / ARCHIVE_MARKER).write_text(
        json.dumps(marker, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    try:
        case_path(run_id).unlink()
    except OSError:
        pass
    return {"archived": run_id, "removed": removed}


# --------------------------------------------------------------------------
# read helpers
# --------------------------------------------------------------------------

def read_console(run_id: str, offset: int) -> dict[str, Any]:
    path = console_path(run_id)
    if not path.is_file():
        return {"offset": 0, "text": "", "size": 0}
    size = path.stat().st_size
    start = 0 if offset > size or offset < 0 else offset
    with open(path, "rb") as handle:
        handle.seek(start)
        data = handle.read()
    return {
        "offset": start + len(data),
        "text": data.decode("utf-8", errors="replace"),
        "size": size,
    }


def run_files(run_id: str) -> list[dict[str, Any]]:
    base = run_dir(run_id)
    if not base.is_dir():
        raise UIError(f"run not found: {run_id}", 404)
    rows = []
    for path in sorted(base.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts:
            continue
        rows.append({
            "path": path.relative_to(base).as_posix(),
            "size": path.stat().st_size,
        })
    return rows


def read_run_file(run_id: str, relative: str, *, offset: int = 0, limit: int = MAX_FILE_BYTES) -> dict[str, Any]:
    base = run_dir(run_id)
    path = safe_child(base, relative)
    if not path.is_file():
        raise UIError(f"no such file in this run: {relative}", 404)
    size = path.stat().st_size
    offset = max(0, min(int(offset), size))
    limit = max(1, min(int(limit), MAX_FILE_BYTES))
    with open(path, "rb") as handle:
        handle.seek(offset)
        data = handle.read(limit)
    next_offset = offset + len(data)
    return {
        "path": relative,
        "size": size,
        "offset": offset,
        "next_offset": next_offset,
        "truncated": next_offset < size,
        "text": data.decode("utf-8", errors="replace"),
        "data_base64": base64.b64encode(data).decode("ascii"),
    }


def report(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "report-final.md"
    if not path.is_file():
        return {"exists": False, "text": ""}
    return {"exists": True, "text": path.read_text(encoding="utf-8", errors="replace")}


def run_manifest(run_id: str) -> dict[str, Any]:
    path = run_dir(run_id) / "run-config" / "manifest.json"
    if not path.is_file():
        return {}
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return doc if isinstance(doc, dict) else {}


def is_archived(run_id: str) -> bool:
    return (run_dir(run_id) / ARCHIVE_MARKER).is_file()


def usage(run_id: str) -> dict[str, Any]:
    _ensure_root_on_path()
    from scripts import model_usage
    path = run_dir(run_id) / "logs" / "model-usage.json"
    summary = model_usage.summarize(path)
    if summary is None:
        return {"available": False, "summary": None}
    return {"available": True, "summary": summary}


def bootstrap() -> dict[str, Any]:
    name, note = default_pipeline()
    return {
        "version": version(),
        "root": str(ROOT),
        "workflow": WORKFLOW_ID,
        "pipelines": list_pipelines(),
        "shipped": sorted(SHIPPED_PIPELINES),
        "default_pipeline": name,
        "default_pipeline_note": note,
        "examples": demo_examples(),
        "validation": validation_cases(),
        "modes": modes(),
        "roles": list(roles()),
        "cul_profiles": cul_profiles(),
        "stages": [{"key": key, "label": label} for key, label in STAGES],
        "keys": env_status(),
        "runner": REGISTRY.snapshot(),
    }


def runs_list() -> list[dict[str, Any]]:
    result = nel("runs", "--json")
    rows = extract_json(result.stdout)
    if not isinstance(rows, list):
        return []
    for row in rows:
        if isinstance(row, dict) and row.get("run_id"):
            try:
                row["archived"] = is_archived(str(row["run_id"]))
            except UIError:
                row["archived"] = False
    return rows


def status(run_id: str) -> dict[str, Any]:
    run_id = check_run_id(run_id)
    result = nel("status", "--run-id", run_id, "--json")
    if result.returncode != 0:
        return {"available": False, "detail": (result.stdout or "").strip()[-800:]}
    try:
        doc = extract_json(result.stdout)
    except UIError as exc:
        return {"available": False, "detail": exc.message}
    return {
        "available": True,
        "status": doc,
        "manifest": run_manifest(run_id),
        "archived": is_archived(run_id),
    }


def config_check(pipeline: str, cul: str = "") -> dict[str, Any]:
    args = ["config-check", "--json"]
    if pipeline:
        args += ["--pipeline", pipeline]
    if cul:
        args += ["--cul", cul]
    result = nel(*args)
    try:
        doc = extract_json(result.stdout)
    except UIError:
        return {"ok": False, "errors": [(result.stdout or "").strip()[-1200:]], "warnings": []}
    if not isinstance(doc, dict):
        return {"ok": False, "errors": ["unexpected output from config-check"], "warnings": []}
    doc.pop("cul_layer", None)
    return doc


# --------------------------------------------------------------------------
# HTTP layer
# --------------------------------------------------------------------------

class Handler(BaseHTTPRequestHandler):
    server_version = "nel-ui"
    token = ""

    def log_message(self, *args):  # noqa: D102 - silence the terminal
        return

    # -- helpers ----------------------------------------------------------
    def _headers(self, status_code: int, content_type: str, length: int) -> None:
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(length))
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def _send(self, status_code: int, content_type: str, body: bytes) -> None:
        self._headers(status_code, content_type, len(body))
        if self.command != "HEAD":
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def _json(self, payload: Any, status_code: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self._send(status_code, "application/json; charset=utf-8", body)

    def _text(self, text: str, status_code: int = 200) -> None:
        self._send(status_code, "text/plain; charset=utf-8", text.encode("utf-8"))

    def _query(self) -> dict[str, list[str]]:
        return parse_qs(urlparse(self.path).query)

    def _param(self, name: str, default: str = "") -> str:
        values = self._query().get(name) or []
        return values[0] if values else default

    def _body(self) -> dict[str, Any]:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            raise UIError("malformed Content-Length")
        if length > MAX_BODY_BYTES:
            raise UIError("request body is too large", 413)
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        try:
            doc = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise UIError("request body is not valid JSON") from exc
        if not isinstance(doc, dict):
            raise UIError("request body must be a JSON object")
        return doc

    def _authorised_api(self) -> bool:
        supplied = self.headers.get("X-NEL-Token") or ""
        return secrets.compare_digest(supplied, Handler.token)

    # -- routing ----------------------------------------------------------
    def do_HEAD(self):  # noqa: N802
        self.do_GET()

    def do_GET(self):  # noqa: N802
        path = urlparse(self.path).path
        if path in {"/", "/index.html"}:
            return self._serve_page()
        if path.startswith("/assets/"):
            return self._serve_asset(path[len("/assets/"):])
        if path.startswith("/api/"):
            if not self._authorised_api():
                return self._json({"error": "missing or invalid session token"}, 403)
            return self._dispatch(path, "GET")
        return self._text("not found\n", 404)

    def do_POST(self):  # noqa: N802
        path = urlparse(self.path).path
        if not path.startswith("/api/"):
            return self._text("not found\n", 404)
        if not self._authorised_api():
            return self._json({"error": "missing or invalid session token"}, 403)
        return self._dispatch(path, "POST")

    def _serve_page(self) -> None:
        if not secrets.compare_digest(self._param("t"), Handler.token):
            return self._text(
                "This page needs the session address printed in the terminal that "
                "started nel.py ui. Copy that address into the browser.\n",
                403,
            )
        source = UI_DIR / "index.html"
        try:
            text = source.read_text(encoding="utf-8")
        except OSError:
            return self._text("ui/index.html is missing\n", 500)
        body = text.replace("__NEL_TOKEN__", Handler.token).encode("utf-8")
        self._send(200, "text/html; charset=utf-8", body)

    def _serve_asset(self, name: str) -> None:
        if not name or "/" in name or "\\" in name or name in {".", ".."}:
            return self._text("not found\n", 404)
        path = ASSET_DIR / name
        if not path.is_file():
            return self._text("not found\n", 404)
        kind = "application/javascript" if name.endswith(".js") else "text/plain; charset=utf-8"
        self._send(200, kind, path.read_bytes())

    def _dispatch(self, path: str, method: str) -> None:
        try:
            payload = self._handle(path, method)
        except UIError as exc:
            return self._json({"error": exc.message}, exc.status)
        except Exception as exc:  # noqa: BLE001 - no tracebacks reach the browser
            return self._json({"error": f"{type(exc).__name__}: {exc}"}, 500)
        self._json(payload)

    def _handle(self, path: str, method: str) -> Any:
        if method == "GET":
            if path == "/api/bootstrap":
                return bootstrap()
            if path == "/api/runs":
                return {"runs": runs_list()}
            if path == "/api/status":
                return status(self._param("run"))
            if path == "/api/console":
                try:
                    offset = int(self._param("offset", "0"))
                except ValueError:
                    offset = 0
                return read_console(check_run_id(self._param("run")), offset)
            if path == "/api/usage":
                return usage(check_run_id(self._param("run")))
            if path == "/api/report":
                return report(check_run_id(self._param("run")))
            if path == "/api/files":
                return {"files": run_files(check_run_id(self._param("run")))}
            if path == "/api/file":
                try:
                    offset = int(self._param("offset", "0"))
                    limit = int(self._param("limit", str(MAX_FILE_BYTES)))
                except ValueError as exc:
                    raise UIError("file offset and limit must be integers") from exc
                return read_run_file(
                    check_run_id(self._param("run")), self._param("path"),
                    offset=offset, limit=limit,
                )
            if path == "/api/pipelines":
                name, note = default_pipeline()
                return {
                    "pipelines": list_pipelines(),
                    "default_pipeline": name,
                    "default_pipeline_note": note,
                }
            if path == "/api/pipeline":
                name = str(self._param("name") or "")
                return {"name": name, "doc": read_pipeline(name), "roles": list(roles())}
            if path == "/api/config-check":
                return config_check(self._param("pipeline"), self._param("cul"))
            if path == "/api/runner":
                return REGISTRY.snapshot()
            raise UIError("no such endpoint", 404)

        body = self._body()
        if path == "/api/key":
            env = str(body.get("env") or "").strip()
            if not env:
                raise UIError("name the environment variable the key belongs to")
            value = str(body.get("value") or "").strip()
            if value:
                SECRETS[env] = value
            else:
                SECRETS.pop(env, None)
            return {"keys": env_status()}
        if path == "/api/pipeline":
            name, doc = compose_pipeline(body)
            saved = save_pipeline(name, doc, overwrite=bool(body.get("overwrite")))
            return {"name": name, "path": str(saved), "pipelines": list_pipelines()}
        if path == "/api/provider-models":
            key = str(body.get("api_key") or "").strip()
            if not key:
                key = SECRETS.get(str(body.get("api_key_env") or ""), "")
            return provider_catalogue(str(body.get("base_url") or ""), key)
        if path == "/api/setup":
            return action_setup(body)
        if path == "/api/run":
            return action_run(body)
        if path == "/api/stop":
            return REGISTRY.stop(check_run_id(body.get("run_id")))
        if path == "/api/delete":
            return action_delete(body)
        if path == "/api/archive":
            return action_archive(body)
        raise UIError("no such endpoint", 404)


# --------------------------------------------------------------------------
# startup
# --------------------------------------------------------------------------

def serve(port: int = 8765, open_browser: bool = True) -> int:
    if not (UI_DIR / "index.html").is_file():
        print(f"ui/index.html is missing: {UI_DIR / 'index.html'}", file=sys.stderr)
        return 1
    CONSOLE_DIR.mkdir(parents=True, exist_ok=True)
    CASE_DIR.mkdir(parents=True, exist_ok=True)
    swept = sweep_case_files()
    Handler.token = secrets.token_urlsafe(24)

    httpd = None
    last_error: Exception | None = None
    for candidate in range(port, port + 20):
        try:
            httpd = ThreadingHTTPServer((BIND_HOST, candidate), Handler)
            break
        except OSError as exc:
            last_error = exc
    if httpd is None:
        raise SystemExit(f"no free port in {port}-{port + 19}: {last_error}")

    bound = httpd.server_address[1]
    url = f"http://{BIND_HOST}:{bound}/?t={Handler.token}"
    if swept:
        print(f"[nel-ui] removed {swept} orphaned case file(s) from .nel-ui/cases")
    print(f"[nel-ui] {url}")
    print("[nel-ui] this machine only; the address carries a one-time session token")
    print("[nel-ui] press Ctrl-C to stop")

    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n[nel-ui] stopping active runs")
        REGISTRY.stop_all()
    finally:
        httpd.server_close()
    return 0


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="Serve the local NEL browser interface.")
    parser.add_argument("--port", type=int, default=8765, help="first port to try")
    parser.add_argument("--no-browser", action="store_true", help="do not open a browser window")
    args = parser.parse_args(argv)
    return serve(port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    raise SystemExit(main())
