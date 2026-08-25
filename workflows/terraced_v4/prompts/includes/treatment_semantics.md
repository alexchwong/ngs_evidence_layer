# Treatment interpretation boundaries

Report only treatment implications caused or predicted by the molecular finding itself.

For `drug_target`:
- The variant must identify, enable, or predict sensitivity to a named drug or drug class.
- A therapy used for the disease generally is not a molecular target of the variant.

For `drug_resistance`:
- The variant must predict or confer reduced response or resistance to a named therapy or drug class.
- Poor prognosis is not drug resistance.

Do not classify a variant as a treatment target merely because:
- the disease is treated with that drug;
- the gene is biologically involved in the drug's pathway;
- the gene is diagnostically or prognostically important; or
- a supplied card describes treatment of patients with the disease but does not make the treatment conditional on that molecular finding.

If no variant-specific treatment implication is supported, place the variant in `no_effect`.
