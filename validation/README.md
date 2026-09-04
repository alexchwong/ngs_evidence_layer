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

## Automatic validation marking

Canonical `nel-validate-*` runs are automatically marked after `report-final.md` exists. The marker uses the frozen pipeline's `marking` model role and the same canonical criteria/prompt used by external marking. `nel-demo` is not automatically marked.

Automatic marking is a non-clinical sidecar: failure or staleness does not invalidate the completed clinical report. A later `nel.py run` may retry marking without regenerating the report. Current marking is bound to the SHA-256 of `report-final.md` and writes `marking.md` plus normalized `marking.json`.

The validation layer owns prompt rendering, response validation, hash binding and deterministic marking artifacts only. Model execution belongs to `workflows/proforma_v1/automatic_marking.py`, so validation code does not import or call workflow/provider executors.

For Dublin, the model still marks RxCy only. F1-F9 is generated deterministically afterwards into `functional.json` using `validation/docs/dublin_functional_criteria.md` and `validation/scripts/score_functional_dublin.py`.

Validation batches mark each child independently and deterministically aggregate them into `batch-marking.md` and `batch-marking.json`; there is no batch-marking LLM. See `validation/docs/automatic_marking.md` for the complete artifact/status contract.

## External validation marking

`validation/scripts/package_marking.py` builds the post-report external-marking ZIP. It retrieves both the frozen clinical case and the evaluator criteria through the central registry interface. The ZIP contains only:

- `marking-prompt.md`
- `validation-case.md`
- `report-final.md`

Do not expose marking criteria to the report-generation workflow before `report-final.md` is complete.

`nel-demo` remains a separate demonstration asset and is intentionally outside the validation-suite registry.
