#!/usr/bin/env python3
"""Self-contained deterministic validation for the Phase 1 census product."""
import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

METADATA_SCHEMA = json.loads(r'''{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://local/ngs_evidence_layer/metadata_schema.json","title":"Publication metadata","description":"Publication metadata used in working and archived packages. Confirmation overwrite history is optional for working-package compatibility.","type":"object","required":["schema_version","paper_id","corpus","stem","publication_key","citation","citation_source","citation_resolved_at","source_filename","source_sha256","markdown_sha256","created_at"],"additionalProperties":false,"properties":{"schema_version":{"const":"1.1"},"paper_id":{"type":"string","format":"uuid"},"corpus":{"type":"string","minLength":1},"stem":{"type":"string","minLength":1},"publication_key":{"type":"string","pattern":"^[a-z0-9]+(-[a-z0-9]+)*$"},"citation":{"$ref":"#/$defs/citation"},"citation_source":{"enum":["crossref-doi","model-supplied-doi","operator"]},"citation_resolved_at":{"anyOf":[{"type":"string","format":"date-time"},{"type":"null"}]},"source_filename":{"type":"string","minLength":1},"source_sha256":{"type":["string","null"],"pattern":"^[a-f0-9]{64}$"},"markdown_sha256":{"type":"string","pattern":"^[a-f0-9]{64}$"},"created_at":{"type":"string","format":"date-time"},"version_history":{"type":"array","minItems":1,"uniqueItems":true,"items":{"type":"string","minLength":1}},"latest_version":{"type":"string","minLength":1}},"$defs":{"citation":{"type":"object","required":["authors","title","journal","year","volume","issue","pages","doi","display","citation_incomplete"],"additionalProperties":false,"properties":{"authors":{"type":"array","minItems":1,"items":{"type":"string","minLength":1}},"title":{"type":"string","minLength":1},"journal":{"type":"string"},"year":{"type":"integer","minimum":1950,"maximum":2100},"month":{"type":"string"},"volume":{"type":"string"},"issue":{"type":"string"},"pages":{"type":"string"},"doi":{"type":"string"},"display":{"type":"string","minLength":1},"citation_incomplete":{"type":"array","uniqueItems":true,"items":{"type":"string","minLength":1}}}}}}''')
CENSUS_SCHEMA = json.loads(r'''{"$schema":"https://json-schema.org/draft/2020-12/schema","$id":"https://local/ngs_evidence_layer/census_schema.json","title":"Publication census (Phase 1)","description":"One entry per gene about which the publication makes a claim. The census is the completeness contract: it is what makes under-extraction countable.","type":"object","required":["schema_version","paper_id","census_date","census_model","publication_type","publication_type_basis","entries","geneless_statements","validation_unresolved"],"additionalProperties":false,"properties":{"schema_version":{"const":"3.1"},"paper_id":{"type":"string","format":"uuid"},"census_date":{"type":"string","format":"date"},"census_model":{"type":"string","minLength":1},"publication_type":{"enum":["guideline","consensus statement","primary study","systematic review","narrative review","other"]},"publication_type_basis":{"type":"string","minLength":1},"supplement_flags":{"type":"array","description":"Critical values referenced by the main text but living in supplementary material. Record, do not refuse.","items":{"type":"object","required":["locator","missing_value"],"additionalProperties":false,"properties":{"locator":{"type":"string"},"missing_value":{"type":"string"}}}},"entries":{"type":"array","minItems":1,"items":{"type":"object","required":["entry_id","gene","locators","categories"],"additionalProperties":false,"properties":{"entry_id":{"type":"string","minLength":1},"gene":{"type":"string","pattern":"^[A-Z0-9][A-Z0-9\\-]*$"},"locators":{"type":"array","minItems":1,"description":"Sections, tables and table footnotes where the publication makes a claim about this gene.","items":{"type":"string","minLength":1}},"categories":{"type":"array","minItems":1,"items":{"enum":["diagnosis","prognosis","treatment","biomarker","germline"]}}}}},"geneless_statements":{"type":"array","description":"Rule-relevant statements with no gene attached. Recorded for visibility, not for carding.","items":{"type":"object","required":["locator","summary"],"additionalProperties":false,"properties":{"locator":{"type":"string","minLength":1},"summary":{"type":"string","minLength":1}}}},"validation_unresolved":{"type":"array","description":"Specific Phase 1 exit-validation defects still unresolved after the third pass.","items":{"type":"string","minLength":1}}}}''')


def read_json(path, label="JSON"):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except OSError as exc:
        raise ValueError(f"cannot read {label} {path}: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid {label} in {path}: {exc}") from exc


def schema_errors(document, schema, label):
    errors = sorted(
        Draft202012Validator(schema, format_checker=FormatChecker()).iter_errors(document),
        key=lambda error: list(error.absolute_path),
    )
    return [
        f"{label} schema: {'/'.join(str(p) for p in error.absolute_path) or '<root>'}: "
        f"{error.message}" for error in errors
    ]


def validate_metadata(metadata):
    return schema_errors(metadata, METADATA_SCHEMA, "metadata")


def validate_census(census, metadata=None):
    errors = schema_errors(census, CENSUS_SCHEMA, "census")
    entry_ids = [entry.get("entry_id") for entry in census.get("entries", [])]
    genes = [entry.get("gene") for entry in census.get("entries", [])]
    if len(entry_ids) != len(set(entry_ids)):
        errors.append("census contains duplicate entry_id values")
    if len(genes) != len(set(genes)):
        errors.append("census contains duplicate gene entries")
    if metadata and census.get("paper_id") != metadata.get("paper_id"):
        errors.append("census paper_id does not match metadata")
    return errors


def validate_phase_files(*, metadata_path, census_path):
    metadata = read_json(metadata_path, "metadata")
    census = read_json(census_path, "census")
    errors = [f"metadata: {error}" for error in validate_metadata(metadata)]
    errors.extend(f"census: {error}" for error in validate_census(census, metadata))
    return errors, [], {"phase": 1, "census_entries": len(census.get("entries", []))}


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--census", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    try:
        errors, warnings, report = validate_phase_files(
            metadata_path=args.metadata, census_path=args.census
        )
    except (OSError, ValueError) as exc:
        sys.exit(f"PHASE 1 VALIDATION FAILED:\n{exc}")
    if errors:
        sys.exit("PHASE 1 VALIDATION FAILED:\n" + "\n".join(errors))
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    print(json.dumps({"valid": True, **report}, sort_keys=True))


if __name__ == "__main__":
    main()
