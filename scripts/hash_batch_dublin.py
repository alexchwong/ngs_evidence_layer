#!/usr/bin/env python3
"""Export a Dublin validation batch into source-blinded report filenames.

Supported inputs:
- an NEL batch directory containing batch.json and child report-final.md files;
- a ChatGPT directory/zip containing case-1.md ... case-10.md and source_manifest.json.

Outputs are appended under evaluation/ by default:
- evaluation/blinded/<random>-case-N.md
- evaluation/hash_index.csv
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import secrets
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "evaluation" / "blinded"
DEFAULT_INDEX = ROOT / "evaluation" / "hash_index.csv"
EXPECTED_CASES = tuple(str(i) for i in range(1, 11))
INDEX_FIELDS = ("filename", "profile", "run #")
HASH_BYTES = 4


class BlindExportError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise BlindExportError(f"missing required file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise BlindExportError(f"invalid JSON in {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise BlindExportError(f"expected JSON object: {path}")
    return value


def _case_number(value: Any) -> str:
    text = str(value or "").strip()
    if text in EXPECTED_CASES:
        return text
    match = re.fullmatch(r"case[-_ ]?(10|[1-9])", text, re.IGNORECASE)
    if match:
        return match.group(1)
    raise BlindExportError(f"cannot map case identifier to Dublin case 1-10: {text!r}")


def _validate_cases(reports: dict[str, Path]) -> dict[str, Path]:
    missing = [case for case in EXPECTED_CASES if case not in reports]
    extra = sorted(set(reports) - set(EXPECTED_CASES))
    if missing or extra or len(reports) != 10:
        parts = []
        if missing:
            parts.append("missing " + ", ".join(f"case-{case}" for case in missing))
        if extra:
            parts.append("unexpected " + ", ".join(extra))
        raise BlindExportError("Dublin export requires exactly cases 1-10: " + "; ".join(parts))
    for case, path in reports.items():
        if not path.is_file():
            raise BlindExportError(f"case-{case} report is missing: {path}")
    return reports


def _read_existing_names(index_path: Path, output_dir: Path) -> set[str]:
    names = {path.name for path in output_dir.glob("*.md")} if output_dir.is_dir() else set()
    if not index_path.is_file():
        return names
    with index_path.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames and tuple(reader.fieldnames) != INDEX_FIELDS:
            raise BlindExportError(
                f"unexpected index columns in {index_path}: {reader.fieldnames}; expected {list(INDEX_FIELDS)}"
            )
        for row in reader:
            filename = str(row.get("filename") or "").strip()
            if filename:
                names.add(filename)
    return names


def _new_filename(case: str, used: set[str]) -> str:
    while True:
        filename = f"{secrets.token_hex(HASH_BYTES)}-case-{case}.md"
        if filename not in used:
            used.add(filename)
            return filename


def _detect_nel(root: Path) -> tuple[dict[str, Path], str, str]:
    batch_path = root / "batch.json"
    batch = _load_json(batch_path)
    if batch.get("kind") != "batch":
        raise BlindExportError(f"not an NEL batch manifest: {batch_path}")
    if batch.get("mode") != "nel-validate-dublin":
        raise BlindExportError(
            f"NEL batch mode is {batch.get('mode')!r}; expected 'nel-validate-dublin'"
        )
    profile = str(batch.get("pipeline") or "").strip()
    run_label = str(batch.get("batch_id") or root.name).strip()
    if not profile:
        raise BlindExportError(f"NEL batch manifest has no pipeline/profile: {batch_path}")
    children = batch.get("children")
    if not isinstance(children, list):
        raise BlindExportError(f"NEL batch manifest children must be a list: {batch_path}")
    reports: dict[str, Path] = {}
    for child in children:
        if not isinstance(child, dict):
            raise BlindExportError(f"invalid child entry in {batch_path}")
        source_case_id = child.get("source_case_id")
        if source_case_id is None:
            title = str(child.get("title") or "").strip()
            match = re.fullmatch(r"Case\s+(10|[1-9])", title, re.IGNORECASE)
            if not match:
                raise BlindExportError(
                    f"batch child {child.get('case_id')!r} has no Dublin source_case_id"
                )
            source_case_id = match.group(1)
        case = _case_number(source_case_id)
        child_id = str(child.get("case_id") or "").strip()
        if not child_id:
            raise BlindExportError(f"case-{case} has no child case_id in {batch_path}")
        if case in reports:
            raise BlindExportError(f"NEL batch contains Dublin case-{case} more than once")
        reports[case] = root / child_id / "report-final.md"
    return _validate_cases(reports), profile, run_label


def _detect_chatgpt(root: Path) -> tuple[dict[str, Path], str, str]:
    manifest_path = root / "source_manifest.json"
    manifest = _load_json(manifest_path)
    if str(manifest.get("source") or "").strip().lower() != "chatgpt":
        raise BlindExportError(f"source_manifest.json must declare source 'ChatGPT': {manifest_path}")
    profile = str(manifest.get("profile") or "").strip()
    run_label = str(manifest.get("run") or "").strip()
    if not profile or not run_label:
        raise BlindExportError("ChatGPT source_manifest.json requires non-empty profile and run")
    cases = manifest.get("cases")
    if not isinstance(cases, dict):
        raise BlindExportError("ChatGPT source_manifest.json requires a cases object")
    reports: dict[str, Path] = {}
    for key, filename in cases.items():
        case = _case_number(key)
        file_text = str(filename or "").strip()
        if not file_text or Path(file_text).name != file_text:
            raise BlindExportError(f"invalid report filename for case-{case}: {filename!r}")
        if case in reports:
            raise BlindExportError(f"source_manifest.json defines case-{case} more than once")
        reports[case] = root / file_text
    return _validate_cases(reports), profile, run_label


def _detect(root: Path) -> tuple[dict[str, Path], str, str, str]:
    if (root / "batch.json").is_file():
        reports, profile, run_label = _detect_nel(root)
        return reports, profile, run_label, "NEL"
    if (root / "source_manifest.json").is_file():
        reports, profile, run_label = _detect_chatgpt(root)
        return reports, profile, run_label, "ChatGPT"
    raise BlindExportError(
        "input is neither an NEL batch (batch.json) nor a ChatGPT export (source_manifest.json)"
    )


def _append_index(index_path: Path, rows: list[dict[str, str]]) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    exists = index_path.is_file() and index_path.stat().st_size > 0
    with index_path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS)
        if not exists:
            writer.writeheader()
        writer.writerows(rows)


def export(root: Path, *, output_dir: Path, index_path: Path) -> list[dict[str, str]]:
    reports, profile, run_label, source = _detect(root)
    output_dir.mkdir(parents=True, exist_ok=True)
    used = _read_existing_names(index_path, output_dir)
    planned: list[tuple[Path, Path, dict[str, str]]] = []
    for case in EXPECTED_CASES:
        filename = _new_filename(case, used)
        destination = output_dir / filename
        row = {"filename": filename, "profile": profile, "run #": run_label}
        planned.append((reports[case], destination, row))

    copied: list[Path] = []
    try:
        for source_path, destination, _row in planned:
            shutil.copyfile(source_path, destination)
            copied.append(destination)
        rows = [row for _source, _destination, row in planned]
        _append_index(index_path, rows)
    except Exception:
        for path in copied:
            try:
                path.unlink()
            except OSError:
                pass
        raise

    print(f"SOURCE={source}")
    print(f"PROFILE={profile}")
    print(f"RUN={run_label}")
    print(f"EXPORTED={len(planned)}")
    print(f"OUTPUT_DIR={output_dir.resolve()}")
    print(f"INDEX={index_path.resolve()}")
    for _source, destination, _row in planned:
        print(destination.name)
    return [row for _source, _destination, row in planned]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="NEL Dublin batch folder, or ChatGPT Dublin folder/zip")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX)
    args = parser.parse_args(argv)

    input_path = args.input.expanduser().resolve()
    try:
        if input_path.is_dir():
            export(input_path, output_dir=args.output_dir, index_path=args.index)
            return 0
        if input_path.is_file() and input_path.suffix.lower() == ".zip":
            with tempfile.TemporaryDirectory(prefix="nel-blind-dublin-") as temp:
                target = Path(temp)
                with zipfile.ZipFile(input_path) as archive:
                    archive.extractall(target)
                candidates = [target]
                candidates.extend(path for path in target.iterdir() if path.is_dir())
                roots = [
                    path for path in candidates
                    if (path / "source_manifest.json").is_file() or (path / "batch.json").is_file()
                ]
                if len(roots) != 1:
                    raise BlindExportError(
                        f"zip must contain exactly one export root; found {len(roots)}"
                    )
                export(roots[0], output_dir=args.output_dir, index_path=args.index)
                return 0
        raise BlindExportError(f"input does not exist or is not a directory/zip: {input_path}")
    except (BlindExportError, OSError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"blind export error: {exc}\n")


if __name__ == "__main__":
    raise SystemExit(main())
