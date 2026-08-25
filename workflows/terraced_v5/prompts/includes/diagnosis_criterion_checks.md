# Diagnostic criterion-check discipline

Represent each discrete authority-backed diagnostic rule once, then classify only the case results relevant to that rule.

For each criterion:
- `authority_card_id`: supplied authority card containing the rule;
- `criterion_type`: `molecular_membership` only for an explicitly finite qualifying gene set; otherwise `other`;
- `criterion`: the rule being applied;
- `reason`: why the rule contributes to the diagnosis, written once;
- `checks`: compact subject-ID lists only.

Contribution buckets:
- `positive_supportive`: present/positive result supports the criterion;
- `negative_supportive`: negative result supports the criterion because the authority card requires that negative relationship;
- `indeterminate`: relevant result remains unresolved after applying testing-state rules;
- `not_contributory`: known result does not support or oppose this criterion.

Subject conventions:
- detected NGS variant: supplied internal variant ID (`v01`, `v02`, ...);
- unreported NGS gene: uppercase gene symbol, ONLY when the authority card explicitly makes that gene's negative status relevant;
- reported non-NGS result: supplied case fact ID (`C1`, `C2`, ...);
- unsupplied relevant non-NGS result: short test/modality name.

Testing-state rules are deterministic and MUST NOT be written in the model output:
- detected NGS variant -> `positive`;
- unreported gene on the supplied NGS panel -> `verified_negative`;
- relevant non-NGS test absent, pending, or not done -> `presumed_negative` for provisional reasoning;
- core expands each compact subject into an atomic check with its result status after this pass.

Relevance:
- relevance comes from the supplied authority card, not general model knowledge;
- include a negative subject only when the authority card makes that negative result part of the rule;
- DO NOT enumerate unreported panel genes;
- DO NOT invent exclusions, dependencies, or qualifying genes absent from the authority card;
- emit only criteria that contribute to, qualify, condition, or materially distinguish a returned diagnosis.

For `molecular_membership` criteria:
- classify EVERY supplied detected variant exactly once;
- use the deterministic finite-gene-set membership context when supplied;
- subjects inside the finite set may be `positive_supportive` when the card's other requirements are met;
- subjects outside the finite set are `not_contributory`;
- do not add bare negative panel genes to this criterion;
- do not describe `not_contributory` subjects as qualifying in `criterion` or `reason`.

Conditionality:
- if diagnostic support depends on an unsupplied/pending non-NGS negative, set diagnosis `status: conditional`;
- `not_contributory` checks are internal reasoning and are not themselves reportable negatives.

Output discipline:
- keep checks as short subject-ID arrays;
- do not repeat reasons per subject;
- do not explain individual checks;
- use the fewest criteria needed to express the authority-backed diagnostic reasoning.
