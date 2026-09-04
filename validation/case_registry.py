#!/usr/bin/env python3
"""Discover and retrieve canonical repository validation cases.

A validation suite is registered by dropping one canonical Markdown file under
``validation/``. Registration is data-driven: no suite names or filenames are
hard-coded in Python.
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

VALIDATION_ROOT = Path(__file__).resolve().parent
SCHEMA_VERSION = 1
SUITE_RE = re.compile(r"nel-validate(?:-[a-z0-9]+)*")
CASE_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")
CASE_HEADING_RE = re.compile(r"^## Case ([A-Za-z0-9][A-Za-z0-9._-]*)(?:\s+—\s+.*)?$", re.MULTILINE)
RUBRIC_HEADINGS = {
    "R1": "Diagnosis and classification",
    "R2": "Prognostic interpretation",
    "R3": "Clinical actionability",
    "R4": "MRD interpretation",
    "R5": "Possible germline flagging",
}
CRITERION_RE = re.compile(r"^- \*\*(R([1-5])C([1-9][0-9]*))\.\*\*\s+(.+)$")


class RegistryError(ValueError):
    pass


@dataclass(frozen=True)
class CaseRecord:
    case_id: str
    title: str | None
    summary: str
    criteria: str


@dataclass(frozen=True)
class SuiteRecord:
    schema_version: int
    suite: str
    title: str
    path: Path
    cases: tuple[CaseRecord, ...]

    @property
    def mode(self) -> str:
        return self.suite


def _front_matter(text: str, path: Path) -> tuple[dict[str, str], str]:
    if not text.startswith("---\n"):
        raise RegistryError(f"{path}: missing YAML-style front matter")
    end = text.find("\n---\n", 4)
    if end < 0:
        raise RegistryError(f"{path}: unterminated front matter")
    raw = text[4:end]
    data: dict[str, str] = {}
    for line_no, raw_line in enumerate(raw.splitlines(), start=2):
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" not in line:
            raise RegistryError(f"{path}:{line_no}: front matter must use key: value lines")
        key, value = line.split(":", 1)
        key, value = key.strip(), value.strip()
        if key in data:
            raise RegistryError(f"{path}:{line_no}: duplicate front-matter key {key!r}")
        data[key] = value
    allowed = {"schema_version", "suite", "title"}
    unknown = sorted(set(data) - allowed)
    missing = sorted(allowed - set(data))
    if unknown:
        raise RegistryError(f"{path}: unknown front-matter key(s): {', '.join(unknown)}")
    if missing:
        raise RegistryError(f"{path}: missing front-matter key(s): {', '.join(missing)}")
    return data, text[end + 5 :]


def _parse_case(block: str, case_id: str, title: str | None, path: Path) -> CaseRecord:
    if not CASE_ID_RE.fullmatch(case_id):
        raise RegistryError(f"{path}: invalid case id {case_id!r}")
    summary_marker = "### Case summary\n"
    criteria_marker = "### Marking criteria\n"
    if block.count(summary_marker) != 1 or block.count(criteria_marker) != 1:
        raise RegistryError(
            f"{path}: Case {case_id} must contain exactly one '### Case summary' and one '### Marking criteria'"
        )
    if block.index(summary_marker) > block.index(criteria_marker):
        raise RegistryError(f"{path}: Case {case_id} must place Case summary before Marking criteria")
    summary_start = block.index(summary_marker) + len(summary_marker)
    criteria_start = block.index(criteria_marker)
    summary = block[summary_start:criteria_start].strip()
    criteria = block[criteria_start + len(criteria_marker):].strip()
    if not summary:
        raise RegistryError(f"{path}: Case {case_id} has an empty case summary")
    if not criteria:
        raise RegistryError(f"{path}: Case {case_id} has no marking criteria")
    if re.search(r"^### (?!Case summary$|Marking criteria$).+", block, re.MULTILINE):
        raise RegistryError(f"{path}: Case {case_id} contains a non-canonical ### section")
    if re.search(r"^#{1,2} (?:NEL task|Shared stem|Differences from stem|Trap)\b", block, re.MULTILINE | re.IGNORECASE):
        raise RegistryError(f"{path}: Case {case_id} contains prohibited legacy benchmark sections")

    seen_rubrics: list[int] = []
    expected_next: dict[int, int] = {}
    criterion_count = 0
    current_rubric: int | None = None
    for line_no, line in enumerate(criteria.splitlines(), start=1):
        if not line.strip():
            continue
        rubric_match = re.fullmatch(r"#### R([1-5]) — (.+)", line)
        if rubric_match:
            rubric = int(rubric_match.group(1))
            expected_title = RUBRIC_HEADINGS[f"R{rubric}"]
            if rubric_match.group(2) != expected_title:
                raise RegistryError(
                    f"{path}: Case {case_id}: R{rubric} heading must be '#### R{rubric} — {expected_title}'"
                )
            if rubric in seen_rubrics or (seen_rubrics and rubric < seen_rubrics[-1]):
                raise RegistryError(f"{path}: Case {case_id}: rubric headings must be unique and ordered R1 to R5")
            seen_rubrics.append(rubric)
            expected_next[rubric] = 1
            current_rubric = rubric
            continue
        criterion_match = CRITERION_RE.fullmatch(line)
        if criterion_match:
            rubric = int(criterion_match.group(2))
            number = int(criterion_match.group(3))
            if current_rubric != rubric:
                raise RegistryError(
                    f"{path}: Case {case_id}: {criterion_match.group(1)} is not under its matching R{rubric} heading"
                )
            if number != expected_next[rubric]:
                raise RegistryError(
                    f"{path}: Case {case_id}: R{rubric} criteria must be sequential from C1; got C{number}"
                )
            text = criterion_match.group(4).strip()
            if not text:
                raise RegistryError(f"{path}: Case {case_id}: empty criterion {criterion_match.group(1)}")
            expected_next[rubric] += 1
            criterion_count += 1
            continue
        raise RegistryError(f"{path}: Case {case_id}: invalid marking-criteria line {line_no}: {line!r}")
    if criterion_count == 0:
        raise RegistryError(f"{path}: Case {case_id} has no R1-R5 criteria")
    return CaseRecord(case_id=case_id, title=title, summary=summary, criteria=criteria)


def parse_suite(path: Path) -> SuiteRecord:
    path = Path(path)
    text = path.read_text(encoding="utf-8")
    meta, body = _front_matter(text, path)
    try:
        version = int(meta["schema_version"])
    except ValueError as exc:
        raise RegistryError(f"{path}: schema_version must be an integer") from exc
    if version != SCHEMA_VERSION:
        raise RegistryError(f"{path}: unsupported schema_version {version}; expected {SCHEMA_VERSION}")
    suite = meta["suite"]
    if not SUITE_RE.fullmatch(suite):
        raise RegistryError(f"{path}: suite must match {SUITE_RE.pattern!r}")
    title = meta["title"].strip()
    if not title:
        raise RegistryError(f"{path}: title must not be empty")
    h1 = re.findall(r"^# (.+)$", body, re.MULTILINE)
    if h1 != [title]:
        raise RegistryError(f"{path}: body must contain exactly one '# {title}' heading")

    matches = list(CASE_HEADING_RE.finditer(body))
    if not matches:
        raise RegistryError(f"{path}: suite contains no canonical '## Case <id>' sections")
    h1_match = re.match(rf"^\n?# {re.escape(title)}\n", body)
    if h1_match is None:
        raise RegistryError(f"{path}: '# {title}' must be the first body heading")
    if body[h1_match.end():matches[0].start()].strip():
        raise RegistryError(
            f"{path}: only canonical Case sections may appear between the suite title and first case"
        )
    cases: list[CaseRecord] = []
    seen: set[str] = set()
    for index, match in enumerate(matches):
        case_id = match.group(1)
        if case_id in seen:
            raise RegistryError(f"{path}: duplicate case id {case_id!r}")
        seen.add(case_id)
        heading = match.group(0)
        title_part = heading.split(" — ", 1)[1].strip() if " — " in heading else None
        start = match.end() + 1
        end = matches[index + 1].start() if index + 1 < len(matches) else len(body)
        cases.append(_parse_case(body[start:end], case_id, title_part, path))
    return SuiteRecord(version, suite, title, path.resolve(), tuple(cases))


def _candidate_files(root: Path = VALIDATION_ROOT) -> Iterable[Path]:
    for path in sorted(Path(root).glob("*.md")):
        try:
            prefix = path.read_text(encoding="utf-8")[:256]
        except OSError:
            continue
        if prefix.startswith("---\n") and ("\nschema_version:" in prefix or "\nsuite:" in prefix):
            yield path


def discover_suites(root: Path = VALIDATION_ROOT) -> dict[str, SuiteRecord]:
    suites: dict[str, SuiteRecord] = {}
    for path in _candidate_files(root):
        suite = parse_suite(path)
        if suite.suite in suites:
            raise RegistryError(
                f"duplicate validation suite {suite.suite!r}: {suites[suite.suite].path} and {suite.path}"
            )
        suites[suite.suite] = suite
    return suites


def validation_modes(root: Path = VALIDATION_ROOT) -> frozenset[str]:
    return frozenset(discover_suites(root))


def is_validation_mode(mode: str, root: Path = VALIDATION_ROOT) -> bool:
    return mode in validation_modes(root)


def suite_spec(mode: str, root: Path = VALIDATION_ROOT) -> SuiteRecord:
    try:
        return discover_suites(root)[mode]
    except KeyError as exc:
        raise RegistryError(f"unknown validation suite {mode!r}") from exc


def case_source_path(mode: str, root: Path = VALIDATION_ROOT) -> Path:
    return suite_spec(mode, root).path


def list_case_ids(mode: str, root: Path = VALIDATION_ROOT) -> tuple[str, ...]:
    return tuple(case.case_id for case in suite_spec(mode, root).cases)


def normalise_selector(mode: str, selector: str | int, root: Path = VALIDATION_ROOT) -> str:
    case_id = str(selector).strip()
    available = list_case_ids(mode, root)
    if case_id not in available:
        raise KeyError(f"case {case_id!r} not found in {mode}; available: {', '.join(available)}")
    return case_id


def _case(mode: str, selector: str | int, root: Path = VALIDATION_ROOT) -> CaseRecord:
    case_id = normalise_selector(mode, selector, root)
    return next(case for case in suite_spec(mode, root).cases if case.case_id == case_id)


def retrieve_case_input(mode: str, selector: str | int, root: Path = VALIDATION_ROOT) -> str:
    return _case(mode, selector, root).summary


def retrieve_marking_criteria(mode: str, selector: str | int, root: Path = VALIDATION_ROOT) -> str:
    return _case(mode, selector, root).criteria


def marking_bundle_filename(mode: str, selector: str | int, root: Path = VALIDATION_ROOT) -> str:
    case_id = normalise_selector(mode, selector, root)
    suffix = mode.removeprefix("nel-validate")
    return f"nel-validation{suffix}-{case_id}.zip"


def check(root: Path = VALIDATION_ROOT) -> tuple[SuiteRecord, ...]:
    suites = discover_suites(root)
    if not suites:
        raise RegistryError(f"no canonical validation suites discovered under {root}")
    return tuple(suites.values())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("check")
    sub.add_parser("list")
    get = sub.add_parser("get")
    get.add_argument("suite")
    get.add_argument("case_id")
    get.add_argument("--criteria", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.action == "check":
            suites = check()
            for suite in suites:
                print(f"{suite.suite}\t{len(suite.cases)}\t{suite.path.name}")
            return 0
        if args.action == "list":
            for suite in check():
                print(f"{suite.suite}\t{suite.title}\t{','.join(case.case_id for case in suite.cases)}")
            return 0
        if args.criteria:
            print(retrieve_marking_criteria(args.suite, args.case_id))
        else:
            print(retrieve_case_input(args.suite, args.case_id))
        return 0
    except (OSError, RegistryError, KeyError) as exc:
        parser.exit(1, f"validation registry error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
