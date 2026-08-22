# Local fact-to-card support check

Verify only whether each supplied reportable fact is supported by the card or cards explicitly attributed to it.

This is a reject-only verification task:
- use only the supplied facts and supplied claimed cards;
- do not use the case, diagnosis state, other facts, outside literature, or web knowledge;
- do not search for a better card;
- do not rewrite a fact;
- do not add, remove, or reassign card tags;
- treat patient-specific observations stated inside the fact (for example a measured blast percentage or the presence of a reported variant) as supplied premises; the cards are not expected to prove those case observations;
- the claimed card set must support the complete **interpretive inference** made from those premises (classification rule, prognostic meaning, treatment implication, MRD role, germline implication, etc.), not merely be topically related;
- every claimed card must materially support the fact or a necessary element of it;
- when multiple cards jointly support a fact, judge the set collectively while still rejecting irrelevant claimed cards;
- if the interpretive inference is incomplete, overstated, scoped to a different disease/context, or otherwise not supported by the claimed cards when the stated patient observations are taken as true premises, return `supported: false` and state the precise mismatch concisely.

{{output_contract}}
