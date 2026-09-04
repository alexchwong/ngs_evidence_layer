# Validation assets

Validation suites are self-registering canonical Markdown files under this directory. `validation/case_registry.py` discovers them from their front matter and supplies cases and evaluator-only marking criteria to runtime callers.

A new validation suite requires no Python mapping: add a canonical `.md` file, then run:

```bash
python validation/case_registry.py check
python validation/case_registry.py list
```

Use the public suite value and case ID with the reporting workflow, for example:

```bash
python nel.py setup --mode <registered-validation-suite> --case-id <case-id> --pipeline self
```

The filename is not part of the public contract. The current canonical files retain the existing public suite IDs while using one strict standalone-case format.

`validation/DEVEL.md` defines the complete schema and the mandatory fairness rules for authoring marking criteria. In particular, every RnCm criterion must be independently testable and must not combine multiple scorable obligations.

## External validation marking

`validation/scripts/package_marking.py` builds the post-report external-marking ZIP. It retrieves both the frozen clinical case and the evaluator criteria through the central registry interface. The ZIP contains only:

- `marking-prompt.md`
- `validation-case.md`
- `report-final.md`

Do not expose marking criteria to the report-generation workflow before `report-final.md` is complete.

`nel-demo` remains a separate demonstration asset and is intentionally outside the validation-suite registry.
