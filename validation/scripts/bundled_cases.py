"""Compatibility facade for bundled demo cases and dynamic validation suites.

Validation suites are discovered exclusively by :mod:`validation.case_registry`.
This module retains the historical public helper API so workflow/UI callers do not
need suite-specific code. The demo suite remains a separate non-validation asset.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from validation import case_registry

VALIDATION_ROOT = Path(__file__).resolve().parents[1]
_DEMO_MODE = "nel-demo"
_DEMO_SOURCE = "demo.md"
_CASE_ID_RE = re.compile(r"(\d+)([A-Z]?)")


@dataclass(frozen=True)
class SuiteSpec:
    mode: str
    source: str
    marking_prefix: str | None
    selector_flag: str

    @property
    def source_path(self) -> Path:
        return VALIDATION_ROOT / self.source


def validation_modes() -> frozenset[str]:
    return case_registry.validation_modes()


def bundled_modes() -> tuple[str, ...]:
    return (_DEMO_MODE, *sorted(validation_modes()))


def is_validation_mode(mode: str) -> bool:
    return case_registry.is_validation_mode(mode)


def is_bundled_mode(mode: str) -> bool:
    return mode == _DEMO_MODE or is_validation_mode(mode)


def suite_spec(mode: str) -> SuiteSpec:
    if mode == _DEMO_MODE:
        return SuiteSpec(_DEMO_MODE, _DEMO_SOURCE, None, "--example")
    suite = case_registry.suite_spec(mode)
    return SuiteSpec(mode, suite.path.name, f"nel-validation{mode.removeprefix('nel-validate')}", "--case-id")


def case_source_path(mode: str) -> Path:
    if is_validation_mode(mode):
        return case_registry.case_source_path(mode)
    if mode != _DEMO_MODE:
        raise ValueError(f"Unsupported bundled case mode: {mode!r}")
    path = VALIDATION_ROOT / _DEMO_SOURCE
    if not path.is_file():
        raise FileNotFoundError(f"Bundled case source is missing for {mode}: {path}")
    return path


def normalise_selector(mode: str, selector: str | int) -> str:
    if is_validation_mode(mode):
        return case_registry.normalise_selector(mode, selector)
    if mode != _DEMO_MODE:
        raise ValueError(f"Unsupported bundled case mode: {mode!r}")
    case_id = str(selector).strip().upper()
    match = _CASE_ID_RE.fullmatch(case_id)
    if not match or match.group(2):
        raise ValueError("nel-demo selectors must be integer case numbers")
    if case_id not in list_case_ids(_DEMO_MODE):
        raise KeyError(f"demo case {case_id!r} not found")
    return case_id


def selector_from_args(mode: str, *, example: int | None = None, case_id: str | None = None) -> str | None:
    if mode == _DEMO_MODE:
        return None if example is None else normalise_selector(mode, example)
    if is_validation_mode(mode):
        return None if case_id is None else normalise_selector(mode, case_id)
    return None


def _demo_text() -> str:
    return case_source_path(_DEMO_MODE).read_text(encoding="utf-8")


def _demo_case_block(selector: str | int) -> tuple[str, str]:
    case_id = str(selector).strip()
    text = _demo_text()
    match = re.search(
        rf"^# Case {re.escape(case_id)}\b.*?$(.*?)(?=^# Case \d+\b|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise KeyError(f"demo case {case_id!r} not found")
    return case_id, match.group(1)


def retrieve_case_input(mode: str, selector: str | int) -> str:
    if is_validation_mode(mode):
        return case_registry.retrieve_case_input(mode, selector)
    if mode != _DEMO_MODE:
        raise ValueError(f"Unsupported bundled case mode: {mode!r}")
    case_id, block = _demo_case_block(selector)
    match = re.search(
        r"^## Clinical information\s*\n(.*?)(?=^## NEL task\s*$)",
        block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"demo case {case_id} lacks canonical clinical information")
    return match.group(1).strip()


def retrieve_marking_criteria(mode: str, selector: str | int) -> str:
    if is_validation_mode(mode):
        return case_registry.retrieve_marking_criteria(mode, selector)
    if mode != _DEMO_MODE:
        raise ValueError(f"Unsupported bundled case mode: {mode!r}")
    case_id, block = _demo_case_block(selector)
    match = re.search(
        r"^## Marking criteria\s*\n(.*?)(?=^---\s*$|^# Case \d+\b|\Z)",
        block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise KeyError(f"marking criteria for demo case {case_id} not found")
    return match.group(1).strip()


def list_case_ids(mode: str) -> tuple[str, ...]:
    if is_validation_mode(mode):
        return case_registry.list_case_ids(mode)
    if mode != _DEMO_MODE:
        raise ValueError(f"Unsupported bundled case mode: {mode!r}")
    return tuple(re.findall(r"^# Case (\d+)\b", _demo_text(), flags=re.MULTILINE))


def marking_bundle_filename(mode: str, selector: str | int) -> str:
    if not is_validation_mode(mode):
        raise ValueError(f"{mode} does not use an external marking ZIP")
    return case_registry.marking_bundle_filename(mode, selector)


def write_demo_marking_criteria_after_report(
    selector: str | int,
    *,
    report_path: Path,
    output_path: Path,
) -> Path:
    report_path = Path(report_path)
    if not report_path.is_file() or not report_path.read_text(encoding="utf-8").strip():
        raise ValueError("demo marking criteria may be materialised only after a non-empty report-final.md exists")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(retrieve_marking_criteria(_DEMO_MODE, selector).rstrip() + "\n", encoding="utf-8")
    return output_path
