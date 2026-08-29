# Validation development contract

Bundled demo and validation cases are repository-owned test assets. Their runtime retrieval is deliberately centralised so adding or reorganising cases does not require workflow-specific path logic.

## Single source of truth

`validation/scripts/bundled_cases.py` owns:

- public bundled modes and their backing Markdown files;
- selector normalisation and case listing;
- clinical case retrieval;
- marking-criteria retrieval;
- validation marking-ZIP naming.

Workflow code must never hard-code `demo.md`, `case_summary.md`, `case_functional.md`, or `validation_brief.md`, and must not parse those files itself. Every workflow must fetch bundled clinical input through `retrieve_case_input(mode, selector)`.

## Retrieval boundary

Before report completion, runtime code may retrieve only clinical case content. `retrieve_case_input()` intentionally excludes `NEL task` and `Marking criteria` sections.

Marking criteria are evaluator-only. They may be retrieved through `retrieve_marking_criteria()` only after `report-final.md` exists. `nel-demo` may materialise `demo-expected.md` only through `write_demo_marking_criteria_after_report()`, which enforces that boundary. Validation marking ZIPs are similarly created only from a completed report.

## Adding or changing cases

- Add a case to the appropriate Markdown suite; do not edit workflows.
- New standalone cases use `# Case N`, `## Clinical information`, `## NEL task`, and `## Marking criteria`.
- Existing shared-stem suites may continue to use `## Shared stem` plus `## Case NA` sections with `### Clinical information`, `### NEL task`, and `### Marking criteria`.
- Clinical facts belong only in clinical-information sections.
- Marking criteria describe evaluator expectations and must not add hidden clinical facts required to solve the case.
- Adding a new bundled suite requires one registry entry in `bundled_cases.py`, its Markdown file, public CLI exposure if appropriate, and tests. It should not require edits across workflow implementations.

## Workflow rule

Workflow-specific setup may decide where `case.md` lives, but not where a bundled source lives or how it is parsed. Runtime hooks receive the public mode and selector, call the central retrieval API, and write the returned clinical text into their existing layout.

## Required regression coverage

Tests must verify:

1. every registered suite lists and retrieves all production selectors;
2. clinical retrieval never includes `NEL task` or `Marking criteria`;
3. demo expected/marking material cannot be generated before a non-empty `report-final.md` exists;
4. validation marking ZIPs contain only the selected clinical case, rendered marking prompt, and final report;
5. all workflow runtime implementations use the central bundled-case API;
6. workflow code contains no direct bundled-source filenames, legacy example paths, `VALIDATION_CASE_FILES`, `DEMO_EXAMPLES`, or workflow-local `MARKING_PREFIX` mappings.

These tests are architectural regression guards: if one fails, centralisation has been bypassed even if an individual workflow still appears to run.
