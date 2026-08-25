---
id: core.cards.identity
semantic_type: evidence.card_identity_manifest
format: json
provides: ["cards[].card_id", "cards[].card_tag", "corpus_sha256"]
requires: []
runtime_invariants: [deterministic_whole_corpus_card_tags]
---
# Card identity manifest

Deterministic whole-corpus mapping between internal card IDs and runtime 12-character card tags.
