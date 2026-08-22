---
id: core.requirements.report.summary
semantic_type: report.summary.sentences
format: yaml
provides: []
requires: ["sentences[].sentence_id", "sentences[].sentence", "sentences[].card_tags"]
runtime_invariants: []
---
# Input requirement: report.summary.sentences

Compatibility contract used during pipeline setup. An upstream module may use any output representation that declares this semantic type and provides the required fields.
