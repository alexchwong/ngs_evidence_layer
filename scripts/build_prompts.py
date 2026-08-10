#!/usr/bin/env python3
"""Render one committed, self-contained phase prompt from canonical sources."""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VALIDATION_BUNDLE_FILES = (
    ROOT / "scripts" / "final_validation.py",
    ROOT / "scripts" / "package_validation.py",
    ROOT / "scripts" / "vocab.py",
)


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
        lines.append(f'- `{entry["value"]}`: {entry["definition"]} {entry["excludes"]}')
    lines.append("\nApply these precedence rules in order:")
    lines.extend(
        f"{number}. {rule}"
        for number, rule in enumerate(vocabulary["precedence"], start=1)
    )
    if phase == 3:
        lines.append("\nApply these audit-stability rules:")
        lines.extend(f"- {rule}" for rule in vocabulary["audit_stability"])
    return "\n".join(lines)


def source_disease_alias_policy():
    """Render the strict source-to-canonical disease alias policy."""
    vocabulary = json.loads(read(ROOT / "schema" / "disease_vocabulary.json"))
    aliases = vocabulary.get("source_disease_aliases", {})
    lines = [
        "A source-stated disease may ground a canonical card disease when it exactly",
        "matches one of these reviewed aliases (case-insensitive):",
        "",
    ]
    lines.extend(f'- `{alias}` → `{target}`' for alias, target in aliases.items())
    lines.extend(
        [
            "",
            "Emit only the canonical target in `diseases`, but preserve the source's",
            "actual disease or population wording in evidence and interpretation. Alias",
            "matching is otherwise exact. Do not use fuzzy matching, stemming, punctuation",
            "substitution, semantic inference, or nearest-term mapping. A source term that is",
            "neither canonical nor listed above remains outside the controlled vocabulary.",
        ]
    )
    return "\n".join(lines)


def validation_bundle_paths():
    """Return every repository-owned file needed by final_validation.py."""
    paths = list(VALIDATION_BUNDLE_FILES)
    paths.extend(sorted((ROOT / "schema").glob("*.json")))
    return paths


def validation_bundle():
    """Embed the canonical validator and all local dependencies verbatim."""
    lines = [
        "Create a directory named `validation_bundle` and recreate every file below",
        "at its displayed relative path. Preserve the directory structure and file",
        "contents verbatim. Do not combine files or rewrite imports.",
        "",
    ]
    for path in validation_bundle_paths():
        relative = path.relative_to(ROOT).as_posix()
        language = "python" if path.suffix == ".py" else "json"
        lines.extend(
            [
                f"<!-- BEGIN VERBATIM {relative} -->",
                f"```{language}",
                read(path),
                "```",
                f"<!-- END VERBATIM {relative} -->",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def render(phase):
    template = read(ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md")
    replacements = {
        "{{PHASE_VALIDATION_BUNDLE}}": validation_bundle(),
    }
    if phase in (2, 3, 4, 5):
        replacements["{{SOURCE_DISEASE_ALIAS_POLICY}}"] = source_disease_alias_policy()
    if phase in (1, 3):
        replacements["{{PUBLICATION_TYPE_RUBRIC}}"] = publication_type_rubric(phase)
    if phase in (1, 2, 4):
        replacements["{{REPORTING_RULES}}"] = read(
            ROOT / "rules" / "agreed_reporting_rules.md"
        )
    if phase == 1:
        replacements["{{CENSUS_SCHEMA}}"] = read(
            ROOT / "schema" / "census_schema.json"
        )
    if phase in (2, 4):
        replacements["{{DISEASE_VOCABULARY}}"] = read(
            ROOT / "schema" / "disease_vocabulary.json"
        )
        replacements["{{PACKAGE_SCHEMA}}"] = read(
            ROOT / "schema" / "ingestion_package_schema.json"
        )
    for marker, content in replacements.items():
        template = template.replace(marker, content)
    unresolved = sorted(
        set(part.split("}}", 1)[0] + "}}" for part in template.split("{{")[1:])
    )
    if unresolved:
        raise ValueError("unresolved prompt markers: " + ", ".join(unresolved))
    if phase == 3 and any(
        term in template
        for term in (
            "agreed_reporting_rules",
            '"diseases": [',
            '"$schema"',
        )
    ):
        # The validation bundle necessarily contains schemas and vocabulary data.
        # Restrict this guard to authoring context outside that verbatim bundle.
        before_bundle = template.split(
            "<!-- BEGIN VERBATIM scripts/final_validation.py -->", 1
        )[0]
        if any(
            term in before_bundle
            for term in ("agreed_reporting_rules", '"diseases": [', '"$schema"')
        ):
            raise ValueError("Phase 3 prompt contains forbidden authoring context")
    return template + "\n"


def render_phase5_review():
    template = read(ROOT / "prompts" / "templates" / "phase5_review_prompt.md")
    template = template.replace(
        "{{SOURCE_DISEASE_ALIAS_POLICY}}", source_disease_alias_policy()
    )
    unresolved = sorted(
        set(part.split("}}", 1)[0] + "}}" for part in template.split("{{")[1:])
    )
    if unresolved:
        raise ValueError("unresolved prompt markers: " + ", ".join(unresolved))
    return template + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--phase", type=int, choices=(1, 2, 3, 4, 5))
    mode.add_argument("--phase5-review", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    try:
        errors = vocabulary_errors()
        if errors:
            raise ValueError("\n".join(errors))
        if args.phase5_review:
            destination = args.output or ROOT / "prompts" / "phase5_review_prompt.md"
            content = render_phase5_review()
        else:
            destination = args.output or ROOT / "prompts" / f"phase{args.phase}_prompt.md"
            content = render(args.phase)
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(content, encoding="utf-8")
    except (OSError, ValueError, KeyError, json.JSONDecodeError) as exc:
        sys.exit(f"PROMPT BUILD FAILED:\n{exc}")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
