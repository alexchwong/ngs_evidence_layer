# Batch processing

Batch v1 is implemented by the root `nel.py` facade. The CLI and browser call the same batch setup, execution, status, resume and deletion paths; clinical workflow code remains single-case.

## Run layout

Run type is explicit and mandatory:

```text
runs/
├── <single-run>/
│   ├── run.json
│   └── ...
└── <batch-id>/
    ├── batch.json
    ├── batch-state.json
    ├── batch-source.md          # free-text batches only
    ├── 001-case-1/
    │   ├── run.json
    │   └── ...
    └── 002-case-2/
        ├── run.json
        └── ...
```

Folders without `run.json` or `batch.json` are unsupported legacy run layouts. `run-config/manifest.json` remains the frozen configuration/provenance record; `run.json` owns run identity and filesystem layout.

## Free-text batches

Every case must start with a Markdown H1 of the exact form `# Case <title>`:

```markdown
# Case 1
Clinical case text.

# Case 2
Clinical case text.
```

Malformed input hard-fails with a deterministic message. Content before the first case, missing titles, empty cases and duplicate titles are rejected.

```bash
python nel.py batch setup --mode ngs-report --case cases.md --pipeline lmstudio
python nel.py batch run --run-id <batch-id>
python nel.py batch status --run-id <batch-id>
```

## Bundled batches

The browser uses an explicit compact **Batch** toggle for both **Freetext** and **Examples**. With Batch mode off, the existing single-case selector is used. With Batch mode on, one bundled series is selected and its cases are chosen from a compact multi-select dropdown with tickboxes; the closed control shows the selected-case count and the dropdown stays open while ticking multiple cases. Changing series clears the selection. The preview has its own selector so each selected source case can be inspected before preparation. Demo and validation series both use comma-delimited `--case-ids` in the CLI.

Validation example:

```bash
python nel.py batch setup \
  --mode nel-validate-brief \
  --case-ids 1,2,5 \
  --pipeline openrouter
```

Demo example:

```bash
python nel.py batch setup \
  --mode nel-demo \
  --case-ids 1,2,5 \
  --pipeline lmstudio
```

## Validation marking

Automatic validation marking is optional and off by default for newly prepared batches. Enable it only when wanted:

```bash
python nel.py batch setup \
  --mode nel-validate-dublin \
  --case-ids 1,2,3 \
  --pipeline openrouter \
  --mark-validation
```

Whether marking is enabled or disabled is frozen into the batch and child run configuration. When it is disabled, the batch becomes clinically complete as soon as the clinical children are complete; unperformed marking does not turn it into `marking_incomplete`.

Mark a completed validation batch later with:

```bash
python nel.py mark --run-id <batch-id>
```

Each eligible child is marked in a separate `nel.py mark` subprocess. This deliberately prevents evaluator context from carrying between validation cases.

A validation batch has one external-marking deliverable at its root:

```text
runs/<batch-id>/validation-marking-bundle.zip
```

The ZIP is designed for direct upload to ChatGPT with a minimal instruction to follow `MARKING_INSTRUCTIONS.md`. It contains one isolated directory per completed case. Each case directory contains only its marking prompt, validation case and final report. Historical per-child validation ZIPs are removed after the batch bundle represents that child. Dublin bundles additionally contain `F1-F9-SCORING.md` and `dublin-functional-criteria.md`; F1-F9 are calculated only after all cases have been independently marked.

The browser exposes the same behavior: marking is an opt-in checkbox during preparation and a separate **Mark** / **Retry marking** action after clinical completion.

## Parallelism

`execution.max_parallel_cases` in the selected pipeline YAML is the batch concurrency ceiling. Shipped defaults are:

- LM Studio: `1` (local execution is always forced serial)
- OpenRouter: `4`

Each case is a separate `nel.py run` subprocess and keeps its own logs and checkpoints.

## Failure, blocking and resume

A terminal case/workflow failure after its normal validation/repair budget is exhausted is marked `failed` and `retry_eligible`. It does not stop other independent children. A finished batch containing these failures is `complete_with_errors`.

Running a `complete_with_errors` batch again selects only retry-eligible failed children. The same child run folder is reused and ordinary `nel.py run` is invoked. The clinical workflow remains authoritative for checkpoint validation and therefore resumes from its existing failed checkpoint rather than the batch scheduler guessing which upstream artifacts are reusable.

Provider/infrastructure failures are different. Failure to reach LM Studio/OpenRouter, authentication/service errors, rate limiting and equivalent provider outages mark the batch `blocked`; they do not consume or create case-level retry eligibility. Provider preflight blocks before any child starts. If provider failure is detected during execution, new children stop being scheduled and affected active children preserve their existing checkpoint state. After connectivity is restored, **Resume batch** continues non-complete children.

A user-stopped batch likewise resumes every non-complete child. A complete batch has no clinical work to restart. Marking retries use the separate `mark` action rather than reopening clinical execution.

## Legacy development runs

Folders without `run.json` or `batch.json` are not runnable or resumable. They remain visible in `nel.py runs` and in the browser as cleanup-only legacy folders, and may be deleted normally.

## Browser batch navigation and progress

A prepared or running batch remains expandable in the left run tree. The Case pane contains the single canonical batch-case selector; choosing a child updates the Case, Report and Dissent views. Clicking a left-tree child or active progress row updates the same selector. Active children are shown as one progress row per concurrent case. Single-case runs use the same component as one labelled progress row. The segmented rail is stage-based and uses the workflow stage list exposed by the backend rather than estimating elapsed-time percentages; the current workflow phase is shown explicitly beside the rail.

The left run tree scrolls independently and uses compact typography aligned with the reading panes. While any child of a running batch is selected, the primary execution control still targets the batch parent and remains **Stop batch**.
