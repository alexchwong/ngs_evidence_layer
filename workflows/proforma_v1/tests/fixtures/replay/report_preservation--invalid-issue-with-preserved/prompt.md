# Report preservation audit

Compare each rendered report block with its deterministic source block.

This is preservation-only. Do NOT reconsider diagnosis, prognosis, treatment, MRD, germline, or evidence.

For each block ask only whether the rendered text:
- represents every supplied component;
- preserves diagnosis/framework, polarity, treatment, molecular scope, qualifiers, and uncertainty;
- does not require internal workflow variant IDs such as `v01`, `v02`, etc. to be retained; omission of those IDs is not a preservation failure when the variant remains clinically identifiable from the rendered text;
- adds no new clinical proposition;
- omits no supplied proposition.

Return YAML only:
```yaml
audits:
  - block_id: "DX"
    preserved: true
    issue: null
```
