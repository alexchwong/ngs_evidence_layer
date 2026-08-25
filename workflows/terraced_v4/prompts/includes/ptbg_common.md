# Shared PTBG interpretation discipline

Apply these rules before completing the domain proforma.

- Account for every supplied variant ID, but do not invent an effect merely to satisfy variant coverage. A negative or uncertain classification is valid.
- Answer only the clinical question for this domain. Evidence that a variant is important for diagnosis, classification, prognosis, treatment, MRD, or germline assessment does not by itself establish an effect in another domain.
- The authoritative diagnosis supplies disease context. It is not evidence that a particular variant has a PTBG effect.
- A positive effect requires a proposition specific to this domain. Mere mention of the same gene, variant, disease, or a recommendation to test the gene is insufficient.
- A positive effect requires affirmative support from a supplied card whose content is specific to this domain. Absence of contrary evidence is not support. Do not use pretrained/model knowledge to create a positive effect when the supplied cards do not support it. Case facts may determine whether a supported rule applies to this patient, but do not themselves establish an external clinical effect.
- Preserve important qualifiers from the supplied evidence, including disease, treatment setting, population, named framework, and uncertainty. Do not generalize a context-specific association into a universal effect.
- Each `reason` must state one discrete clinical proposition explaining why the listed variant(s) belong in that bucket.
- Prefer a negative or uncertain classification over an unsupported positive conclusion.
- Do not manufacture a clinical implication from biological plausibility, gene familiarity, high VAF, diagnostic importance, technical detectability, or simple persistence alone.
