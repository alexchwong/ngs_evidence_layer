# Prognosis

Using only the supplied case, diagnosis, and prognosis cards, classify every supplied variant once by its principal supported prognostic effect in the current disease context.

Rules:
- `reason` is one concise report-ready clinical proposition. Give variants sharing one proposition the same `reason` wording; they are merged deterministically afterwards.
- Preserve qualitative strength from the evidence; do not weaken or strengthen it.
- Do not infer that one variant cancels another unless the supplied evidence explicitly defines that interaction.
- `prognostic_score` is populated only when this workflow can actually assign the named score/risk group from supplied information. Otherwise use null. Never say a score is "not calculable".
