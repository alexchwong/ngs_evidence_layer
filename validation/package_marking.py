#!/usr/bin/env python3
"""Build a self-contained external-marking bundle for one validation case."""
from __future__ import annotations

import argparse
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from validation.cases import retrieve_case, retrieve_MC  # noqa: E402

DEFAULT_PROMPT = ROOT / "validation" / "mark_validation_report.md"
DEFAULT_CASE_FILE = ROOT / "validation" / "case_summary.md"
CASE_TOKEN = "{{CASE_IDENTIFIER}}"
CRITERIA_TOKEN = "{{CASE_SPECIFIC_MARKING_CRITERIA}}"
ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


def render_marking_prompt(
    case_id: str,
    prompt_path: Path = DEFAULT_PROMPT,
    case_file: Path = DEFAULT_CASE_FILE,
) -> str:
    template = prompt_path.read_text(encoding="utf-8")
    criteria = retrieve_MC(case_id, str(case_file))

    missing = [token for token in (CASE_TOKEN, CRITERIA_TOKEN) if token not in template]
    if missing:
        raise ValueError(
            "marking prompt template is missing required token(s): " + ", ".join(missing)
        )

    rendered = template.replace(CASE_TOKEN, case_id.upper())
    rendered = rendered.replace(CRITERIA_TOKEN, criteria.strip())
    return rendered.rstrip() + "\n"


def _writestr(zf: zipfile.ZipFile, name: str, text: str) -> None:
    info = zipfile.ZipInfo(name, ZIP_TIMESTAMP)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    zf.writestr(info, text.encode("utf-8"))


def package_marking_bundle(
    case_id: str,
    report_path: Path,
    output_path: Path,
    prompt_path: Path = DEFAULT_PROMPT,
    case_file: Path = DEFAULT_CASE_FILE,
) -> Path:
    if not report_path.is_file():
        raise FileNotFoundError(
            f"cannot package marking bundle because report-final.md is missing: {report_path}. "
            "Complete Step 6B validation and Step 6C deterministic citation rendering first, then rerun Step 7B."
        )

    report = report_path.read_text(encoding="utf-8")
    if not report.strip():
        raise ValueError(
            f"cannot package marking bundle because report-final.md is empty: {report_path}. "
            "Do not package an empty placeholder; regenerate the report through Steps 6B-6C, then rerun Step 7B."
        )

    validation_case = retrieve_case(case_id, str(case_file))
    marking_prompt = render_marking_prompt(case_id, prompt_path, case_file)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output_path, "w") as zf:
        _writestr(zf, "marking-prompt.md", marking_prompt)
        _writestr(zf, "validation-case.md", validation_case.rstrip() + "\n")
        _writestr(zf, "report-final.md", report)

    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Package report-final.md with the validation case and self-contained marking prompt."
    )
    parser.add_argument("case", help="Validation case variant, e.g. 1A")
    parser.add_argument("--report", type=Path, required=True, help="Path to report-final.md")
    parser.add_argument("--output", type=Path, required=True, help="Output ZIP path")
    parser.add_argument(
        "--case-file",
        type=Path,
        default=DEFAULT_CASE_FILE,
        help="Validation case source (default: validation/case_summary.md)",
    )
    parser.add_argument(
        "--prompt",
        type=Path,
        default=DEFAULT_PROMPT,
        help="Marking prompt template (default: validation/mark_validation_report.md)",
    )
    args = parser.parse_args()

    try:
        path = package_marking_bundle(
            args.case, args.report, args.output, args.prompt, args.case_file
        )
    except (OSError, KeyError, ValueError) as exc:
        parser.exit(1, f"Error: {exc}\n")

    print(path.resolve())


if __name__ == "__main__":
    main()
