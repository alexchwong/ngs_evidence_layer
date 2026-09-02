from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from workflows.proforma_v1 import prompt_loader

HERE = Path(__file__).resolve().parents[1]
PROMPTS = HERE / "prompts"
SCHEMAS = HERE / "schemas"

_INCLUDE_RE = re.compile(r'^\s*\{\{\s*include\s+["\']([^"\']+)["\']\s*\}\}\s*$', re.MULTILINE)

EXPECTED_COMPONENTS = (
    "includes/diagnosis/case_context.md",
    "includes/diagnosis/new_diagnosis.md",
    "includes/diagnosis/progress_testing.md",
    "includes/diagnosis/molecular_result_semantics.md",
    "includes/diagnosis/variant_assessment.md",
)

EXPECTED_SECTIONS = (
    "## 1. Task and authority",
    "## 2. Determine case context",
    "## 3. New diagnosis",
    "## 4. Progress testing",
    "## 5. Molecular and cytogenetic result semantics",
    "## 6. Determine and freeze the primary",
    "## 7. Assess every detected variant",
    "## 8. Output contract",
)

NO_HAEM_SENTINEL = "no_haematological_malignancy"


class DiagnosisPromptContractTests(unittest.TestCase):
    def _source(self, name: str) -> str:
        return (PROMPTS / name).read_text(encoding="utf-8")

    def _render(self, name: str) -> str:
        return prompt_loader.render(PROMPTS / name, root=PROMPTS)

    def _component_order(self, path: Path) -> tuple[str, ...]:
        found: list[str] = []
        text = path.read_text(encoding="utf-8")
        for include in _INCLUDE_RE.findall(text):
            child = (path.parent / include).resolve()
            found.append(child.relative_to(PROMPTS.resolve()).as_posix())
            found.extend(self._component_order(child))
        return tuple(found)

    def _assert_contract(self, name: str) -> None:
        source = self._source(name)
        self.assertEqual(tuple(_INCLUDE_RE.findall(source)), EXPECTED_COMPONENTS)
        self.assertEqual(self._component_order(PROMPTS / name), EXPECTED_COMPONENTS)

        rendered = self._render(name)
        self.assertNotIn("{{ include", rendered)

        positions = []
        for section in EXPECTED_SECTIONS:
            if section.endswith("primary"):
                matches = [
                    rendered.find("## 6. Determine and freeze the primary WHO5 diagnosis"),
                    rendered.find("## 6. Determine and freeze the primary ICC diagnosis"),
                ]
                pos = max(matches)
            else:
                pos = rendered.find(section)
            self.assertGreaterEqual(pos, 0, f"missing section {section!r} in {name}")
            if not section.endswith("primary"):
                self.assertEqual(rendered.count(section), 1, f"section duplicated in {name}: {section!r}")
            positions.append(pos)
        self.assertEqual(positions, sorted(positions), f"section order changed in {name}")

    def test_who5_component_contract(self):
        self._assert_contract("diagnosis_who5.md")

    def test_icc_component_contract(self):
        self._assert_contract("diagnosis_icc.md")

    def test_shared_components_exist_and_are_nonempty(self):
        for rel in EXPECTED_COMPONENTS:
            path = PROMPTS / rel
            self.assertTrue(path.is_file(), rel)
            self.assertTrue(path.read_text(encoding="utf-8").strip(), rel)

    def test_sections_two_and_three_have_one_shared_source_of_truth(self):
        who_source = self._source("diagnosis_who5.md")
        icc_source = self._source("diagnosis_icc.md")
        for rel in EXPECTED_COMPONENTS[:2]:
            directive = '{{ include "' + rel + '" }}'
            self.assertEqual(who_source.count(directive), 1)
            self.assertEqual(icc_source.count(directive), 1)

        who = self._render("diagnosis_who5.md")
        icc = self._render("diagnosis_icc.md")
        start = "## 2. Determine case context"
        end = "## 4. Progress testing"
        who_shared = who[who.index(start):who.index(end)].strip()
        icc_shared = icc[icc.index(start):icc.index(end)].strip()
        self.assertEqual(who_shared, icc_shared)

    def test_new_diagnosis_section_is_list_structured(self):
        text = (PROMPTS / "includes/diagnosis/new_diagnosis.md").read_text(encoding="utf-8")
        self.assertIn("only when all of the following are true:", text)
        self.assertGreaterEqual(len(re.findall(r"^- ", text, flags=re.MULTILINE)), 6)
        self.assertNotIn("Return `schema_disease", text)

    def test_icc_accepts_no_haematological_malignancy_sentinel_without_changing_normal_contract(self):
        schema = json.loads((SCHEMAS / "diagnosis.json").read_text(encoding="utf-8"))
        self.assertNotIn("schema_disease", schema["required"])
        self.assertEqual(schema["properties"]["schema_disease"]["const"], NO_HAEM_SENTINEL)

        who = self._render("diagnosis_who5.md")
        icc = self._render("diagnosis_icc.md")
        marker = f"`schema_disease: {NO_HAEM_SENTINEL}`"
        self.assertIn(marker, who)
        self.assertIn(marker, icc)

    def test_framework_specific_output_contracts_remain_distinct(self):
        who = self._render("diagnosis_who5.md")
        icc = self._render("diagnosis_icc.md")
        self.assertIn('schema_disease: "<allowed schema disease>"', who)
        self.assertNotIn('schema_disease: "<allowed schema disease>"', icc)
        self.assertIn("The WHO5 diagnosis is supplied only as context.", icc)
        self.assertNotIn("The WHO5 diagnosis is supplied only as context.", who)

    def test_semantic_safety_invariants_are_present(self):
        common = (
            "Legacy cases without this field are treated as `new`.",
            "it is not a de-novo opportunity to downgrade the established disease",
            "does not block genuine progression or transformation",
            "A negative NGS result does not invalidate a supplied morphologic diagnosis.",
            "Treat supplied cytogenetic, FISH, rearrangement, copy-number, PCR, and other non-NGS molecular abnormalities independently of NGS variant status.",
            "Use deterministic finite-gene-set membership supplied by core when present.",
            "Do not claim an unlisted variant satisfies a closed molecular criterion.",
            "assess every detected registry variant exactly once in `variant_assessments`",
            "Mere occurrence in another disease is insufficient.",
            "do not manufacture a myeloid neoplasm from descriptive marrow findings or cytopenias",
            "clinical/morphologic correlation is required",
        )
        for name in ("diagnosis_who5.md", "diagnosis_icc.md"):
            rendered = self._render(name)
            for invariant in common:
                self.assertIn(invariant, rendered, f"{name}: lost semantic invariant {invariant!r}")

        who = self._render("diagnosis_who5.md")
        self.assertIn("every link from the finding through any intermediate state to the WHO5 entity must be supported by supplied cards", who)
        self.assertIn("Do not consider concurrent pathology yet.", who)
        self.assertIn(f"`schema_disease: {NO_HAEM_SENTINEL}`", who)
        self.assertIn("internal sentinel only", who)

        icc = self._render("diagnosis_icc.md")
        self.assertIn("Return one ICC diagnosis only.", icc)
        self.assertIn("does not indicate NGS negativity", icc)
        self.assertIn("Retain the established disease and describe the current treated/response state concisely in `reason`", icc)
        self.assertIn("must not be used to retrospectively criticize or invalidate the established diagnosis", icc)
        self.assertIn(f"`schema_disease: {NO_HAEM_SENTINEL}`", icc)
        self.assertIn("otherwise omit `schema_disease`", icc)


if __name__ == "__main__":
    unittest.main()
