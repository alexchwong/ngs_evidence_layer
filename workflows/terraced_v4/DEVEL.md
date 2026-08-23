# Terraced v4 developer notes

The prototype is intentionally explicit rather than declarative. `step.py` owns the fixed workflow; `schema_validation.py` owns structural/coverage checks; prompts are small category-specific files under `prompts/`; `pipeline_registry.py` owns only provider/model-role bindings.

Deterministic validation is limited to syntax, schema shape, stable IDs, variant coverage, incompatible bucket membership, and summary ancestry. Clinical meaning, evidence relevance, source naming and quote fidelity are model/human-audited.

Retry classes:
- fatal structural operations: up to `fatal_attempts` (default 10) per operation;
- semantic evidence rematching: `evidence_match_attempts` (default 3), then log/degrade;
- paraphrase semantic repair: `paraphrase_repair_attempts` (default 2), then fall back to the planned sentence;
- syntax-only repair: `syntax_repair_attempts` (default 2) inside each model operation.

There is no workflow-global retry budget and no stagnation early-stop in the prototype. Repeated failures are preserved under `logs/errors/` for post-mortem analysis.
