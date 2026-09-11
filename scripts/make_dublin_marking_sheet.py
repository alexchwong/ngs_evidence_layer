#!/usr/bin/env python3
"""Create a source-blinded CSV marking sheet for exported Dublin reports.

The script reads only blinded report filenames; it does not read hash_index.csv.
Rows are sorted by filename so Excel order matches opening the reports alphabetically.
Applicable Dublin rubric cells are blank for manual entry; non-applicable cells are N/A.
"""
from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_REPORTS_DIR = ROOT / "evaluation" / "blinded"
DEFAULT_SUITE = ROOT / "validation" / "validation_dublin.md"
DEFAULT_OUTPUT = ROOT / "evaluation" / "marking_sheet.csv"
EXPECTED_CASES = tuple(str(i) for i in range(1, 11))
REPORT_RE = re.compile(r"^[0-9a-f]{8}-case-(10|[1-9])\.md$")
CASE_HEADING_RE = re.compile(r"^## Case (10|[1-9])(?:\s+—\s+.*)?$", re.MULTILINE)
CRITERION_RE = re.compile(r"^- \*\*(R([1-5])C([1-9][0-9]*))\.\*\*", re.MULTILINE)


class MarkingSheetError(RuntimeError):
    pass


def _criterion_key(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"R([1-5])C([1-9][0-9]*)", value)
    if not match:
        raise MarkingSheetError(f"invalid criterion identifier: {value!r}")
    return int(match.group(1)), int(match.group(2))


def _parse_suite(path: Path) -> dict[str, tuple[str, ...]]:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise MarkingSheetError(f"Dublin validation suite is missing: {path}") from exc

    matches = list(CASE_HEADING_RE.finditer(text))
    criteria_by_case: dict[str, tuple[str, ...]] = {}
    for index, match in enumerate(matches):
        case = match.group(1)
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[match.end():end]
        criteria = tuple(sorted({m.group(1) for m in CRITERION_RE.finditer(block)}, key=_criterion_key))
        if not criteria:
            raise MarkingSheetError(f"Dublin case-{case} has no marking criteria in {path}")

        # Keep the manual marking sheet aligned with the validation registry contract:
        # within each rubric, criteria must start at C1 and be contiguous. This catches
        # accidental gaps such as R2C2/R2C3/R2C4 before a marking sheet is generated.
        by_rubric: dict[int, list[int]] = {}
        for criterion in criteria:
            rubric, number = _criterion_key(criterion)
            by_rubric.setdefault(rubric, []).append(number)
        for rubric, numbers in sorted(by_rubric.items()):
            expected = list(range(1, len(numbers) + 1))
            if numbers != expected:
                found = ", ".join(f"R{rubric}C{number}" for number in numbers)
                wanted = ", ".join(f"R{rubric}C{number}" for number in expected)
                raise MarkingSheetError(
                    f"Dublin case-{case} has non-contiguous R{rubric} criteria: "
                    f"found {found}; expected {wanted}"
                )

        if case in criteria_by_case:
            raise MarkingSheetError(f"Dublin case-{case} appears more than once in {path}")
        criteria_by_case[case] = criteria

    missing = [case for case in EXPECTED_CASES if case not in criteria_by_case]
    extra = sorted(set(criteria_by_case) - set(EXPECTED_CASES))
    if missing or extra or len(criteria_by_case) != 10:
        details: list[str] = []
        if missing:
            details.append("missing " + ", ".join(f"case-{case}" for case in missing))
        if extra:
            details.append("unexpected " + ", ".join(f"case-{case}" for case in extra))
        raise MarkingSheetError(
            "Dublin marking sheet requires exactly cases 1-10 in the validation suite: "
            + "; ".join(details)
        )
    return criteria_by_case


def _discover_reports(reports_dir: Path) -> list[tuple[str, str]]:
    if not reports_dir.is_dir():
        raise MarkingSheetError(f"blinded reports directory is missing: {reports_dir}")

    markdown = sorted((path for path in reports_dir.iterdir() if path.is_file() and path.suffix.lower() == ".md"),
                      key=lambda path: path.name.casefold())
    if not markdown:
        raise MarkingSheetError(f"no blinded Markdown reports found in {reports_dir}")

    reports: list[tuple[str, str]] = []
    unexpected: list[str] = []
    for path in markdown:
        match = REPORT_RE.fullmatch(path.name)
        if not match:
            unexpected.append(path.name)
            continue
        reports.append((path.name, match.group(1)))
    if unexpected:
        raise MarkingSheetError(
            "unexpected Markdown file(s) in blinded reports directory: " + ", ".join(unexpected)
        )

    counts = {case: 0 for case in EXPECTED_CASES}
    for _filename, case in reports:
        counts[case] += 1
    missing = [case for case, count in counts.items() if count == 0]
    if missing:
        raise MarkingSheetError(
            "marking sheet requires at least one report for every Dublin case; missing "
            + ", ".join(f"case-{case}" for case in missing)
        )
    distinct_counts = set(counts.values())
    if len(distinct_counts) != 1:
        detail = ", ".join(f"case-{case}={counts[case]}" for case in EXPECTED_CASES)
        raise MarkingSheetError(
            "Dublin cases are not balanced across completed runs; expected the same number of reports per case: "
            + detail
        )
    return reports


def build_sheet(*, reports_dir: Path, suite_path: Path, output_path: Path, force: bool = False) -> int:
    criteria_by_case = _parse_suite(suite_path)
    reports = _discover_reports(reports_dir)
    criteria = sorted({criterion for values in criteria_by_case.values() for criterion in values}, key=_criterion_key)
    fields = ["filename", "case", *criteria, "total", "comments"]

    if output_path.exists() and output_path.stat().st_size > 0 and not force:
        raise MarkingSheetError(
            f"refusing to overwrite existing marking sheet: {output_path}; use --force only if you intend to replace it"
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for filename, case in reports:
            applicable = set(criteria_by_case[case])
            row = {field: "" for field in fields}
            row["filename"] = filename
            row["case"] = f"case-{case}"
            for criterion in criteria:
                if criterion not in applicable:
                    row[criterion] = "N/A"
            writer.writerow(row)

    run_count = len(reports) // 10
    print(f"REPORTS={len(reports)}")
    print(f"RUNS={run_count}")
    print(f"OUTPUT={output_path.resolve()}")
    print("ORDER=filename ascending")
    return len(reports)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports", type=Path, default=DEFAULT_REPORTS_DIR,
                        help="directory containing blinded *-case-N.md reports")
    parser.add_argument("--suite", type=Path, default=DEFAULT_SUITE,
                        help="canonical Dublin validation Markdown used only to determine applicable criterion IDs")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT,
                        help="CSV file to create (default: evaluation/marking_sheet.csv)")
    parser.add_argument("--force", action="store_true",
                        help="replace an existing marking sheet; normally refused to protect entered marks")
    args = parser.parse_args(argv)
    try:
        build_sheet(
            reports_dir=args.reports.expanduser().resolve(),
            suite_path=args.suite.expanduser().resolve(),
            output_path=args.output.expanduser().resolve(),
            force=args.force,
        )
        return 0
    except (MarkingSheetError, OSError) as exc:
        parser.exit(1, f"marking sheet error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
