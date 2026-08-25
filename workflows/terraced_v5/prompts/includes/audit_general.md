# Shared semantic-audit principles

- Judge only the relationship this audit is assigned to assess; do not redo the whole clinical interpretation.
- Prefer preserving a clinically plausible conclusion with an explicit qualifier over rejecting it merely because information is pending or unavailable.
- Distinguish missing exclusion/discriminator information from missing positive defining evidence.
- Missing exclusion/discriminator information may justify a conditional `provided...` or `unless...` statement.
- A condition may qualify or potentially disqualify an already-supported conclusion; it must not invent a missing positive feature required to create the conclusion.
- Treat present, absent, pending, and unknown/not supplied as different states.
- Absence of contrary evidence is not positive support.
- Do not strengthen certainty, broaden scope, or remove important qualifiers.
- When a problem is found, identify the exact unsupported inference or missing qualifier. Do not prescribe the replacement clinical answer.
- Feedback is negative guidance for de-novo regeneration: explain what reasoning must not be repeated.
- When evidence is incomplete but the conclusion remains conditionally supportable, prefer `supported_if` over `unsupported`.
