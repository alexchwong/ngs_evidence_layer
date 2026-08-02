#!/usr/bin/env python3
"""Render one committed, self-contained phase prompt from canonical sources."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def read(path):
    return path.read_text(encoding="utf-8").rstrip()


def vocabulary_errors():
    vocabulary = json.loads(read(ROOT / "schema" / "disease_vocabulary.json"))
    package = json.loads(read(ROOT / "schema" / "ingestion_package_schema.json"))
    expected = vocabulary["diseases"] if isinstance(vocabulary, dict) else vocabulary
    actual = package["$defs"]["disease"]["enum"]
    return [] if expected == actual else ["disease vocabulary and package schema enum differ"]


def render(phase):
    template = read(ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md")
    replacements = {}
    if phase in (1, 2):
        replacements["{{REPORTING_RULES}}"] = read(ROOT / "rules" / "agreed_reporting_rules.md")
    if phase == 1:
        replacements["{{CENSUS_SCHEMA}}"] = read(ROOT / "schema" / "census_schema.json")
    if phase == 2:
        replacements["{{DISEASE_VOCABULARY}}"] = read(ROOT / "schema" / "disease_vocabulary.json")
        replacements["{{PACKAGE_SCHEMA}}"] = read(ROOT / "schema" / "ingestion_package_schema.json")
    for marker, content in replacements.items():
        template = template.replace(marker, content)
    unresolved = sorted(set(part.split("}}", 1)[0] + "}}" for part in template.split("{{")[1:]))
    if unresolved:
        raise ValueError("unresolved prompt markers: " + ", ".join(unresolved))
    if phase == 3 and any(term in template for term in ("agreed_reporting_rules", '"diseases": [', '"$schema"')):
        raise ValueError("Phase 3 prompt contains forbidden authoring context")
    return template + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--phase", type=int, choices=(1, 2, 3), required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        errors = vocabulary_errors()
        if errors:
            raise ValueError("\n".join(errors))
        destination = args.output or ROOT / "prompts" / f"phase{args.phase}_prompt.md"
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(render(args.phase), encoding="utf-8")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"PROMPT BUILD FAILED:\n{exc}")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()