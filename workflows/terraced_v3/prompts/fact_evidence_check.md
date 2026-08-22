# Local fact provenance/support check

Verify only whether each supplied reportable fact has the correct provenance pattern and, when it makes a literature-dependent interpretation, whether the card or cards explicitly attributed to it support that interpretation.

This is a reject-only verification task:
- use only the supplied facts, their `case_refs`, and the supplied claimed cards;
- do not use the case text, diagnosis state, other facts, outside literature, or web knowledge;
- `case_refs` are patient-source identifiers only. Treat patient-specific observations stated inside the fact as supplied premises and assume them true; you are not being asked to verify those observations from the cards;
- a pure patient observation (for example, a measured blast percentage or the presence of a reported variant) should normally have `card_tags: []`; reject literature cards attached merely to prove that the patient observation exists;
- a classification, prognostic, treatment, MRD, germline, or other literature-dependent interpretive inference must have card evidence; reject a cardless interpretive inference;
- the claimed card set must support the complete **interpretive inference** made from the stated patient premises, not merely be topically related;
- every claimed card must materially support the fact or a necessary element of it;
- when multiple cards jointly support a fact, judge the set collectively while still rejecting irrelevant claimed cards;
- cards do not need to prove patient-specific observations already stated in the fact. Do not reject an otherwise supported inference merely because the card does not establish that this patient has the stated blast count, mutation, cytogenetic result, or other case premise;
- do not search for a better card;
- do not rewrite a fact;
- do not add, remove, or reassign card tags.

Use the most specific failure code:
- `observation_should_be_cardless`: the proposition is only a patient observation but literature cards were attached;
- `missing_card_evidence`: the proposition makes a literature-dependent inference but has no adequate card evidence;
- `irrelevant_card`: at least one claimed card is unnecessary or unrelated to the proposition;
- `incomplete_rule_support`: the cards support only part of the interpretive rule/inference;
- `authority_mismatch`: the fact names or implies one classification/guideline authority but the claimed evidence comes from another;
- `scope_mismatch`: the card concerns a materially different disease, alteration, treatment, MRD, germline, or clinical context;
- `unsupported_inference`: use only when none of the more specific codes applies.

Boundary examples:

1. **Supported mixed patient-premise + literature inference**
   - Fact: `With 30% marrow blasts and an SRSF2 mutation, this case meets the stated WHO5 AML-MR criterion.`
   - Card: a WHO5 card stating the relevant blast threshold and qualifying SRSF2 rule.
   - Result: `supported: true`. The card does not need to prove that this patient actually has 30% blasts or SRSF2; those are stated patient premises.

2. **Observation should be cardless**
   - Fact: `An SRSF2 mutation is present.`
   - Card: a WHO5 AML-MR criterion card.
   - Result: `supported: false`, `issue_code: observation_should_be_cardless`. The fact does not make the WHO5 inference.

3. **Authority mismatch**
   - Fact: `According to WHO5, the findings meet AML-MR criteria.`
   - Card: an ICC-only AML-MR criterion.
   - Result: `supported: false`, `issue_code: authority_mismatch`.

{{output_contract}}
