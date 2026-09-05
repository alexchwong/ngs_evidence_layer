# Validation suites

NEL exposes canonical `proforma-v1` validation suites through the root `nel.py` CLI. Validation-suite registration is data-driven: canonical Markdown files under `validation/` declare their public suite ID and cases, and `validation/case_registry.py` discovers them automatically.

List the currently registered suites and case IDs with:

```bash
python validation/case_registry.py list
```

Run any discovered case with:

```bash
python nel.py setup \
  --mode <registered-validation-suite> \
  --case-id <case-id> \
  --run-id <run-id>
python nel.py run --run-id <run-id>
```

For a `self` pipeline, repeat `python nel.py run --run-id <run-id>` after completing each returned model handoff until `STATUS=complete`.

The filename that contains a suite is not part of the public runtime contract. Dropping a new canonical validation Markdown file into `validation/` makes it available to canonical `proforma-v1`, root `nel.py`, the UI, and the root SKILL path without adding a Python mapping.

Only the case's `### Case summary` is supplied during report generation. `### Marking criteria` are evaluator-only and must remain unavailable to report-generation models until `report-final.md` is complete.

## Optional validation marking

Validation marking is **off by default** for newly prepared runs and batches. Clinical completion does not wait for marking unless automatic marking was explicitly enabled at setup.

Enable automatic post-report marking for a new validation run with:

```bash
python nel.py setup \
  --mode <registered-validation-suite> \
  --case-id <case-id> \
  --pipeline <pipeline> \
  --run-id <run-id> \
  --mark-validation
```

For a batch, add the same flag to `python nel.py batch setup ...`.

A completed validation run or batch can be marked later without rerunning the clinical workflow:

```bash
python nel.py mark --run-id <run-id-or-batch-id>
```

For batches, marking is performed one child at a time in separate processes so evaluator context cannot leak between cases. A batch-level `validation-marking-bundle.zip` is written at the batch root. It contains isolated case directories plus `MARKING_INSTRUCTIONS.md`; individual child marking ZIPs are removed after the batch bundle is built. Dublin bundles also contain `F1-F9-SCORING.md` and the canonical functional mapping needed to calculate F1-F9 after independent case marking.

The browser exposes the same policy: **Automatically mark validation result** is opt-in during preparation, and completed validation items have a separate **Mark** / **Retry marking** action.

Legacy validation manifests created before the policy field existed retain the former automatic-marking behavior when resumed. New setups always freeze an explicit on/off value.

After report completion, `validation/scripts/package_marking.py` builds external-marking bundles through the same central registry. A single-run bundle contains the candidate report, standalone validation case, and rendered marking prompt.

For the canonical Markdown schema, strict structural rules, and fair-marking requirements—including the prohibition on compound criteria—see [`../validation/DEVEL.md`](../validation/DEVEL.md).

`nel-demo` is a separate demonstration asset and is intentionally outside the validation-suite registry. Legacy `terraced-v6` retains only its explicitly supported historical validation modes; automatic registry expansion applies to canonical `proforma-v1`.
