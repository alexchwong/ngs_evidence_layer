# proforma_v1 — Phase 3 declarative proforma workflow

`proforma_v1` is the configurable successor to `terraced_v6`. The selected
`workflow/*.yaml` is the canonical logical workflow; `step.py` and `self.py` are
execution adapters over the same compiled graph. `terraced_v6` remains the frozen
behavioural reference for components that Phase 3 does not intentionally change.

The shipped workflow is `workflow/default.yaml`. Both entrypoints accept
`--workflow <yaml>` for experiments with ordering, prompts, compatible proformas,
conditions, evidence policy and native-self batching. See `workflow/README.md` for
authoring examples and `DEVEL.md` for the complete default-YAML term reference.

## Phase 3 logical flow

The default workflow currently compiles to 24 logical operations:

```text
structure -> corpus -> WHO1 proposal -> assess routing change
    -> [blocking WHO1 diagnostic evidence when routing changes]
    -> commit accepted/fallback routing -> optional WHO2 -> ICC -> diagnosis.other
    -> diagnosis.finalize -> prognosis/treatment/biomarker/germline
    -> evidence rescue/audit/adjudication -> evidence.finalize
    -> report.blocks -> report.write -> report.preservation -> report.finalize
```

Native self may physically batch independent PTBG owner operations; provider
execution may issue them separately. Intentional executor-specific omissions are
declared in YAML. The default disables `report.preservation` for native self only.

## WHO routing

WHO1 first produces a proposal. A deterministic transform assesses whether the
proposal materially changes schema disease, diagnosis or routing CMCs. A routing
change must pass blocking `diagnosis_complete_support` evidence review before it
can alter downstream retrieval. Unsupported routing changes fall back
deterministically when a supplied morphologic routing state exists; rejected
routing is retained in dissent.

WHO2 reconsideration is controlled by:

```json
{
  "diagnosis": {
    "who5": {
      "reconsider_after_cmc_expansion": false
    }
  }
}
```

The default is `false`. Disabling WHO2 disables only reconsideration: an accepted
WHO1 routing/CMC change still drives ICC and PTBG retrieval.

## PTBG evidence ownership

Prognosis, treatment, biomarker and germline proformas may assign initial card tags
from the exact cards supplied to that owner step. Out-of-envelope tags reject that
owner artifact and are fed back to the same model step for repair. Python carries
valid tags through deterministic pivot/consolidation; equivalent merged
propositions take a stable union of their tags.

The dedicated evidence matcher is therefore a rescue mechanism for uncarded or
audit-rejected facts. Rescue pass count is workflow-configurable. Match inputs are
per-fact isolated blocks; audit sees only assigned cards. Audit-rejected cards are
excluded from later rescue candidates, and only unresolved disputes proceed to
cropped adjudication.

## Validation model

Structured model output flows through format parsing, JSON Schema, deterministic
runtime rules and registered transforms before an artifact commits. Complex
deterministic checks/transforms are allow-listed Python extensions; workflow YAML
may select them but cannot execute arbitrary code.

Clinical validation failures are fed back to the owning model operation as a
complete-artifact repair. Semantic audit failures use the bounded `review` routing
declared in the workflow.

## Validate and test

```bash
python workflows/proforma_v1/step.py workflow-check
python workflows/proforma_v1/step.py pipeline-check --pipeline self
python -m unittest discover -s workflows/proforma_v1/tests -p "test_*.py"
```

After changing proforma-v1's local settings or pipeline defaults, validate them without modifying root `config/`:

```bash
python workflows/proforma_v1/devel_sync.py --check
```

`proforma_v1` is not the promoted default workflow, so its developer tooling must not sync its defaults into root `config/`.

Phase 3 intentionally changes routing/evidence behaviour, so acceptance focuses on
clinical/evidence invariants. Replay equality remains useful for unchanged
components rather than serving as the sole Phase 3 oracle.
