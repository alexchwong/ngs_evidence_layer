# Diagnosis category formatting

- Maximum 70 words across the completed `text` fields.
- Use full sentences.
- Produce one integrated patient-level diagnosis paragraph, not a line-by-line shortening or separate paraphrase of the source statements.
- Consider every reportable (`omit: false`) R0/R1 statement before drafting and integrate every clinically distinct retained fact needed to preserve their meaning.
- Answer, in a clinically natural order: **What NGS variants were detected? What is the integrated diagnosis? What patient-level facts support that diagnosis?**
- State the WHO diagnosis and state the ICC diagnosis only when materially different or clinically useful.
- If the source supports multiple pathologies, state the distinct diagnoses clearly; otherwise give one integrated diagnosis.
- Do not restore findings from `omit: true` rules.
