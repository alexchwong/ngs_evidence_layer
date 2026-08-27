"""Static compiler for the canonical proforma-v1 declarative workflow."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from workflows.proforma_v1 import pipeline_registry, stage_spec
from workflows.proforma_v1.engine import assemblers, checks, prompt_renderer, transforms
from workflows.proforma_v1.engine.evidence import policies_from_workflow
from workflows.proforma_v1.engine.workflow_loader import DEFAULT_WORKFLOW, WorkflowLoadError, load as load_workflow

HERE = Path(__file__).resolve().parents[1]
WORKFLOW_SCHEMA = HERE / "schemas" / "workflow.schema.json"
PROMPT_ROOT = HERE / "prompts"
CONDITION_KEYS = {"setting", "artifact_changed", "has_items", "artifact_true", "predicate"}


class WorkflowCompileError(ValueError):
    pass


@dataclass(frozen=True)
class CompiledStep:
    id: str
    type: str
    needs: tuple[str, ...]
    role: str | None
    prompt: Path | None
    stage: str | None
    inputs: dict[str, Any]
    output: dict[str, Any]
    checks: tuple[dict, ...]
    transforms: tuple[Any, ...]
    transform: str | None
    when: dict | None
    evidence: dict | None
    execution: dict[str, Any]
    barrier_for: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class CompiledWorkflow:
    workflow_id: str
    source: Path
    doc: dict[str, Any]
    steps: tuple[CompiledStep, ...]
    evidence_policies: dict

    def step(self, step_id: str) -> CompiledStep:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)


def _schema() -> dict:
    try:
        doc = json.loads(WORKFLOW_SCHEMA.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(doc)
        return doc
    except Exception as exc:
        raise WorkflowCompileError(f"invalid workflow schema {WORKFLOW_SCHEMA}: {exc}") from exc


def _validate_schema(doc: dict) -> None:
    errors = sorted(Draft202012Validator(_schema()).iter_errors(doc), key=lambda e: list(map(str, e.absolute_path)))
    if errors:
        first = errors[0]
        where = ".".join(str(p) for p in first.absolute_path) or "<root>"
        raise WorkflowCompileError(f"workflow schema violation at {where}: {first.message}")


def _known_roles() -> set[str]:
    roles: set[str] = set()
    for name in pipeline_registry.names():
        plan = pipeline_registry.load(name)
        roles.update((plan.doc.get("model_roles") or plan.doc.get("models") or {}).keys())
    return roles


def _safe_asset(rel: str, *, kind: str) -> Path:
    path = (HERE / rel).resolve()
    try:
        path.relative_to(HERE.resolve())
    except ValueError as exc:
        raise WorkflowCompileError(f"{kind} path escapes workflow root: {rel!r}") from exc
    if not path.is_file():
        raise WorkflowCompileError(f"missing {kind}: {rel!r}")
    return path


def _validate_reference(ref: str, *, produced: set[str], step_id: str) -> None:
    if ref.startswith(("run.", "assets.", "settings.")) or ref == "owner.cards":
        return
    if ref.startswith("artifacts."):
        name = ref.split(".", 1)[1]
        if name not in produced:
            raise WorkflowCompileError(f"step {step_id!r} references artifact {name!r} before it can exist")
        return
    raise WorkflowCompileError(f"step {step_id!r} has unsupported input reference {ref!r}")


def _topological(step_docs: dict[str, dict]) -> list[str]:
    order = list(step_docs)
    unknown = []
    for sid, cfg in step_docs.items():
        for need in cfg.get("needs") or []:
            if need not in step_docs:
                unknown.append((sid, need))
    if unknown:
        sid, need = unknown[0]
        raise WorkflowCompileError(f"step {sid!r} depends on unknown step {need!r}")
    pending = set(order)
    resolved: list[str] = []
    while pending:
        ready = [sid for sid in order if sid in pending and all(n in resolved for n in (step_docs[sid].get("needs") or []))]
        if not ready:
            raise WorkflowCompileError(f"workflow dependency cycle involving: {sorted(pending)}")
        for sid in ready:
            pending.remove(sid)
            resolved.append(sid)
    return resolved


def compile_workflow(path: Path | str | None = None) -> CompiledWorkflow:
    source = Path(path or DEFAULT_WORKFLOW).resolve()
    try:
        doc = load_workflow(source)
    except WorkflowLoadError as exc:
        raise WorkflowCompileError(str(exc)) from exc
    _validate_schema(doc)
    if doc.get("workflow_id") != "proforma-v1":
        raise WorkflowCompileError(f"workflow_id must be 'proforma-v1', got {doc.get('workflow_id')!r}")

    roles = _known_roles()
    policy_map = policies_from_workflow(doc)
    for name, policy in policy_map.items():
        for pass_name in ("assignment", "audit", "adjudication"):
            row = getattr(policy, pass_name)
            if row.get("role") not in roles:
                raise WorkflowCompileError(f"evidence policy {name!r}.{pass_name} names unknown model role {row.get('role')!r}")
            prompt = _safe_asset(row["prompt"], kind="prompt")
            try:
                prompt_renderer.compile_asset(prompt, root=PROMPT_ROOT, declared_inputs=set())
            except Exception as exc:
                raise WorkflowCompileError(f"evidence policy {name!r}.{pass_name}: {exc}") from exc

    step_docs = doc["steps"]
    ordered = _topological(step_docs)
    produced: set[str] = set()
    compiled: list[CompiledStep] = []

    for sid in ordered:
        cfg = step_docs[sid]
        role = cfg.get("role")
        if role and role not in roles:
            raise WorkflowCompileError(f"step {sid!r} names unknown model role {role!r}")
        stage = cfg.get("stage")
        if stage:
            try:
                stage_spec.load(stage)
            except Exception as exc:
                raise WorkflowCompileError(f"step {sid!r} has invalid stage {stage!r}: {exc}") from exc
        input_specs = cfg.get("inputs") or {}
        for name, binding in input_specs.items():
            if not isinstance(binding, dict) or not isinstance(binding.get("from"), str):
                raise WorkflowCompileError(f"step {sid!r} input {name!r} must declare a from reference")
            _validate_reference(binding["from"], produced=produced, step_id=sid)
        prompt_path = None
        if cfg.get("prompt"):
            prompt_path = _safe_asset(cfg["prompt"], kind="prompt")
            try:
                prompt_renderer.compile_asset(prompt_path, root=PROMPT_ROOT, declared_inputs=set(input_specs))
            except Exception as exc:
                raise WorkflowCompileError(f"step {sid!r} prompt invalid: {exc}") from exc
        output = dict(cfg.get("output") or {})
        if output.get("schema"):
            schema_path = _safe_asset(output["schema"], kind="schema")
            try:
                schema_doc = json.loads(schema_path.read_text(encoding="utf-8"))
                Draft202012Validator.check_schema(schema_doc)
            except Exception as exc:
                raise WorkflowCompileError(f"step {sid!r} schema invalid: {exc}") from exc
        assembly = output.get("assembly") or {}
        if assembly and assembly.get("type") not in assemblers.REGISTRY:
            raise WorkflowCompileError(f"step {sid!r} names unknown assembler {assembly.get('type')!r}")
        for check in cfg.get("checks") or []:
            name = check.get("rule")
            if name not in checks.REGISTRY:
                raise WorkflowCompileError(f"step {sid!r} names unknown check rule {name!r}")
            if name == "custom" and check.get("handler") not in checks.CUSTOM_REGISTRY:
                raise WorkflowCompileError(f"step {sid!r} names unknown custom check handler {check.get('handler')!r}")
        transform_names = []
        if cfg.get("transform"):
            transform_names.append(cfg["transform"])
        for item in cfg.get("transforms") or []:
            transform_names.append(item if isinstance(item, str) else item.get("transform"))
        for name in transform_names:
            if name not in transforms.REGISTRY:
                raise WorkflowCompileError(f"step {sid!r} names unknown transform {name!r}")
        condition = cfg.get("when")
        if condition:
            if len(condition) != 1 or next(iter(condition)) not in CONDITION_KEYS:
                raise WorkflowCompileError(f"step {sid!r} has unsupported condition {condition!r}")
        barrier_for = tuple(cfg.get("barrier_for") or ())
        if barrier_for and cfg.get("type") != "evidence_adjudication":
            raise WorkflowCompileError(f"step {sid!r} uses barrier_for but is not evidence_adjudication")
        for owner in barrier_for:
            if owner not in step_docs:
                raise WorkflowCompileError(f"step {sid!r} barrier_for references unknown step {owner!r}")
        evidence = cfg.get("evidence")
        if evidence:
            if evidence.get("policy") not in policy_map:
                raise WorkflowCompileError(f"step {sid!r} names unknown evidence policy {evidence.get('policy')!r}")
            if evidence.get("timing") not in {"blocking", "deferred"}:
                raise WorkflowCompileError(f"step {sid!r} has invalid evidence timing {evidence.get('timing')!r}")
            cards = evidence.get("cards") or {}
            if cards:
                _validate_reference(cards.get("from", ""), produced=produced, step_id=sid)
        artifact = output.get("artifact")
        if artifact:
            if artifact in produced:
                raise WorkflowCompileError(f"step {sid!r} collides with existing output artifact {artifact!r}")
            produced.add(artifact)
        compiled.append(CompiledStep(
            id=sid,
            type=cfg["type"],
            needs=tuple(cfg.get("needs") or ()),
            role=role,
            prompt=prompt_path,
            stage=stage,
            inputs=dict(input_specs),
            output=output,
            checks=tuple(cfg.get("checks") or ()),
            transforms=tuple(cfg.get("transforms") or ()),
            transform=cfg.get("transform"),
            when=condition,
            evidence=dict(evidence) if evidence else None,
            execution=dict(cfg.get("execution") or {}),
            barrier_for=barrier_for,
            raw=dict(cfg),
        ))

    deps = {sid: set(step_docs[sid].get("needs") or []) for sid in step_docs}

    def depends_on(step_id: str, ancestor_id: str) -> bool:
        seen: set[str] = set()
        stack = list(deps.get(step_id) or ())
        while stack:
            cur = stack.pop()
            if cur == ancestor_id:
                return True
            if cur in seen:
                continue
            seen.add(cur)
            stack.extend(deps.get(cur) or ())
        return False

    barriers = {
        sid: set(cfg.get("barrier_for") or [])
        for sid, cfg in step_docs.items()
        if cfg.get("type") == "evidence_adjudication"
    }
    for review_id, cfg in step_docs.items():
        ev = cfg.get("evidence") or {}
        if cfg.get("type") != "evidence_review" or ev.get("timing") != "deferred":
            continue
        review_barriers = [bid for bid, owners in barriers.items() if review_id in owners]
        if not review_barriers:
            raise WorkflowCompileError(f"deferred evidence step {review_id!r} has no adjudication barrier")
        for bid in review_barriers:
            if not depends_on(bid, review_id):
                raise WorkflowCompileError(f"evidence barrier {bid!r} is not downstream of deferred step {review_id!r}")
        for consumer_id, consumer in step_docs.items():
            if consumer_id in review_barriers or not depends_on(consumer_id, review_id):
                continue
            if consumer.get("type") in {"evidence_review", "evidence_adjudication"}:
                continue
            if not any(depends_on(consumer_id, bid) for bid in review_barriers):
                raise WorkflowCompileError(
                    f"step {consumer_id!r} consumes deferred evidence {review_id!r} without its adjudication barrier"
                )

    return CompiledWorkflow(doc["workflow_id"], source, doc, tuple(compiled), policy_map)


def describe(workflow: CompiledWorkflow | None = None) -> list[str]:
    workflow = workflow or compile_workflow()
    lines = [f"WORKFLOW={workflow.workflow_id}", f"STEPS={len(workflow.steps)}"]
    for i, step in enumerate(workflow.steps, 1):
        bits = [f"{i:02d} {step.id}", f"type={step.type}"]
        if step.needs:
            bits.append(f"needs={','.join(step.needs)}")
        if step.role:
            bits.append(f"role={step.role}")
        lines.append(" ".join(bits))
    return lines
