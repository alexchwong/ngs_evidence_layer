# Validation development guide

Bundled demo and validation cases are repository-owned test assets. Runtime retrieval is deliberately centralised so cases cannot leak evaluator material and workflows do not acquire suite-specific parsers or paths.

## Single source of truth

`validation/scripts/bundled_cases.py` owns:

- public bundled modes and their backing Markdown files;
- selector normalisation and case listing;
- clinical case retrieval;
- marking-criteria retrieval;
- validation marking-ZIP naming.

Workflow code must never hard-code bundled Markdown filenames or parse suite files itself. Every workflow fetches bundled clinical input through `retrieve_case_input(mode, selector)`.

## Confidentiality boundary

Before report completion, runtime code may retrieve only the clinical case. `retrieve_case_input()` excludes both `NEL task` and `Marking criteria`.

Marking criteria are evaluator-only. Retrieve them through `retrieve_marking_criteria()` only after `report-final.md` exists. `nel-demo` may materialise `demo-expected.md` only through `write_demo_marking_criteria_after_report()`. Validation marking ZIPs must be created with `package_marking_bundle()` from a completed, non-empty report.

Clinical facts required to solve a case belong in `Clinical information`, never only in the task or criteria. The task states requested reporting behavior. Criteria describe evaluator expectations without adding hidden clinical facts.

## Case-file formats

### Standalone cases

Use this exact heading hierarchy:

```markdown
# Case 1 — Optional title

## Clinical information

Clinical facts supplied to the reporting workflow.

## NEL task

Evaluator-authored description of the behavior under test.

## Marking criteria

Evaluator-only expectations.
```

Separate cases with `---`. Optional suite material after the cases must begin with `# Source notes` so it cannot become part of the final case's criteria.

### Existing shared-stem suites

Existing suites may use `# Case N`, followed by `## Shared stem` and `## Case NA` variants. Each variant uses `### Clinical information`, `### NEL task`, and `### Marking criteria`. Do not introduce a new heading shape without extending the central parser and its tests.

## Add cases to an existing suite

1. Add correctly structured cases to the suite Markdown file.
2. Do not edit workflow runtime code.
3. Confirm selectors and retrieval:

   ```bash
   .env/bin/python validation/scripts/retrieve_cli.py list --mode <mode>
   .env/bin/python validation/scripts/retrieve_cli.py case <ID> --mode <mode>
   ```

4. Confirm the clinical output contains neither the task nor marking criteria.
5. Update expected selector coverage in `tests/test_validation_cases.py` when the suite has an asserted fixed range.

## Add a new bundled suite

1. **Add the Markdown asset** under `validation/` using one of the supported formats.
2. **Register one `SuiteSpec`** in `validation/scripts/bundled_cases.py` with its public mode, source filename, marking-ZIP prefix, and selector flag. Validation modes must begin with `nel-validate`.
3. **Choose workflow exposure** by adding the public mode to `supported_modes` in each intended `workflow.json`:
   - `workflows/proforma_v1/workflow.json` exposes the canonical root CLI and browser UI;
   - `workflows/terraced_v6/workflow.json` exposes `python nel.py setup --legacy`.
4. **Do not add suite-specific setup code.** Workflow runtime hooks already receive the public mode and selector and call the central retrieval API.
5. **Add a UI label** to both `ui/batch_server.py` and `ui/enhancements.py`. UI discovery remains driven by the registry and canonical workflow support.
6. **Update user documentation** in `validation/README.md`, `docs/validation.md`, root `README.md`/`SKILL.md`, and the documentation for every workflow that exposes the mode.
7. **Update `release/skill.txt`** so the suite is present in the distributed runtime package.
8. **Add regression tests** described below.

Root `nel.py` derives canonical mode choices from `proforma-v1` metadata and validates legacy choices against `terraced-v6` metadata at execution time. A new suite should not require a mode-specific branch in `nel.py`.

## Required regression coverage

Tests must verify:

1. the registry lists the expected selectors and resolves the expected source;
2. every production selector retrieves non-empty clinical and marking content;
3. clinical retrieval never includes `NEL task`, `Marking criteria`, or suite-level source notes;
4. standalone suites reject variant selectors;
5. the marking ZIP has the canonical name and contains only `marking-prompt.md`, `validation-case.md`, and `report-final.md`;
6. every intended workflow advertises and sets up the mode through central retrieval;
7. root CLI and UI discovery expose the suite where intended;
8. workflow code and workflow documentation contain no bundled-source filename or legacy registry mapping.

Use repository unittests:

```bash
.env/bin/python -m unittest tests.test_validation_cases tests.test_package_marking
.env/bin/python -m unittest tests.test_nel_cli tests.test_ui_server
```

Also smoke-test both root paths when both workflows support the suite:

```bash
.env/bin/python nel.py setup --mode <mode> --case-id <ID> --pipeline self --run-id <canonical-run>
.env/bin/python nel.py setup --legacy --mode <mode> --case-id <ID> --pipeline self --run-id <legacy-run>
```

Use temporary or disposable run IDs and remove smoke-test runs afterward. These checks are architectural regression guards: a failure means centralisation or evaluator isolation may have been bypassed even if one workflow appears to run.
