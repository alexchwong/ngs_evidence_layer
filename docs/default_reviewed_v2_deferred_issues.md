# Deferred issues from the reviewed-v2 reasoning refactor

These are intentionally outside the implementation scope and should be transferred to the project issue tracker when convenient.

## 1. Deterministic-safe `dissent.md` summariser

Cover provider optional-model fallback, native-self fallback, semantic ledger ID/status validation including `retained_without_review`, regeneration timing, and prevention of invalid model summaries replacing the deterministic view.

## 2. Engine-level exhausted-review artifact

Allow a reviewer that never emits a parseable document to record an `unusable` terminal audit state rather than failing without a completed audit artifact.

## 3. Per-cycle `model-operations.json`

Represent owner calls per correction cycle. Until implemented, `audit_v2/owner-cycles/` remains the authoritative per-cycle record.

## 4. Declared checks under native-self execution

`SelfExecutor.is_complete()` can short-circuit before declared validation for reasoning-model steps. Reviewed-v2 works around this with unconditional deterministic downstream validation, but the engine-level inconsistency remains.

## 5. Native-self raw transport preservation

Preserve the submitted pre-normalisation model output before `domain_contract.normalize_model_output` overwrites it, so native-self cycle archives can carry the same raw transport provenance as provider execution.
