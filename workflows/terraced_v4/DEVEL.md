# Terraced v4 developer notes

`step.py` owns the fixed workflow; `schema_validation.py` owns structural/coverage checks; `runtime.py` owns deterministic CMC and summary/block operations; prompts are small category-specific files under `prompts/`; `prompts/includes/ptbg_common.md` plus `*_semantics.md` files hold injectable PTBG interpretation policy; `corpus_filters.yaml` pins WHO5 diagnosis to Khoury 2022 and ICC diagnosis to Arber 2022.

Deterministic validation is limited to syntax, schema shape, stable IDs, variant coverage, incompatible bucket membership, row completeness and summary ancestry. Clinical meaning, evidence relevance, source naming and quote fidelity remain model/human-audited. Validators accumulate all detectable defects instead of failing on the first field. Representation-only (`serialization`) defects are repaired through shared `scripts/core/syntax_repair` before the originating task is retried.

## Diagnosis ordering

`WHO5 pass 1 → conditional WHO5 pass 2 → ICC → other diagnostic considerations`.

WHO5 alone drives deterministic CMC derivation. A CMC-changing WHO5 pass 1 causes pass 2 to start from scratch with cumulative old+new CMC recall. ICC then receives authoritative WHO5 for comparison but uses Arber-only evidence. The other-diagnosis call receives authoritative WHO5 but not ICC.


## PTBG prompt composition

PTBG calls are assembled as `shared interpretation discipline → domain semantic boundaries → small proforma → case/diagnosis/cards`. The shared include blocks cross-domain inference (for example diagnostic importance → MRD suitability), while each domain include defines the clinical meaning of its buckets. Keep these semantic policies outside the YAML proforma so they can be tuned without changing schema validation or Python. Germline no longer receives a special system prompt licensing unsupported model-memory classification; a positive `suspect` call must be supported by supplied case/evidence plus VAF compatibility.

## Batched semantic operations

Initial evidence matching is one whole-workflow batch, followed by one whole-workflow audit. Only obvious mismatches continue into bounded retry batches. Report planning is one omit/split/merge call. Python converts temporary model group labels into canonical domain block IDs and order. All blocks are paraphrased in one call and audited in one call. Semantic failure degrades to source-preserving blocks rather than per-sentence retry loops.

## Retry classes

- clinical diagnosis/PTBG proformas: initial generation plus at most `proforma_rewrite_attempts` (default 3) complete rewrites;
- syntax/serialization repair: at most `syntax_repair_attempts` (default 5) attempts for one artifact; exhaustion abandons that artifact and consumes one full proforma rewrite rather than continuing syntax repair;
- other fatal structural operations: up to `fatal_attempts` (default 10) per operation;
- evidence rematching: `evidence_match_attempts` (default 3) semantic batch attempts, then log/degrade;

Syntax repair eligibility is deliberately conservative: the workflow must be able to change representation while preserving the existing informational tokens. Wrong schema choices that require deleting, adding or reinterpreting fields are content/proforma defects, not syntax defects. There is no workflow-global retry budget. Failed clinical and syntax-repair artifacts are preserved under `logs/errors/`.

## Token accounting

Every direct OpenAI-compatible model attempt records provider-reported `prompt_tokens`, `completion_tokens`, and `total_tokens` in `logs/model-usage.json`, including truncated completions and syntax-only repairs. The CLI prints aggregate totals at completion. Providers that omit usage are counted as unreported; `self` handoffs are not estimated.
