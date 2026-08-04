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
    errors = [] if expected == actual else ["disease vocabulary and package schema enum differ"]

    publication_vocabulary = json.loads(
        read(ROOT / "schema" / "publication_type_vocabulary.json")
    )
    publication_types = [entry["value"] for entry in publication_vocabulary["types"]]
    census = json.loads(read(ROOT / "schema" / "census_schema.json"))
    census_types = census["properties"]["publication_type"]["enum"]
    package_types = package["properties"]["publication_type"]["enum"]
    if publication_types != census_types:
        errors.append("publication type vocabulary and census schema enum differ")
    if publication_types != package_types:
        errors.append("publication type vocabulary and package schema enum differ")
    return errors


def publication_type_rubric(phase):
    vocabulary = json.loads(read(ROOT / "schema" / "publication_type_vocabulary.json"))
    lines = ["Allowed values and operational definitions:"]
    for entry in vocabulary["types"]:
        lines.append(
            f'- `{entry["value"]}`: {entry["definition"]} {entry["excludes"]}'
        )
    lines.append("\nApply these precedence rules in order:")
    lines.extend(
        f"{number}. {rule}"
        for number, rule in enumerate(vocabulary["precedence"], start=1)
    )
    if phase == 3:
        lines.append("\nApply these audit-stability rules:")
        lines.extend(f"- {rule}" for rule in vocabulary["audit_stability"])
    return "\n".join(lines)


def render(phase):
    template = read(ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md")
    replacements = {}
    if phase in (1, 3):
        replacements["{{PUBLICATION_TYPE_RUBRIC}}"] = publication_type_rubric(phase)
    if phase in (1, 2, 4):
        replacements["{{REPORTING_RULES}}"] = read(ROOT / "rules" / "agreed_reporting_rules.md")
    if phase == 1:
        replacements["{{CENSUS_SCHEMA}}"] = read(ROOT / "schema" / "census_schema.json")
    if phase in (2, 4):
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
    parser.add_argument("--phase", type=int, choices=(1, 2, 3, 4), required=True)
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