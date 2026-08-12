#!/usr/bin/env python3
"""Render one committed, self-contained phase prompt from manifest-backed sources."""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MANIFEST_PATH = ROOT / "prompts" / "assets" / "manifest.json"
MARKER_RE = re.compile(r"\{\{([A-Z0-9_]+)\}\}")


def read(path):
    return path.read_text(encoding="utf-8").rstrip()


def repo_path(relative):
    path = (ROOT / relative).resolve()
    try:
        path.relative_to(ROOT.resolve())
    except ValueError as exc:
        raise ValueError(f"asset path escapes repository root: {relative}") from exc
    return path


def load_manifest():
    manifest = json.loads(read(MANIFEST_PATH))
    if not isinstance(manifest, dict) or not isinstance(manifest.get("assets"), dict):
        raise ValueError("prompt asset manifest must contain an 'assets' object")
    return manifest


def bundle_paths(spec):
    paths = []
    for relative in spec.get("paths", []):
        path = repo_path(relative)
        if not path.is_file():
            raise ValueError(f"bundle file does not exist: {relative}")
        paths.append(path)
    for pattern in spec.get("globs", []):
        matches = sorted(ROOT.glob(pattern))
        if not matches:
            raise ValueError(f"bundle glob matched no files: {pattern}")
        paths.extend(path.resolve() for path in matches if path.is_file())
    deduplicated = []
    seen = set()
    for path in paths:
        if path not in seen:
            seen.add(path)
            deduplicated.append(path)
    if not deduplicated:
        raise ValueError("bundle asset contains no files")
    return deduplicated


def fence_language(path):
    return {
        ".py": "python",
        ".json": "json",
        ".md": "markdown",
        ".txt": "text",
    }.get(path.suffix.lower(), "text")


def render_bundle(spec):
    lines = []
    for path in bundle_paths(spec):
        relative = path.relative_to(ROOT).as_posix()
        lines.extend(
            [
                f"<!-- BEGIN VERBATIM {relative} -->",
                f"```{fence_language(path)}",
                read(path),
                "```",
                f"<!-- END VERBATIM {relative} -->",
                "",
            ]
        )
    return "\n".join(lines).rstrip()


def asset_content(keyword, manifest=None):
    manifest = manifest or load_manifest()
    spec = manifest["assets"].get(keyword)
    if not isinstance(spec, dict):
        raise ValueError(f"unknown prompt asset: {keyword}")
    asset_type = spec.get("type")
    if asset_type == "file":
        relative = spec.get("path")
        if not isinstance(relative, str) or not relative:
            raise ValueError(f"file asset {keyword} has no path")
        path = repo_path(relative)
        if not path.is_file():
            raise ValueError(f"asset file does not exist: {relative}")
        return read(path)
    if asset_type == "bundle":
        return render_bundle(spec)
    raise ValueError(f"unsupported asset type for {keyword}: {asset_type!r}")


def template_markers(template):
    return list(dict.fromkeys(MARKER_RE.findall(template)))


def render_template(path):
    template = read(path)
    manifest = load_manifest()
    markers = template_markers(template)
    unknown = sorted(set(markers) - set(manifest["assets"]))
    if unknown:
        raise ValueError("unknown prompt markers: " + ", ".join(unknown))
    for keyword in markers:
        template = template.replace(
            "{{" + keyword + "}}", asset_content(keyword, manifest=manifest)
        )
    unresolved = sorted(set(MARKER_RE.findall(template)))
    if unresolved:
        raise ValueError("unresolved prompt markers: " + ", ".join(unresolved))
    return template


def vocabulary_errors():
    vocabulary = json.loads(read(ROOT / "schema" / "disease_vocabulary.json"))
    aliases = json.loads(read(ROOT / "schema" / "source_disease_aliases.json"))
    package = json.loads(read(ROOT / "schema" / "ingestion_package_schema.json"))
    expected = vocabulary["diseases"] if isinstance(vocabulary, dict) else vocabulary
    actual = package["$defs"]["disease"]["enum"]
    errors = [] if expected == actual else ["disease vocabulary and package schema enum differ"]
    if not isinstance(aliases, dict):
        errors.append("source disease aliases must be a JSON object")
    else:
        normalized = set()
        canonical_casefold = {disease.casefold() for disease in expected}
        for alias, target in aliases.items():
            if not isinstance(alias, str) or not alias.strip():
                errors.append("source disease aliases must be non-empty strings")
                continue
            normalized_alias = alias.strip().casefold()
            if normalized_alias in normalized:
                errors.append(
                    f"source disease alias {alias!r} duplicates another alias after normalization"
                )
            normalized.add(normalized_alias)
            if normalized_alias in canonical_casefold:
                errors.append(f"source disease alias {alias!r} collides with a canonical disease")
            if target not in expected:
                errors.append(
                    f"source disease alias {alias!r} targets non-canonical disease {target!r}"
                )
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


def render(phase):
    template = render_template(
        ROOT / "prompts" / "templates" / f"phase{phase}_prompt.md"
    )
    if phase == 3 and any(
        term in template
        for term in (
            "agreed_reporting_rules",
            '"diseases": [',
            '"$schema"',
        )
    ):
        raise ValueError("Phase 3 prompt contains forbidden authoring context")
    return template + "\n"


def render_phase5_review():
    return render_template(
        ROOT / "prompts" / "templates" / "phase5_review_prompt.md"
    ) + "\n"


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
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError) as exc:
        sys.exit(f"PROMPT BUILD FAILED:\n{exc}")
    print(f"wrote {destination}")


if __name__ == "__main__":
    main()
