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

After report completion, `validation/scripts/package_marking.py` builds the external-marking bundle through the same central registry. The bundle contains the candidate report, standalone validation case, and rendered marking prompt.

For the canonical Markdown schema, strict structural rules, and fair-marking requirements—including the prohibition on compound criteria—see [`../validation/DEVEL.md`](../validation/DEVEL.md).

`nel-demo` is a separate demonstration asset and is intentionally outside the validation-suite registry. Legacy `terraced-v6` retains only its explicitly supported historical validation modes; automatic registry expansion applies to canonical `proforma-v1`.
