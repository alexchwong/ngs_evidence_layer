#!/usr/bin/env python3
"""Validate legacy terraced-v6 local defaults without touching root config.

``terraced_v6`` remains runnable for legacy/reproducibility use, but root
``config/`` is owned by the canonical ``proforma_v1`` workflow. This helper
therefore validates only terraced-v6's workflow-local settings and pipelines.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from workflows.terraced_v6 import pipeline_registry

SOURCE_SETTINGS = HERE / "settings.json.template"
SOURCE_PIPELINES = HERE / "pipelines"


def _validate_sources() -> int:
    if not SOURCE_SETTINGS.is_file():
        raise RuntimeError(f"missing terraced-v6 settings template: {SOURCE_SETTINGS}")
    doc = json.loads(SOURCE_SETTINGS.read_text(encoding="utf-8"))
    if not isinstance(doc, dict):
        raise RuntimeError("terraced-v6 settings template must contain a JSON object")
    paths = sorted(SOURCE_PIPELINES.glob("*.yaml"))
    if not paths:
        raise RuntimeError(f"no pipeline defaults found in {SOURCE_PIPELINES}")
    for path in paths:
        pipeline_registry.load_yaml(path)
    return 1 + len(paths)


def check() -> int:
    count = _validate_sources()
    print("STATUS=ok")
    print(f"FILES={count}")
    print("ROOT_CONFIG_UNCHANGED=true")
    return 0


def sync() -> int:
    return check()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate terraced-v6 local settings/pipeline defaults")
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
