# Interpretation principles

A card interpretation is a self-contained clinical conclusion derived from its source evidence. It is not merely a quotation, paraphrase, extracted result, or restatement of a statistic.

State the strongest clinically useful conclusion directly entailed by the evidence, using only the minimum source-supported context needed for the conclusion to be understood correctly when presented alone.

Include the minimum context required to understand what population or disease the conclusion applies to, what molecular finding or biological group is relevant, what intervention and comparator are being compared when applicable, what outcome or clinical role is asserted, and what subgroup, analysis, threshold, treatment setting, or other qualifier materially limits the conclusion. Every gene listed in the card's `genes` field must be explicitly named in the interpretation. Every disease listed in the card's `diseases` field must be explicitly identified in the interpretation by its canonical name or an accepted source-disease alias. Generic substitutes such as "the driver gene", "this disease", or "these mutations" do not satisfy this surfacing requirement. The card category does not need to be named.

Do not add contextual detail merely to make the interpretation more complete. Include methodological detail only when it changes the clinical meaning or strength of the claim.

A trial name, cohort name, treatment-arm label, model number, table identifier, analysis label, subgroup nickname, or similar paper-local term must not carry information required to understand the interpretation. A paper-local study-population label such as `Arm A`, `Cohort 2`, `Group B`, or an author-named arm fails this standard when the interpretation does not state what clinically defines that population. Replace it with a short semantic description such as `patients who received drug A`, `patients with relapsed AML`, or `patients with TP53-mutated AML`; if the local label adds no clinical value, omit it and use the semantic description alone. Recognized clinical classifications may be retained when their meaning is the clinical assertion itself.

Numerical results, effect estimates, confidence intervals, P values, and other statistics may quantify or qualify a conclusion but must not substitute for stating the conclusion.

A quantitative finding may itself constitute a valid clinical conclusion when it is independently clinically useful, correctly scoped, and sufficiently supported. It does not require a treatment recommendation or practice directive merely to be card-worthy. A reported effect estimate is not automatically eligible solely because population, comparator, and outcome are stated.

Do not make the interpretation broader, stronger, more certain, or more directive than the evidence supports. Source-supported synthesis is permitted only when the conclusion is directly entailed without an unstated clinical or methodological premise.

If the source supports an isolated observation but no independently useful, correctly scoped standalone conclusion can be stated without assumed study knowledge or unsupported inference, do not create or retain a card for that observation.
