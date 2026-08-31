#!/usr/bin/env python3
"""Build a self-contained external-marking bundle for one validation case."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.scripts.bundled_cases import (  # noqa: E402
    is_validation_mode,
    marking_bundle_filename,
    retrieve_case_input,
    retrieve_marking_criteria,
    validation_modes,
)

DEFAULT_PROMPT = ROOT / "validation" / "mark_validation_report.md"
CASE_TOKEN = "{{CASE_IDENTIFIER}}"
CRITERIA_TOKEN = "{{CASE_SPECIFIC_MARKING_CRITERIA}}"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def render_marking_prompt(mode: str, case_id: str, prompt_path: Path = DEFAULT_PROMPT) -> str:
    if not is_validation_mode(mode):
        raise ValueError(f"external marking bundles are only defined for validation modes, not {mode!r}")
    template = Path(prompt_path).read_text(encoding="utf-8")
    criteria = retrieve_marking_criteria(mode, case_id)
    missing = [token for token in (CASE_TOKEN, CRITERIA_TOKEN) if token not in template]
    if missing:
        raise ValueError("marking prompt template is missing required token(s): " + ", ".join(missing))
    return (
        template.replace(CASE_TOKEN, str(case_id).upper())
        .replace(CRITERIA_TOKEN, criteria.strip())
        .rstrip()
        + "\n"
    )


def _writestr(zf: zipfile.ZipFile, name: str, text: str) -> None:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, text.encode("utf-8"))


def package_marking_bundle(
    mode: str,
    case_id: str,
    report_path: Path,
    output_path: Path | None = None,
    prompt_path: Path = DEFAULT_PROMPT,
) -> Path:
    """Package one completed validation report using the canonical suite registry."""
    if not is_validation_mode(mode):
        raise ValueError(f"unsupported validation mode for marking bundle: {mode!r}")
    report_path = Path(report_path)
    if not report_path.is_file():
        raise FileNotFoundError(
            f"cannot package marking bundle because report-final.md is missing: {report_path}. "
            "Complete report finalisation first, then rerun deterministic packaging."
        )
    report = report_path.read_text(encoding="utf-8")
    if not report.strip():
        raise ValueError(f"cannot package marking bundle because report-final.md is empty: {report_path}")

    validation_case = retrieve_case_input(mode, case_id)
    marking_prompt = render_marking_prompt(mode, case_id, prompt_path)
    output = Path(output_path) if output_path is not None else report_path.parent / marking_bundle_filename(mode, case_id)
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as zf:
        _writestr(zf, "marking-prompt.md", marking_prompt)
        _writestr(zf, "validation-case.md", validation_case.rstrip() + "\n")
        _writestr(zf, "report-final.md", report)
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", help="Validation case selector, e.g. 1A")
    parser.add_argument("--mode", required=True, choices=sorted(validation_modes()))
    parser.add_argument("--report", type=Path, required=True, help="Path to report-final.md")
    parser.add_argument("--output", type=Path, help="Optional output ZIP path; canonical name is used by default")
    parser.add_argument("--prompt", type=Path, default=DEFAULT_PROMPT)
    args = parser.parse_args()
    try:
        print(package_marking_bundle(args.mode, args.case, args.report, args.output, args.prompt).resolve())
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")


if __name__ == "__main__":
    main()
