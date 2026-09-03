# Validation suites

NEL exposes the canonical `proforma-v1` validation modes through the root `nel.py` CLI. Marking criteria are withheld until report generation is complete.

## Standard validation

Use `nel-validate` with one of the legacy validation-suite case IDs:

`1A`, `1B`, `1C`, `1D`, `1E`; `2A`, `2B`, `2C`, `2D`, `2E`;
`3A`, `3B`, `3C`, `3D`; `4A`, `4B`, `4C`, `4D`; `5A`, `5B`, `5C`, `5D`.

Example:

```bash
python nel.py setup --mode nel-validate --case-id 1A --run-id validate-1A
python nel.py run --run-id validate-1A
```

The source cases are in `validation/case_summary.md`.

## Function-targeted validation

`nel-validate-function` uses `validation/case_functional.md`.

Available IDs are `1A`-`1H` (AML), `2A`-`2G` (MDS with 12% blasts), `3A`-`3G`
(thrombocytosis/leukocytosis without marrow), and `4A`-`4D` (miscellaneous).

`validation/case_functional_manifest.md` documents the reporting function isolated by each functional case. It is evaluator/developer-only and is never supplied to the report-generation model or included in the external marking ZIP.

## Brief regression suite

`nel-validate-brief` uses `validation/validation_brief.md` and contains cases `1` through `10`. It is intended for high-yield end-to-end regression rather than exhaustive gene/disease content coverage.

Example:

```bash
python nel.py setup --mode nel-validate-brief --case-id 1 --run-id brief-1
python nel.py run --run-id brief-1
```

For a `self` pipeline, repeat `python nel.py run --run-id <id>` after completing each returned model handoff until `STATUS=complete`.

## Dual-pathology validation

`nel-validate-dual` uses `validation/validate_dual.md` and contains cases `1` through `6`. These cases test discordance between the morphological diagnosis and a molecular finding suggesting a concurrent pathology.

Example:

```bash
python nel.py setup --mode nel-validate-dual --case-id 1 --run-id dual-1
python nel.py run --run-id dual-1
```

## Dublin molecular-haematology validation

`nel-validate-dublin` uses `validation/validation_dublin.md` and contains cases `1` through `10`. It covers diagnostic integration and refinement, concurrent diagnoses, prognosis, therapy, MRD, germline predisposition, and disease-specific molecular prognostic frameworks.

The suite is available in both the canonical `proforma-v1` workflow and legacy `terraced-v6`:

```bash
python nel.py setup --mode nel-validate-dublin --case-id 1 --run-id dublin-1
python nel.py run --run-id dublin-1

python nel.py setup --legacy --mode nel-validate-dublin --case-id 1 --run-id legacy-dublin-1
python nel.py run --run-id legacy-dublin-1
```

Only clinical information is supplied during report generation. The task and case-specific marking criteria remain evaluator-only until `report-final.md` is complete.
