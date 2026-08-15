#!/usr/bin/env python3
"""Convert the canonical blacklist YAML into runtime JSON."""
import argparse
import json
import sys
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SOURCE = REPO_ROOT / "output/corpus/blacklist.yaml"
DEFAULT_OUTPUT = REPO_ROOT / "output/corpus/blacklist.json"


def convert(source, output):
    """Read YAML from ``source`` and write deterministic JSON to ``output``."""
    source = Path(source)
    output = Path(output)
    try:
        document = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"blacklist YAML is invalid: {exc}") from exc
    if document is None:
        document = {}
    try:
        payload = json.dumps(document, indent=2, ensure_ascii=False) + "\n"
    except (TypeError, ValueError) as exc:
        raise ValueError(f"blacklist YAML cannot be represented as JSON: {exc}") from exc
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(payload, encoding="utf-8")
    return output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    try:
        output = convert(args.source, args.output)
    except (OSError, ValueError) as exc:
        sys.exit(f"blacklist build failed: {exc}")
    print(f"wrote {output}", file=sys.stderr)


if __name__ == "__main__":
    main()