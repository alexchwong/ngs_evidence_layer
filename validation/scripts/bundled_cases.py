"""Single source of truth for repository-bundled demo and validation cases.

Workflow code must resolve bundled clinical inputs through :func:`retrieve_case_input`
and must not hard-code validation markdown filenames. Marking criteria are exposed
through a separate API so setup/report-generation paths do not need to read them.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

VALIDATION_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class SuiteSpec:
    mode: str
    source: str
    marking_prefix: str | None
    selector_flag: str

    @property
    def source_path(self) -> Path:
        return VALIDATION_ROOT / self.source


_SUITES: dict[str, SuiteSpec] = {
    "nel-demo": SuiteSpec("nel-demo", "demo.md", None, "--example"),
    "nel-validate": SuiteSpec("nel-validate", "case_summary.md", "nel-validation", "--case-id"),
    "nel-validate-function": SuiteSpec(
        "nel-validate-function", "case_functional.md", "nel-validation-function", "--case-id"
    ),
    "nel-validate-brief": SuiteSpec(
        "nel-validate-brief", "validation_brief.md", "nel-validation-brief", "--case-id"
    ),
    "nel-validate-dual": SuiteSpec(
        "nel-validate-dual", "validate_dual.md", "nel-validation-dual", "--case-id"
    ),
    "nel-validate-dublin": SuiteSpec(
        "nel-validate-dublin", "validation_dublin.md", "nel-validation-dublin", "--case-id"
    ),
}
_CASE_ID_RE = re.compile(r"(\d+)([A-Z]?)")


def bundled_modes() -> tuple[str, ...]:
    return tuple(_SUITES)


def validation_modes() -> frozenset[str]:
    return frozenset(mode for mode in _SUITES if mode.startswith("nel-validate"))


def is_bundled_mode(mode: str) -> bool:
    return mode in _SUITES


def is_validation_mode(mode: str) -> bool:
    return mode in validation_modes()


def suite_spec(mode: str) -> SuiteSpec:
    try:
        return _SUITES[mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported bundled case mode: {mode!r}") from exc


def case_source_path(mode: str) -> Path:
    path = suite_spec(mode).source_path
    if not path.is_file():
        raise FileNotFoundError(f"Bundled case source is missing for {mode}: {path}")
    return path


def normalise_selector(mode: str, selector: str | int) -> str:
    spec = suite_spec(mode)
    case_id = str(selector).strip().upper()
    match = _CASE_ID_RE.fullmatch(case_id)
    if not match:
        raise ValueError(f"Invalid selector for {mode}: {selector!r}")
    if mode == "nel-demo" and match.group(2):
        raise ValueError("nel-demo selectors must be integer case numbers")
    return case_id


def selector_from_args(mode: str, *, example: int | None = None, case_id: str | None = None) -> str | None:
    if mode == "nel-demo":
        if example is None:
            return None
        return normalise_selector(mode, example)
    if is_validation_mode(mode):
        if case_id is None:
            return None
        return normalise_selector(mode, case_id)
    return None


def _read_mode_text(mode: str) -> str:
    return case_source_path(mode).read_text(encoding="utf-8")


def _case_parts(mode: str, selector: str | int) -> tuple[str, str, str]:
    case_id = normalise_selector(mode, selector)
    match = _CASE_ID_RE.fullmatch(case_id)
    assert match is not None
    return case_id, match.group(1), match.group(2)


def retrieve_case_input(mode: str, selector: str | int) -> str:
    """Return clinical information only for one bundled case.

    Supports both standalone cases and the legacy shared-stem + variant format.
    `NEL task` and `Marking criteria` content are never returned.
    """
    case_id, case_number, variant = _case_parts(mode, selector)
    text = _read_mode_text(mode)
    case_block_match = re.search(
        rf"^# Case {re.escape(case_number)}\b.*?$(.*?)(?=^# Case \d+\b|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not case_block_match:
        raise KeyError(f"Case {case_number} not found in {suite_spec(mode).source}")
    case_block = case_block_match.group(1)

    standalone_match = re.search(
        r"^## Clinical information\s*\n(.*?)(?=^## NEL task\s*$)",
        case_block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if standalone_match:
        if variant:
            raise KeyError(f"Case {case_number} is standalone and has no variant {variant}")
        return standalone_match.group(1).strip()

    stem_match = re.search(
        r"^## Shared stem\s*\n(.*?)(?=^## Case \d+[A-Z]\b|\Z)",
        case_block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not stem_match:
        raise ValueError(f"Case {case_number} has neither standalone clinical information nor a shared stem")
    stem = stem_match.group(1).strip()
    if not variant:
        return stem

    variant_match = re.search(
        rf"^## Case {re.escape(case_id)}\b.*?^### Clinical information\s*\n"
        rf"(.*?)(?=^### NEL task\s*$)",
        case_block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not variant_match:
        raise KeyError(f"Case variant {case_id} not found in {suite_spec(mode).source}")
    return f"{stem}\n\n{variant_match.group(1).strip()}".strip()


def retrieve_marking_criteria(mode: str, selector: str | int) -> str:
    """Return evaluator-only marking criteria for one bundled case."""
    case_id, case_number, variant = _case_parts(mode, selector)
    text = _read_mode_text(mode)
    if not variant:
        standalone_match = re.search(
            rf"^# Case {re.escape(case_number)}\b.*?^## Marking criteria\s*\n"
            rf"(.*?)(?=^---\s*$|^# Case \d+\b|^# Source notes\b|\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if standalone_match:
            return standalone_match.group(1).strip()
        raise ValueError(
            f"Case {case_number} in {suite_spec(mode).source} requires a variant identifier for marking criteria"
        )

    criteria_match = re.search(
        rf"^## Case {re.escape(case_id)}\b.*?^### Marking criteria\s*\n"
        rf"(.*?)(?=^## Case \d+[A-Z]\b|^---\s*$|^# Case \d+\b|^# Source notes\b|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not criteria_match:
        raise KeyError(f"Marking criteria for case variant {case_id} not found in {suite_spec(mode).source}")
    return criteria_match.group(1).strip()


def list_case_ids(mode: str) -> tuple[str, ...]:
    """List selectable IDs in source order for a bundled suite."""
    text = _read_mode_text(mode)
    ids: list[str] = []
    for case_match in re.finditer(r"^# Case (\d+)\b", text, flags=re.MULTILINE):
        number = case_match.group(1)
        start = case_match.end()
        next_match = re.search(r"^# Case \d+\b", text[start:], flags=re.MULTILINE)
        block = text[start : start + next_match.start()] if next_match else text[start:]
        variants = re.findall(rf"^## Case {re.escape(number)}([A-Z])\b", block, flags=re.MULTILINE)
        if variants:
            ids.extend(f"{number}{variant}" for variant in variants)
        else:
            ids.append(number)
    return tuple(ids)


def marking_bundle_filename(mode: str, selector: str | int) -> str:
    spec = suite_spec(mode)
    if not spec.marking_prefix:
        raise ValueError(f"{mode} does not use an external marking ZIP")
    return f"{spec.marking_prefix}-{normalise_selector(mode, selector)}.zip"


def write_demo_marking_criteria_after_report(
    selector: str | int,
    *,
    report_path: Path,
    output_path: Path,
) -> Path:
    """Materialise demo criteria only after a completed report exists.

    This preserves the historical `demo-expected.md` convenience artifact without
    exposing expected behaviour during report generation.
    """
    report_path = Path(report_path)
    if not report_path.is_file() or not report_path.read_text(encoding="utf-8").strip():
        raise ValueError("demo marking criteria may be materialised only after a non-empty report-final.md exists")
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(retrieve_marking_criteria("nel-demo", selector).rstrip() + "\n", encoding="utf-8")
    return output_path
