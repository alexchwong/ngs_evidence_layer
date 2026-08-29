# Validation assets

Bundled demo and validation cases are centralised under this folder.

- `demo.md` — the six repository demonstration cases, each with clinical information, an NEL task, and marking criteria.
- `case_summary.md` — general validation suite used by `nel-validate`.
- `case_functional.md` — function-targeted suite used by `nel-validate-function`.
- `validation_brief.md` — consolidated regression suite used by `nel-validate-brief`.
- `case_functional_manifest.md` — evaluator/developer-only index; never a runtime model input.
- `mark_validation_report.md` — template used for external validation marking bundles.
- `scripts/bundled_cases.py` — single source of truth for public mode → suite mapping, retrieval, selectors, and marking bundle names.
- `scripts/package_marking.py` — deterministic post-report marking ZIP builder.
- `scripts/retrieve_cli.py` — CLI wrapper around the same central retrieval API.
- `devel.md` — development contract for future case additions and workflow integration.

## Retrieval

Clinical content only:

```bash
python validation/scripts/retrieve_cli.py case 1 --mode nel-demo
python validation/scripts/retrieve_cli.py case 1A --mode nel-validate
python validation/scripts/retrieve_cli.py case 1A --mode nel-validate-function
python validation/scripts/retrieve_cli.py case 8 --mode nel-validate-brief
```

List selectors:

```bash
python validation/scripts/retrieve_cli.py list --mode nel-demo
python validation/scripts/retrieve_cli.py list --mode nel-validate-brief
```

Marking criteria are intentionally a separate post-report operation:

```bash
python validation/scripts/retrieve_cli.py MC 1A --mode nel-validate
```

Workflow setup must not use the `MC` action.

## External validation marking

After `report-final.md` exists:

```bash
python validation/scripts/package_marking.py 1A \
  --mode nel-validate \
  --report <work-dir>/report-final.md
```

The canonical output name is selected by `bundled_cases.py`. The ZIP contains exactly `marking-prompt.md`, `validation-case.md`, and `report-final.md`. Full debug packaging remains separate.
