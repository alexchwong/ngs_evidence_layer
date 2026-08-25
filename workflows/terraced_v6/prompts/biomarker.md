# MRD markers

Using only the supplied case, diagnosis, and MRD/biomarker cards, classify every supplied variant as either an MRD marker or not an MRD marker in the current disease context.

Rules:
- Give variants sharing one proposition the same `reason` wording; they are merged deterministically afterwards.
- `reason` is one concise evidence-backed proposition.
- Do not recommend a marker unless the supplied evidence supports its use for MRD in the current context.
