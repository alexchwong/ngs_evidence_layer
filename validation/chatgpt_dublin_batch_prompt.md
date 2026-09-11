# ChatGPT Dublin Batch NGS Report Prompt

You are generating a comparison set of NGS reports for all 10 Dublin validation cases.

## Run metadata

Before generating reports:

1. Record your current ChatGPT model identity as `profile` if you can identify it reliably.
2. Ask me for `run` if I have not already supplied a run number/label in the chat.
3. If you cannot reliably identify your current model, ask me for `profile` as well.
4. Do not invent either value.

## Task

Using the NGS report formatting and reporting instructions supplied in the project/system prompt, independently analyse each case below and generate one final NGS report per case.

Treat every case as an independent reporting task. Do not allow information, conclusions, variants, diagnoses, prognosis, treatment implications, or wording from one case to influence another case.

## Required output

Create exactly these 11 files:

- `case-1.md`
- `case-2.md`
- `case-3.md`
- `case-4.md`
- `case-5.md`
- `case-6.md`
- `case-7.md`
- `case-8.md`
- `case-9.md`
- `case-10.md`
- `source_manifest.json`

Each `case-N.md` file must contain only the final clinical report for that case. Do not include commentary about the task, model identity, source, run number, prompt, blinding, or comparison study in the report.

`source_manifest.json` must contain exactly this structure:

```json
{
  "source": "ChatGPT",
  "profile": "<model/profile identity>",
  "run": "<run number or label>",
  "cases": {
    "case-1": "case-1.md",
    "case-2": "case-2.md",
    "case-3": "case-3.md",
    "case-4": "case-4.md",
    "case-5": "case-5.md",
    "case-6": "case-6.md",
    "case-7": "case-7.md",
    "case-8": "case-8.md",
    "case-9": "case-9.md",
    "case-10": "case-10.md"
  }
}
```

Bundle the 11 files into a single zip named `chatgpt-dublin-<run>.zip`.

Do not hash or rename the reports. A downstream repository script will assign source-blinded filenames and update the central provenance index.

## Case 1

46F presents with pancytopenia. Bone marrow examination shows acute myeloid leukaemia with 55% myeloblasts. Conventional cytogenetics demonstrates a normal karyotype.

She has had mild thrombocytopenia since her twenties. Her father also had longstanding thrombocytopenia and subsequently developed myelodysplastic syndrome.

Molecular testing identifies:

- NPM1 NM_002520.7:c.860_863dup p.(Trp288CysfsTer12), VAF 36%
- FLT3-ITD
- RUNX1 NM_001754.5:c.496C>T p.(Arg166Ter), VAF 48%

## Case 2

34M presents with bruising, anaemia, thrombocytopenia and disseminated intravascular coagulation. Bone marrow examination shows extensive infiltration by abnormal promyelocytes.

Molecular/cytogenetic testing demonstrates:

- PML::RARA fusion
- FLT3-ITD

## Case 3

52F is diagnosed with acute myeloid leukaemia. Blast morphology and immunophenotype are compatible with core-binding-factor AML, and RUNX1::RUNX1T1 is demonstrated.

Separate from the blast population, the marrow contains multifocal dense aggregates of atypical spindle-shaped mast cells expressing tryptase and aberrant CD25.

Molecular testing identifies:

- RUNX1::RUNX1T1 fusion
- KIT NM_000222.3:c.2447A>T p.(Asp816Val), VAF 12%

## Case 4

68M presents with progressive pancytopenia. Bone marrow examination shows a myelodysplastic neoplasm with increased blasts-1, with 8% marrow blasts.

His father developed MDS in his seventies and a paternal uncle developed AML.

Cytogenetic testing demonstrates del(17p) involving TP53.

Molecular testing identifies:

- TP53 NM_000546.6:c.743G>A p.(Arg248Gln), VAF 41%
- DDX41 NM_016222.4:c.415_418dup p.(Asp140delinsGlyTer), VAF 49%
- DDX41 NM_016222.4:c.1574G>A p.(Arg525His), VAF 7%

## Case 5

71F presents with macrocytic anaemia and thrombocytopenia. Bone marrow examination shows a low-blast myelodysplastic neoplasm with 3% marrow blasts and characteristic hypolobated megakaryocytes. Cytogenetic testing demonstrates an isolated del(5q).

A separate small population of abnormal mature B cells has hairy cytoplasmic projections and an immunophenotype supporting hairy-cell leukaemia.

Molecular testing identifies:

- SF3B1 NM_012433.4:c.2098A>G p.(Lys700Glu), VAF 31%
- BRAF NM_004333.6:c.1799T>A p.(Val600Glu), VAF 5%

## Case 6

58M has established primary myelofibrosis with splenomegaly, anaemia and constitutional symptoms.

Molecular testing identifies:

- CALR NM_004343.4:c.1099_1150del p.(Leu367ThrfsTer46), VAF 42%
- ASXL1 NM_015338.6:c.1934dup p.(Gly646TrpfsTer12), VAF 28%
- U2AF1 NM_006758.3:c.470A>C p.(Gln157Pro), VAF 19%

## Case 7

29F presents with persistent cytopenias. She has longstanding monocytopenia, recurrent severe viral warts and a previous atypical mycobacterial infection. Her mother developed MDS at 43 years of age.

Bone marrow examination demonstrates a myelodysplastic neoplasm with increased blasts-1, with 7% marrow blasts. Cytogenetic testing demonstrates monosomy 7.

Molecular testing identifies:

- GATA2 NM_032638.5:c.1061C>T p.(Thr354Met), VAF 48%
- ASXL1 NM_015338.6:c.1934dup p.(Gly646TrpfsTer12), VAF 21%

## Case 8

73M has persistent absolute and relative monocytosis, splenomegaly and bone-marrow dysplasia consistent with chronic myelomonocytic leukaemia. He also has an IgM paraprotein. Bone marrow examination demonstrates a separate small clonal lymphoplasmacytic B-cell population.

Molecular testing identifies:

- ASXL1 NM_015338.6:c.1934dup p.(Gly646TrpfsTer12), VAF 39%
- NRAS NM_002524.5:c.35G>A p.(Gly12Asp), VAF 18%
- MYD88 NM_002468.4:c.794T>C p.(Leu265Pro), VAF 7%

## Case 9

71M presents with fatigue and recurrent infections and is not fit for intensive chemotherapy because of ECOG 2 and cardiac comorbidity. Hb 82 g/L, WCC 3.2 x10^9/L, ANC 0.7 x10^9/L and platelets 60 x10^9/L. The film shows 24% circulating blasts and no Auer rods. Bone marrow shows 46% blasts and no dysplastic ring sideroblasts. Karyotype is normal. Marrow morphological diagnosis: acute myeloid leukaemia.

Molecular testing identifies:

- IDH2 NM_002168.4:c.515G>A p.(Arg172Lys), VAF 40%
- SRSF2 NM_003016.4:c.284C>A p.(Pro95His), VAF 36%

Cytogenetics: 46,XY[20].

## Case 10

68M presents with pancytopenia and fatigue. Hb 84 g/L, MCV 98 fL, WCC 2.1 x10^9/L, ANC 0.9 x10^9/L and platelets 41 x10^9/L. Film shows occasional blasts and dysplastic neutrophils. Bone marrow demonstrates trilineage dysplasia with 4% blasts. No 17p loss or copy-neutral loss of heterozygosity is detected. Marrow morphological diagnosis: myelodysplastic neoplasm with low blasts and multilineage dysplasia.

Molecular testing identifies:

- TP53 NM_000546.6:c.524G>A p.(Arg175His), VAF 12%

Cytogenetics: 46,XY[20]; FISH negative for 17p deletion.
