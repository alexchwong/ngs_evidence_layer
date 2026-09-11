# Dublin blinded evaluation workflow

This workflow builds a source-blinded set of Dublin reports, groups reports by Dublin case for efficient manual review, keeps the private source mapping in a CSV, and creates a separate blinded CSV for marking in Excel.

## Files and layout

- `scripts/hash_batch_dublin.py` — imports a complete 10-case NEL Dublin batch or ChatGPT Dublin zip/folder and writes randomly named blinded reports into case-specific folders.
- `scripts/make_dublin_marking_sheet.py` — creates the manual marking CSV from the blinded report folders and filenames only.
- `validation/chatgpt_dublin_batch_prompt.md` — reusable ChatGPT prompt containing all 10 Dublin case stems and instructions to return `case-1.md` through `case-10.md` plus `source_manifest.json`.
- `evaluation/hash_index.csv` — private unblinding key with columns `filename,profile,run #`.
- `evaluation/marking_sheet.csv` — generated manual marking sheet. This file appears after running the marking-sheet generator.

Blinded reports are arranged as:

```text
evaluation/blinded/
  case-1/
    <8-hex>-case-1.md
    <8-hex>-case-1.md
    ...
  case-2/
    <8-hex>-case-2.md
    ...
  ...
  case-10/
    <8-hex>-case-10.md
    ...
```

The repository `.gitignore` ignores `/evaluation/`, so blinded reports, the unblinding key, and entered marks remain local.

## 1. Add a completed NEL Dublin batch

Run from the repository root:

```bash
python scripts/hash_batch_dublin.py runs/<batch-folder>
```

The input must be a completed `nel-validate-dublin` batch containing all 10 cases and a `report-final.md` for each child run.

The script copies report text unchanged. Each report receives a random 8-hex prefix and is written into the folder for its Dublin case. For example, a blinded Case 3 report becomes:

```text
evaluation/blinded/case-3/a1b2c3d4-case-3.md
```

The script also appends 10 rows to `evaluation/hash_index.csv`. The index keeps the existing schema:

```text
filename,profile,run #
```

Only the blinded basename is stored in `filename`; the case folder is deterministically recoverable from the `-case-N` suffix. For NEL batches, `profile` is taken from the batch `pipeline`, and `run #` is the batch ID.

## 2. Add a completed ChatGPT Dublin batch

Use `validation/chatgpt_dublin_batch_prompt.md` in the ChatGPT project. It asks ChatGPT to produce:

- `case-1.md` through `case-10.md`
- `source_manifest.json`
- a zip containing those 11 files

Then run:

```bash
python scripts/hash_batch_dublin.py chatgpt-dublin-<run>.zip
```

The script reads `profile` and `run` from `source_manifest.json`, writes each blinded report into the matching `evaluation/blinded/case-N/` folder, and appends the private provenance rows to the same index.

## 3. Repeat until all comparison runs are imported

Each genuinely new run appends another balanced set of 10 blinded reports: one into each `case-N` folder.

The importer is idempotent for a given `profile + run # + case`. If you accidentally run the same import command again, already-indexed cases are skipped and no new hashes, report copies, or index rows are created. This also works if the same run has already been duplicated by an older version: the importer will recognise that the run/case is already present and will not add another copy. It does not automatically delete historical duplicates.

As a safety check, if `hash_index.csv` says a run/case was imported but the corresponding blinded file is missing from its expected `case-N` folder, the import fails rather than silently generating a replacement.

Do not rename or move generated reports. Keep `evaluation/hash_index.csv` closed and out of view while marking; it is the unblinding key.

## 4. Remove a previously imported run

To remove one imported run, point the same script at the original NEL batch directory or ChatGPT export directory/zip and add `--remove`:

```bash
python scripts/hash_batch_dublin.py runs/<batch-folder> --remove
```

For a ChatGPT export:

```bash
python scripts/hash_batch_dublin.py chatgpt-dublin-<run>.zip --remove
```

Removal uses the source directory/manifest only to recover the run identity (`profile + run #`). It then removes **all** matching records for that run from:

- `evaluation/hash_index.csv`;
- the blinded Markdown reports under `evaluation/blinded/case-N/`;
- `evaluation/marking_sheet.csv`, when that sheet exists.

This is deliberately duplicate-aware. If an older version of the importer accidentally created multiple blinded copies for the same run/case, every matching indexed copy and every matching marking-sheet row is removed in one operation.

The removal fails closed if an indexed report that should be deleted is missing from its expected case folder. It does not infer or delete unrelated files. If the marking sheet has not yet been generated, removal still updates the index and blinded reports normally. Running the same removal command again is a safe no-op and reports `STATUS=NOT_IMPORTED`.

Custom paths can be supplied when needed:

```bash
python scripts/hash_batch_dublin.py runs/<batch-folder> --remove \
  --output-dir evaluation/blinded \
  --index evaluation/hash_index.csv \
  --marking-sheet evaluation/marking_sheet.csv
```

## 5. Generate the Excel marking sheet

After all intended runs have been imported, run:

```bash
python scripts/make_dublin_marking_sheet.py
```

This reads only the case folders under `evaluation/blinded/`; it deliberately does **not** read `hash_index.csv`.

It creates:

```text
evaluation/marking_sheet.csv
```

Rows are ordered for case-by-case marking:

1. all `case-1` reports, sorted alphabetically by blinded filename;
2. all `case-2` reports, sorted alphabetically by blinded filename;
3. continue through `case-10`.

This means you can open `evaluation/blinded/case-1/`, mark every report alphabetically against the consecutive Case 1 rows in Excel, then move to `case-2/`, and so on.

The sheet contains `filename`, `case`, the Dublin RxCy criterion columns, `total`, and `comments`. Applicable criteria are blank for manual entry; non-applicable criteria are `N/A`.

The generator checks that:

- every `case-1` through `case-10` folder exists;
- every report is in the folder matching the case number in its filename;
- every Dublin case has the same number of blinded reports;
- the canonical Dublin criteria are contiguous within each rubric.

It refuses to overwrite an existing non-empty marking sheet by default.

If you intentionally want to discard and rebuild an existing marking sheet:

```bash
python scripts/make_dublin_marking_sheet.py --force
```

Avoid `--force` after entering marks.

## Suggested marking sequence

1. Import all NEL and ChatGPT batches with `hash_batch_dublin.py`.
2. If a run was imported in error, remove it with the same input path plus `--remove`.
3. Confirm the expected number of reports is present in each `evaluation/blinded/case-N/` folder.
4. Generate `evaluation/marking_sheet.csv` once.
5. Open the CSV in Excel.
6. Open `evaluation/blinded/case-1/` and mark reports alphabetically against the consecutive Case 1 rows.
7. Repeat for Cases 2 through 10.
8. Keep `evaluation/hash_index.csv` hidden until marking is complete.
9. Unblind only after the marks are final.

## Important safeguards

- `hash_batch_dublin.py` requires exactly 10 Dublin cases per input batch.
- Blinded reports are copied without sanitising or rewriting their contents.
- Hash-prefix collisions are checked across all case folders and the private index.
- Re-importing the same `profile + run # + case` is idempotent: existing entries are skipped rather than duplicated.
- `--remove` deletes all indexed copies for the selected `profile + run #`, including historical duplicates, and removes matching marking-sheet rows.
- Indexed reports must still exist in their expected case folder; otherwise import fails closed.
- `make_dublin_marking_sheet.py` rejects reports placed in the wrong case folder.
- `make_dublin_marking_sheet.py` refuses imbalanced case counts.
- The marking sheet generator does not access provenance data.
- `/evaluation/` is gitignored because it contains the unblinding key and human-entered evaluation data.

## Existing flat-layout reports

This version expects the case-folder layout above. If you already have blinded reports directly under `evaluation/blinded/` from the earlier version, move each file into the folder matching its `-case-N` suffix before generating a new marking sheet. The private `hash_index.csv` does not need modification because it stores only the basename.
