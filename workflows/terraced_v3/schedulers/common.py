"""Shared scheduler contracts and execution context for terraced-v3.

Schedulers own only task partitioning/terracing. The surrounding workflow owns
case structure, diagnosis/CMC stabilisation, evidence retrieval, deterministic
validation/repair, evidence alignment, prose synthesis, citation inheritance and
final rendering.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

import yaml


SCHEDULER_API_VERSION = 1
DOMAINS = ("prognosis", "treatment", "biomarker", "germline")


def task_specs(case: dict, diagnoses: list[dict]) -> list[dict]:
    variants = case.get("variants") or []
    genes: list[str] = []
    for row in variants:
        gene = row["gene"]
        if gene not in genes:
            genes.append(gene)
    diagnosis_ids = [row["diagnosis_id"] for row in diagnoses]
    return [
        {
            "domain": "prognosis",
            "category": "prognosis",
            "required_pairs": [(v["variant_id"], dx) for v in variants for dx in diagnosis_ids],
        },
        {
            "domain": "treatment",
            "category": "treatment",
            "required_pairs": [(g, dx) for g in genes for dx in diagnosis_ids],
        },
        {
            "domain": "biomarker",
            "category": "biomarker",
            "required_pairs": [(v["variant_id"], dx) for v in variants for dx in diagnosis_ids],
        },
        {
            "domain": "germline",
            "category": "germline",
            "required_variants": [v["variant_id"] for v in variants],
        },
    ]


def spec_map(case: dict, diagnoses: list[dict]) -> dict[str, dict]:
    return {row["domain"]: row for row in task_specs(case, diagnoses)}


def contract(domain: str, case: dict, diagnoses: list[dict]) -> str:
    del case, diagnoses
    if domain == "prognosis":
        return """## Prognosis contract
For every detected variant × settled WHO5 diagnosis pair, decide its molecular prognostic classification in the most applicable named prognostic scoring/classification system.

Return exactly:
```yaml
decisions:
  - variant_id: V1
    diagnosis_id: DX1
    effect: favorable
    scoring_system: "ELN 2022"
    surface: true
    fact: "... ."
    reason: "..."
    candidate_card_tags: []
```
Allowed effect values: `favorable`, `adverse`, `neither`. `scoring_system` is a non-empty string when a relevant named system applies, otherwise null. A `neither` result is usually `surface: false` unless clinically important."""
    if domain == "treatment":
        return """## Treatment contract
For every detected gene × settled WHO5 diagnosis pair, decide separately whether the detected alteration context makes the gene a drug target and whether it is associated with drug resistance.

Return exactly:
```yaml
decisions:
  - gene: FLT3
    diagnosis_id: DX1
    drug_target: true
    target_surface: true
    target_fact: "... ."
    target_reason: "..."
    target_candidate_card_tags: []
    drug_resistance: false
    resistance_surface: false
    resistance_fact: null
    resistance_reason: null
    resistance_candidate_card_tags: []
```
Boolean decisions are hard facts. Surface positive or otherwise clinically important implications only. Keep alteration-specific qualifiers in the fact/reason; do not generalise a gene-wide statement beyond the detected alteration."""
    if domain == "biomarker":
        return """## MRD/biomarker contract
For every detected variant × settled WHO5 diagnosis pair, decide whether that detected variant can be used as a molecular MRD biomarker in that disease context.

Return exactly:
```yaml
decisions:
  - variant_id: V1
    diagnosis_id: DX1
    mrd_usable: true
    surface: true
    fact: "... ."
    reason: "..."
    candidate_card_tags: []
```
Do not treat every persistent somatic mutation as an MRD marker. Surface clinically useful positive or cautionary statements."""
    if domain == "germline":
        return """## Germline contract
For every detected variant, decide whether its gene is a well-documented germline predisposition gene for haematological malignancy and therefore the finding is potentially germline. Separately decide whether the supplied clinical picture supports a germline syndrome.

Return exactly:
```yaml
variant_decisions:
  - variant_id: V1
    potentially_germline: false
    surface: false
    fact: null
    reason: null
    candidate_card_tags: []
clinical_picture:
  supportive: false
  surface: false
  fact: null
  reason: null
  candidate_card_tags: []
```
`supportive` must be `true`, `false`, or `uncertain`. Potential germline status must be based on well-documented germline predisposition genes, not VAF alone. The clinical-picture decision may use age, phenotype and family history supplied in the case."""
    raise ValueError(f"unknown domain {domain!r}")


@dataclass
class EvidenceView:
    domain: str
    cards: list[dict]
    manifest: dict
    permitted_tags: set[str]
    text: str


@dataclass
class SchedulerContext:
    """Narrow execution surface exposed by step.py to scheduler plugins."""

    work: Path
    case: dict
    diagnoses: list[dict]
    final_cmcs: list[str]
    profile: str | None
    domain_task_prompt: str
    call_yaml: Callable[..., None]
    ensure_evidence: Callable[[str], EvidenceView]
    read_text: Callable[[Path], str]
    write_text: Callable[[Path, str], Path]
    status: Callable[[str], None]

    @property
    def specs(self) -> dict[str, dict]:
        return spec_map(self.case, self.diagnoses)

    def base_context(self, spec: dict, evidence_text: str) -> str:
        scope = {k: v for k, v in spec.items() if k.startswith("required_")}
        return (
            "# Structured immutable case\n```json\n"
            + __import__("json").dumps(self.case, indent=2, ensure_ascii=False)
            + "\n```\n\n# Settled WHO5 diagnoses\n```yaml\n"
            + yaml.safe_dump({"diagnoses": self.diagnoses, "final_cmcs": self.final_cmcs}, sort_keys=False, allow_unicode=True, width=110)
            + "```\n\n# Required decision scope\n```yaml\n"
            + yaml.safe_dump(scope, sort_keys=False, allow_unicode=True)
            + "```\n\n# Evidence\n"
            + evidence_text
        )
