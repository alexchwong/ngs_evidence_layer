# Dublin blinded evaluation workflow

This workflow builds a source-blinded set of Dublin reports, keeps the private source mapping in a CSV, and creates a separate blinded CSV for manual marking in Excel.

## Files

- `scripts/hash_batch_dublin.py` — imports a complete 10-case NEL Dublin batch or ChatGPT Dublin zip/folder and writes randomly named blinded reports.
- `scripts/make_dublin_marking_sheet.py` — creates the manual marking CSV from the blinded report filenames only.
- `validation/chatgpt_dublin_batch_prompt.md` — reusable ChatGPT prompt containing all 10 Dublin case stems and instructions to return `case-1.md` through `case-10.md` plus `source_manifest.json`.
- `evaluation/blinded/` — generated blinded reports. Reports are named `<8-hex>-case-N.md`.
- `evaluation/hash_index.csv` — private unblinding key with columns `filename,profile,run #`.
- `evaluation/marking_sheet.csv` — generated manual marking sheet. This file appears after running the marking-sheet generator.

The repository `.gitignore` ignores `/evaluation/`, so blinded reports, the unblinding key, and entered marks remain local.

## 1. Add a completed NEL Dublin batch

Run from the repository root:

```bash
python scripts/hash_batch_dublin.py runs/<batch-folder>
```

The input must be a completed `nel-validate-dublin` batch containing all 10 cases and a `report-final.md` for each child run.

The script copies report text unchanged into `evaluation/blinded/`, assigns a random 8-hex prefix, keeps the Dublin case number visible, and appends 10 rows to `evaluation/hash_index.csv`.

For NEL batches, `profile` is taken from the batch `pipeline`, and `run #` is the batch ID.

## 2. Add a completed ChatGPT Dublin batch

Use `validation/chatgpt_dublin_batch_prompt.md` in the ChatGPT project. It asks ChatGPT to produce:

- `case-1.md` through `case-10.md`
- `source_manifest.json`
- a zip containing those 11 files

Then run:

```bash
python scripts/hash_batch_dublin.py chatgpt-dublin-<run>.zip
```

The script reads `profile` and `run` from `source_manifest.json`, creates the same blinded filenames, and appends them to the same private index.

## 3. Repeat until all comparison runs are imported

Each invocation appends another balanced set of 10 blinded reports. Do not rename the generated files: their filenames preserve the case identity needed for marking while hiding the source/model.

Keep `evaluation/hash_index.csv` closed and out of view while marking; it is the unblinding key.

## 4. Generate the Excel marking sheet

After all intended runs have been imported, run:

```bash
python scripts/make_dublin_marking_sheet.py
```

This reads only `evaluation/blinded/`; it deliberately does **not** read `hash_index.csv`.

It creates:

```text
evaluation/marking_sheet.csv
```

Rows are sorted by blinded filename ascending, matching alphabetical file-opening order. The sheet contains `filename`, `case`, the Dublin RxCy criterion columns, `total`, and `comments`. Applicable criteria are blank for manual entry; non-applicable criteria are `N/A`.

The generator checks that every Dublin case has the same number of blinded reports and that the canonical Dublin criteria are contiguous within each rubric. It refuses to overwrite an existing non-empty marking sheet by default.

If you intentionally want to discard and rebuild an existing marking sheet:

```bash
python scripts/make_dublin_marking_sheet.py --force
```

Avoid `--force` after entering marks.

## Suggested marking sequence

1. Import all NEL and ChatGPT batches with `hash_batch_dublin.py`.
2. Confirm the expected number of reports exists in `evaluation/blinded/`.
3. Generate `evaluation/marking_sheet.csv` once.
4. Open the CSV in Excel.
5. Open reports alphabetically and enter marks into the corresponding CSV row.
6. Keep `evaluation/hash_index.csv` hidden until marking is complete.
7. Unblind only after the marks are final.

## Important safeguards

- `hash_batch_dublin.py` requires exactly 10 Dublin cases per input batch.
- Blinded reports are copied without sanitising or rewriting their contents.
- Hash-prefix collisions are checked against both existing blinded files and the index.
- `make_dublin_marking_sheet.py` refuses imbalanced case counts.
- The marking sheet generator does not access provenance data.
- `/evaluation/` is gitignored because it contains the unblinding key and human-entered evaluation data.
