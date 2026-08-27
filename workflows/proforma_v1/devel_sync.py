#!/usr/bin/env python3
"""Sync proforma-v1 developer defaults into the root user-facing config.

This script owns only shipped defaults. It never writes ``config/settings.json``
and never deletes custom files under ``config/pipelines``.
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
SOURCE_SETTINGS = HERE / "settings.json.template"
SOURCE_PIPELINES = HERE / "pipelines"
TARGET_CONFIG = REPO_ROOT / "config"
TARGET_SETTINGS = TARGET_CONFIG / "settings.json.template"
TARGET_PIPELINES = TARGET_CONFIG / "pipelines"


def _managed_files() -> list[tuple[Path, Path]]:
    rows = [(SOURCE_SETTINGS, TARGET_SETTINGS)]
    rows.extend((src, TARGET_PIPELINES / src.name) for src in sorted(SOURCE_PIPELINES.glob("*.yaml")))
    return rows


def _validate_sources(rows: list[tuple[Path, Path]]) -> None:
    missing = [str(src) for src, _dst in rows if not src.is_file()]
    if missing:
        raise RuntimeError("missing proforma-v1 default file(s): " + ", ".join(missing))
    if not any(src.suffix == ".yaml" for src, _dst in rows):
        raise RuntimeError(f"no pipeline defaults found in {SOURCE_PIPELINES}")


def check() -> int:
    rows = _managed_files()
    _validate_sources(rows)
    drift = []
    for src, dst in rows:
        if not dst.is_file() or src.read_bytes() != dst.read_bytes():
            drift.append((src, dst))
    if drift:
        for src, dst in drift:
            print(f"DRIFT={dst.relative_to(REPO_ROOT)} <- {src.relative_to(REPO_ROOT)}")
        return 1
    print(f"STATUS=ok")
    print(f"FILES={len(rows)}")
    return 0


def sync() -> int:
    rows = _managed_files()
    _validate_sources(rows)
    TARGET_CONFIG.mkdir(parents=True, exist_ok=True)
    TARGET_PIPELINES.mkdir(parents=True, exist_ok=True)
    for src, dst in rows:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
        print(f"SYNCED={dst.relative_to(REPO_ROOT)}")
    print("USER_SETTINGS_UNCHANGED=config/settings.json")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if root shipped defaults differ from proforma-v1")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return check() if args.check else sync()
    except Exception as exc:
        print(f"devel_sync failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
