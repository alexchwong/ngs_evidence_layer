"""Step specifications for categorical-v1.

This module is the single source of truth for the workflow's step sequence. Both
the uniform front end (`step.py`) and, from stage 2, `SKILL.md` derive their
command list from `ORDER`.

Permitted model input sets are declared here as callables and are enforced by
construction: the bundle a model step receives contains exactly the declared
files, so anything omitted is absent rather than merely discouraged.
"""
from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from pathlib import Path

from scripts import vocab
from workflows.categorical_v1 import report_yaml, runtime

WORKFLOW_DIR = Path(__file__).resolve().parent
REPO_ROOT = WORKFLOW_DIR.parents[1]
PROMPT_DIR = WORKFLOW_DIR / "prompts"
SHARED_PROMPT_DIR = REPO_ROOT / "prompts" / "workflow"

# Appended to every model step's instruction section.
COMMON_PROMPTS: tuple[Path, ...] = (PROMPT_DIR / "patient_result_semantics.md",)

ALL_MODES = ("ngs-report", "nel-demo", "nel-validate", "nel-validate-function")
CAPTURE_MODES = ("ngs-report", "nel-demo")

# 6b1..6b5 map onto the canonical category order without restating it here.
CATEGORY_STEP_IDS: dict[str, str] = {
    f"6b{index}": category
    for index, category in enumerate(report_yaml.SUMMARY_SECTIONS, start=1)
}


@dataclass(frozen=True)
class ModelStep:
    step_id: str
    role: str
    title: str
    prompts: tuple[Path, ...]
    inputs: Callable[[Path], list[Path]]
    output: str
    seed_output: bool
    validate: Callable[[Path], str]
    modes: tuple[str, ...] | None = None
    max_attempts: int = 3
    prepare: Callable[[Path], None] | None = None
    required: Callable[[Path], tuple[bool, str]] | None = None

    is_model_step: bool = field(default=True, init=False)

    def output_path(self, work: Path) -> Path:
        return Path(work) / self.output


@dataclass(frozen=True)
class DeterministicStep:
    step_id: str
    title: str
    run: Callable[[Path, str], list[str]]
    modes: tuple[str, ...] | None = None

    is_model_step: bool = field(default=False, init=False)


# ---------------------------------------------------------------------------
# Validators. Existing runtime functions wherever one exists.
# ---------------------------------------------------------------------------


def _validate_case(work: Path) -> str:
    path = work / "case.md"
    if not path.is_file():
        raise ValueError(f"step 1A produced no case file: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"step 1A wrote an empty case file: {path}")
    return f"case.md captured ({len(text.split())} words)"


def _validate_case_input(work: Path) -> str:
    path = work / "case-input.json"
    if not path.is_file():
        raise ValueError(f"step 1B produced no structured case: {path}")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"case-input.json is not valid JSON: {exc}") from exc
    if not isinstance(document, dict):
        raise ValueError("case-input.json must be a JSON object")

    expected = {"case_major_category", "provisional_disease", "genes", "case_facts"}
    missing = sorted(expected - set(document))
    if missing:
        raise ValueError("case-input.json is missing field(s): " + ", ".join(missing))
    extra = sorted(set(document) - expected)
    if extra:
        raise ValueError(
            "case-input.json has unexpected top-level field(s): " + ", ".join(extra)
        )

    category = document["case_major_category"]
    allowed = _allowed_categories(work)
    if category not in allowed:
        raise ValueError(
            f"case_major_category {category!r} is not a canonical case major category. "
            "Choose exactly one value from case-major-categories.json."
        )
    if not isinstance(document["provisional_disease"], str) or not document["provisional_disease"].strip():
        raise ValueError("provisional_disease must be non-empty supplied diagnostic wording")
    if not isinstance(document["genes"], list):
        raise ValueError("genes must be a list")
    if not isinstance(document["case_facts"], list) or not document["case_facts"]:
        raise ValueError("case_facts must be a non-empty list of preserved patient facts")
    return f"CMC1={category}"


def _allowed_categories(work: Path) -> set[str]:
    path = work / "case-major-categories.json"
    if path.is_file():
        try:
            document = json.loads(path.read_text(encoding="utf-8"))
            values = document.get("case_major_categories")
            if isinstance(values, list) and values:
                return set(values)
        except (OSError, json.JSONDecodeError):
            pass
    return set(vocab.CASE_MAJOR_CATEGORIES)


def _validate_diagnosis_draft(work: Path) -> str:
    refined = runtime.validate_diagnosis_draft(
        work / "report-draft-dx.yaml",
        work / "diagnostic_evidence.md",
        work / "reporting-rules-dx.md",
    )
    return f"CMC2={refined}"


def _validate_dx_summary(work: Path) -> str:
    path = runtime.validate_dx_summary(work)
    return f"validated {Path(path).name}"


def _validate_remainder(work: Path) -> str:
    runtime.validate_remainder_draft(
        work / "report-draft-remainder.yaml",
        work / "downstream_evidence.md",
        work / "reporting-rules-remainder.md",
    )
    return "validated report-draft-remainder.yaml"


def _validate_category(category: str) -> Callable[[Path], str]:
    def _validate(work: Path) -> str:
        path = runtime.validate_category(work, category)
        return f"validated {Path(path).name}"

    return _validate


# ---------------------------------------------------------------------------
# Permitted input sets.
# ---------------------------------------------------------------------------


def _inputs_1a(work: Path) -> list[Path]:
    return [work / "case-source.md"]


def _inputs_1b(work: Path) -> list[Path]:
    return [work / "case.md", work / "case-major-categories.json"]


def _inputs_3a(work: Path) -> list[Path]:
    return [
        work / "case.md",
        work / "case-major-categories.json",
        work / "diagnostic_evidence.md",
        work / "ngs-panel-scope.md",
        work / "reporting-rules-dx.md",
    ]


def _inputs_3b(work: Path) -> list[Path]:
    return [work / "case.md", work / "report-draft-dx.yaml"]


def _inputs_5(work: Path) -> list[Path]:
    # The CMC branch is already carried by reporting-rules-remainder.md, which the
    # deterministic step 4 wrote with or without injected diagnosis context. The
    # branch decision therefore stays in Python and is never re-derived here.
    return [
        work / "case.md",
        work / "downstream_evidence.md",
        work / "ngs-panel-scope.md",
        work / "reporting-rules-remainder.md",
    ]


def _manifest(work: Path) -> dict:
    path = work / "report-summary-manifest.yaml"
    if not path.is_file():
        raise ValueError(
            f"category manifest is missing: {path}. Run step 6a before any 6b step."
        )
    return runtime._load_manifest(Path(work))


def _inputs_category(work: Path) -> list[Path]:
    manifest = _manifest(work)
    permitted = [
        work / "case.md",
        work / "case-input.json",
        work / "report-draft.yaml",
        work / "report-draft-remainder.yaml",
        work / "report-summary-manifest.yaml",
    ]
    if manifest.get("cmc_changed") is False:
        permitted.append(work / "report-summary-dx.yaml")
    return permitted


def _category_required(category: str) -> Callable[[Path], tuple[bool, str]]:
    def _required(work: Path) -> tuple[bool, str]:
        manifest = _manifest(work)
        entry = (manifest.get("categories") or {}).get(category)
        if entry is None:
            raise ValueError(f"category manifest has no entry for {category!r}")
        status = entry.get("status")
        reason = entry.get("reason") or ""
        if status in {"pending_model_draft", "drafted"}:
            return True, reason
        return False, reason or f"manifest status {status!r} forbids a model call"

    return _required


# ---------------------------------------------------------------------------
# Deterministic step bodies.
# ---------------------------------------------------------------------------


def _run_case_stage(stage: str) -> Callable[[Path, str], list[str]]:
    def _run(work: Path, python: str) -> list[str]:
        from scripts import run_case

        run_case.run_stage(stage, work, python)
        return [f"case pipeline stage {stage} complete"]

    return _run


def _runtime_commands(*commands: str) -> Callable[[Path, str], list[str]]:
    def _run(work: Path, python: str) -> list[str]:
        lines: list[str] = []
        for command in commands:
            lines.extend(runtime.run(command, Path(work)))
        return lines

    return _run


def _step_4(work: Path, python: str) -> list[str]:
    lines = list(runtime.run("remainder-rules", Path(work)))
    lines.extend(_run_case_stage("downstream")(work, python))
    return lines


def _step_7(work: Path, python: str) -> list[str]:
    from scripts import package_run

    from workflows.categorical_v1 import step as step_module

    work = Path(work)
    debug_zip = work / "ngs-report-debug.zip"
    package_run.package_run_bundle(work, debug_zip)
    lines = [str(debug_zip)]
    bundle_zip = step_module.package_bundles(work)
    if bundle_zip is not None:
        lines.append(str(bundle_zip))
    return lines


# ---------------------------------------------------------------------------
# Step table.
# ---------------------------------------------------------------------------

_STEPS: list[ModelStep | DeterministicStep] = [
    ModelStep(
        step_id="1a",
        role="structure",
        title="Case capture",
        prompts=(SHARED_PROMPT_DIR / "capture_case.md",),
        inputs=_inputs_1a,
        output="case.md",
        seed_output=False,
        validate=_validate_case,
        modes=CAPTURE_MODES,
    ),
    ModelStep(
        step_id="1b",
        role="structure",
        title="Case structuring and CMC1",
        prompts=(SHARED_PROMPT_DIR / "structure_case.md",),
        inputs=_inputs_1b,
        output="case-input.json",
        seed_output=False,
        validate=_validate_case_input,
    ),
    DeterministicStep(
        step_id="2",
        title="Diagnosis evidence and R0/R1 draft template",
        run=_run_case_stage("diagnosis"),
    ),
    ModelStep(
        step_id="3a",
        role="judgment",
        title="R0/R1 diagnostic rule drafting and refined CMC",
        prompts=(
            PROMPT_DIR / "analyse_diagnosis.md",
            PROMPT_DIR / "citation_rules.md",
        ),
        inputs=_inputs_3a,
        output="report-draft-dx.yaml",
        seed_output=True,
        validate=_validate_diagnosis_draft,
    ),
    ModelStep(
        step_id="3b",
        role="summarisation",
        title="Integrated diagnosis synthesis",
        prompts=(
            PROMPT_DIR / "format_report.md",
            PROMPT_DIR / "citation_rules.md",
            PROMPT_DIR / "formatting" / "diagnosis.md",
        ),
        inputs=_inputs_3b,
        output="report-summary-dx.yaml",
        seed_output=True,
        validate=_validate_dx_summary,
        max_attempts=2,
        prepare=lambda work: runtime.prepare_dx_summary(Path(work)),
    ),
    DeterministicStep(
        step_id="4",
        title="Branch state, remainder rule view and downstream retrieval",
        run=_step_4,
    ),
    ModelStep(
        step_id="5",
        role="judgment",
        title="Remainder rule drafting",
        prompts=(
            PROMPT_DIR / "analyse_remainder.md",
            PROMPT_DIR / "citation_rules.md",
        ),
        inputs=_inputs_5,
        output="report-draft-remainder.yaml",
        seed_output=True,
        validate=_validate_remainder,
    ),
    DeterministicStep(
        step_id="6a",
        title="Retained-rule assembly and category manifest",
        run=_runtime_commands("prepare-categories"),
    ),
]

for _step_id, _category in CATEGORY_STEP_IDS.items():
    _STEPS.append(
        ModelStep(
            step_id=_step_id,
            role="summarisation",
            title=f"Final {_category} category draft",
            prompts=(
                PROMPT_DIR / "format_report.md",
                PROMPT_DIR / "citation_rules.md",
                PROMPT_DIR / "formatting" / f"{_category}.md",
            ),
            inputs=_inputs_category,
            output=f"report-summary-{_category}.yaml",
            seed_output=True,
            validate=_validate_category(_category),
            max_attempts=2,
            required=_category_required(_category),
        )
    )

_STEPS.extend(
    [
        DeterministicStep(
            step_id="6c",
            title="Summary assembly and final rendering",
            run=_runtime_commands("assemble-summary", "render"),
        ),
        DeterministicStep(
            step_id="7",
            title="Debug and model-step packaging",
            run=_step_7,
        ),
    ]
)

STEPS: dict[str, ModelStep | DeterministicStep] = {step.step_id: step for step in _STEPS}
ORDER: tuple[str, ...] = tuple(step.step_id for step in _STEPS)
MODEL_STEP_IDS: tuple[str, ...] = tuple(
    step.step_id for step in _STEPS if isinstance(step, ModelStep)
)


def get_step(step_id: str) -> ModelStep | DeterministicStep:
    try:
        return STEPS[step_id]
    except KeyError as exc:
        raise ValueError(
            f"unknown step {step_id!r}. Canonical order: " + " ".join(ORDER)
        ) from exc


def steps_for_mode(mode: str) -> tuple[str, ...]:
    return tuple(
        step_id
        for step_id in ORDER
        if (STEPS[step_id].modes is None or mode in (STEPS[step_id].modes or ()))
    )


def prompt_sequence(step: ModelStep) -> Sequence[Path]:
    return tuple(step.prompts) + COMMON_PROMPTS
