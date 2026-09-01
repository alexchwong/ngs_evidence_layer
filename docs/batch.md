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

The browser uses an explicit **Batch mode** toggle for both free text and bundled cases. With Batch mode off, the existing single-case selector is used. With Batch mode on, one bundled series is selected and its cases are shown as checkboxes; changing series clears the selection. Demo and validation series both use comma-delimited `--case-ids` in the CLI.

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

## Parallelism

`execution.max_parallel_cases` in the selected pipeline YAML is the batch concurrency ceiling. Shipped defaults are:

- LM Studio: `1` (local execution is always forced serial)
- OpenRouter: `4`

Each case is a separate `nel.py run` subprocess and keeps its own logs and checkpoints.

## Failure and resume

A child failure does not stop other children. A finished batch with failures is `complete_with_errors`.

Running that batch again selects only children whose batch state is `failed`. The same child run folder is reused and ordinary `nel.py run` is invoked. The clinical workflow remains authoritative for checkpoint validation and therefore resumes from its existing failed checkpoint rather than the batch scheduler guessing which upstream artifacts are reusable.

A stopped batch resumes every non-complete child. A complete batch has no work to restart.

## Legacy development runs

Folders without `run.json` or `batch.json` are not runnable or resumable. They remain visible in `nel.py runs` and in the browser as cleanup-only legacy folders, and may be deleted normally.
