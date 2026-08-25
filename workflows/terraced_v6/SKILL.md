# Terraced v6

Terraced-v6 has one shared clinical/proforma workflow and two execution engines.

## Provider routing

- No provider selector, or explicit `--self`: use `workflows/terraced_v6/self.py`. `self` is the default.
- Explicit non-self provider (`lmstudio`, `openrouter`, or another registered staged pipeline): use the existing `workflows/terraced_v6/step.py` path unchanged.
- Never emulate a non-self provider when executing `self`.

The existing files under `prompts/`, `stages/`, and `schemas/` are the shared clinical contracts. Self execution must use those same contracts; it changes model-pass grouping and permitted inputs, not the proformas.

## Self execution principle

You are the model executor. For every self model pass, directly read the file paths printed by `self.py`, perform the reasoning in the current session, and write the requested output file(s). Do not call another model or LLM API.

`self.py` performs deterministic setup, retrieval, identity, routing, critical structural validation, evidence comparison/adjudication cropping, citation/provenance and final rendering. It does not call a model. There is no routine syntax-repair or report-preservation model pass.

Card assignment is forbidden in owner proformas. Diagnosis/PTBG may read candidate cards as clinical source material, but no card becomes attached to a reason until evidence resolution. Leaked `card_tag`/`card_tags` fields or runtime tags in owner reasons are silently stripped before owner validation.

## Self pass topology

Routine model passes are:

1. **WHO1** — structure the raw case and perform the first WHO5 assessment in one continuous self reasoning pass. The deterministic interleave needed to create the variant registry and retrieve WHO cards does not start another model pass.
2. **ICC** — isolated ICC assessment. WHO1 is used only by Python to derive retrieval CMCs and is not exposed as model context.
3. **WHO2** — isolated second WHO5 assessment using the same shared WHO5 contract. It may receive a deterministic WHO card redraw triggered by CMCs discovered in WHO1. WHO1 and ICC conclusions are not exposed. WHO2 is authoritative WHO for all downstream routing/reporting.
4. **PTBG** — one model pass completes the four existing prognosis, treatment, biomarker/MRD and germline contracts and writes four normal model-classification artifacts.
5. **Evidence resolution** — one shared evidence-match pass assigns zero or more candidate cards to every reportable reason. This is the first card-assignment stage.
6. **Evidence audit** — one independent audit pass. For reasons with selected cards, audit those selected cards. For a resolver zero-card decision, audit the full deterministic candidate set to detect a false-negative no-support decision.
7. **Evidence adjudication** — conditional only. Python compares resolution and audit, crops only disagreements, and a short adjudicator decides include/exclude for each disputed reason/card pair. The adjudicator cannot search, introduce cards, or change clinical conclusions.
8. **Final report synthesis** — always run. Use the existing report-write contract, deterministic audited report blocks, and the original `case.md`/structured case context. The report must address the actual case but may not create new clinical conclusions or evidence assignments.

A clean run therefore uses seven routine model passes; evidence disagreement adds one short eighth pass.

## Self commands

Set up the run with `self.py setup` using the same modes as staged v6. For an interactive `ngs-report`, first place the user's case verbatim in a temporary case file and pass it with `--case-file`.

Choose the setup work-location argument once:

- supplied directory: `--work-dir <supplied-directory>`;
- exact `->project` modifier: `--project`, which writes under `<repo-root>/temp/`;
- otherwise omit both, which writes to a unique system temporary directory.

These work-location rules apply only to native `self.py`. The existing staged `step.py` work-directory behaviour is unchanged. Always use the exact directory printed by self setup for every later self command.

Then follow this deterministic/model interleave. `<work-dir>` is the directory printed by setup.

```bash
python workflows/terraced_v6/self.py structure --work-dir <work-dir>
# Read the printed structure_case contract/inputs and write case.json.
# Stay in the same WHO1 reasoning pass:
python workflows/terraced_v6/self.py who1 --work-dir <work-dir>
# Read printed WHO5 inputs and write WHO1 output.

python workflows/terraced_v6/self.py icc --work-dir <work-dir>
# Write ICC output.

python workflows/terraced_v6/self.py who2 --work-dir <work-dir>
# Write authoritative WHO2 output.

python workflows/terraced_v6/self.py ptbg --work-dir <work-dir>
# In ONE model pass read all four printed domain contracts/contexts/card pools/output contracts.
# Write all four requested model-classification.yaml files.

python workflows/terraced_v6/self.py evidence-resolution --work-dir <work-dir>
# Write the shared evidence-match output.

python workflows/terraced_v6/self.py evidence-audit --work-dir <work-dir>
# Write the shared evidence-audit output.

python workflows/terraced_v6/self.py evidence-adjudication --work-dir <work-dir>
# If required=false, do not run an adjudication model pass.
# If required=true, read only the cropped disputes, disputed-card catalog and adjudication contract; write the requested output.

python workflows/terraced_v6/self.py finalize-evidence --work-dir <work-dir>

python workflows/terraced_v6/self.py report --work-dir <work-dir>
# Read the existing report-write contract, ORIGINAL case.md, and deterministic report context; write report-write.yaml.

python workflows/terraced_v6/self.py finalize-report --work-dir <work-dir>
# Prints REPORT, REPORT_JSON, MARKING_ZIP (validation modes), DEBUG_ZIP and DISSENT.
# DISSENT=none when there is no semantic dissent.
```

For non-self providers, continue to use `workflows/terraced_v6/step.py` with its existing work-directory behaviour unchanged.

## Deterministic boundaries retained for self

Retain deterministic case/variant identity, corpus hash and blacklist handling, runtime card tags, diagnosis/PTBG card retrieval, CMC-triggered WHO redraw, reportability, reason candidate-card pools, returned card membership/ID checks, evidence resolution-vs-audit comparison, disagreement cropping, adjudication application, no-support policy, citation/provenance rendering, dissent ledger/rendering, and validation/marking packaging.

Do not add routine deterministic/model repair for cosmetic whitespace, Markdown form, YAML style, or prose preservation. Parsing and identifiers required by downstream code remain critical.

`dissent.md` is never model-authored. Python records evidence disagreements/warnings and adjudication outcomes in the semantic-dissent ledger and deterministically renders the Markdown audit trail.
