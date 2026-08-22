---
id: core.requirements.ptbg.germline
semantic_type: ptbg.germline.state
format: yaml
provides: []
requires: ["variant_decisions[]", "clinical_picture"]
runtime_invariants: []
---
# Input requirement: ptbg.germline.state

Compatibility contract used during pipeline setup. An upstream module may use any output representation that declares this semantic type and provides the required fields.
