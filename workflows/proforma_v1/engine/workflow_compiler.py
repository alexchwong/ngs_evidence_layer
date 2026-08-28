"""Static compiler for selectable proforma-v1 declarative workflows."""
from __future__ import annotations

import hashlib
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
    stage_spec_obj: Any | None
    inputs: dict[str, Any]
    output: dict[str, Any]
    checks: tuple[dict, ...]
    transforms: tuple[Any, ...]
    transform: str | None
    when: dict | None
    review: dict | None
    evidence: dict | None
    execution: dict[str, Any]
    barrier_for: tuple[str, ...]
    raw: dict[str, Any]


@dataclass(frozen=True)
class CompiledWorkflow:
    workflow_id: str
    source: Path
    source_sha256: str
    asset_root: Path
    doc: dict[str, Any]
    steps: tuple[CompiledStep, ...]
    evidence_policies: dict
    self_groups: dict[str, dict]
    asset_sha256: dict[str, str]

    def step(self, step_id: str) -> CompiledStep:
        for step in self.steps:
            if step.id == step_id:
                return step
        raise KeyError(step_id)


def resolve_workflow_path(path: Path | str | None = None) -> Path:
    """Resolve CLI workflow selectors predictably.

    Absolute paths are used directly. A relative path that exists from the
    caller's cwd wins; otherwise it is resolved beneath the proforma-v1 package
    root so ``--workflow workflow/my.yaml`` works from the repository root.
    """
    if path is None:
        return DEFAULT_WORKFLOW.resolve()
    candidate = Path(path).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()
    if candidate.exists():
        return candidate.resolve()
    return (HERE / candidate).resolve()


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


def _asset_root(doc: dict, source: Path) -> Path:
    raw = doc.get("asset_root")
    if not raw:
        return HERE.resolve()
    candidate = Path(str(raw)).expanduser()
    if not candidate.is_absolute():
        candidate = HERE / candidate
    root = candidate.resolve()
    if not root.is_dir():
        raise WorkflowCompileError(f"asset_root does not exist or is not a directory: {raw!r}")
    return root


def _safe_asset(rel: str, *, kind: str, asset_root: Path) -> Path:
    raw = Path(rel).expanduser()
    path = raw.resolve() if raw.is_absolute() else (asset_root / raw).resolve()
    # Explicit asset_root is the trust boundary: all referenced assets must live
    # beneath it. This permits external experiment packages without arbitrary
    # path traversal from YAML.
    try:
        path.relative_to(asset_root.resolve())
    except ValueError as exc:
        raise WorkflowCompileError(f"{kind} path escapes asset_root: {rel!r}") from exc
    if not path.is_file():
        raise WorkflowCompileError(f"missing {kind}: {rel!r}")
    return path


def _validate_reference(ref: str, *, produced: set[str], step_id: str) -> None:
    if ref.startswith(("run.", "assets.", "settings.", "feedback.")) or ref == "owner.cards":
        return
    if ref.startswith("artifacts."):
        name = ref.split(".", 1)[1]
        if name not in produced:
            raise WorkflowCompileError(f"step {step_id!r} references artifact {name!r} before it can exist")
        return
    raise WorkflowCompileError(f"step {step_id!r} has unsupported input reference {ref!r}")


def _topological(step_docs: dict[str, dict]) -> list[str]:
    order = list(step_docs)
    for sid, cfg in step_docs.items():
        for need in cfg.get("needs") or []:
            if need not in step_docs:
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


def _dependency_helpers(step_docs: dict[str, dict]):
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

    return deps, depends_on


def compile_workflow(path: Path | str | None = None) -> CompiledWorkflow:
    source = resolve_workflow_path(path)
    try:
        doc = load_workflow(source)
    except WorkflowLoadError as exc:
        raise WorkflowCompileError(str(exc)) from exc
    _validate_schema(doc)
    asset_root = _asset_root(doc, source)
    roles = _known_roles()
    policy_map = policies_from_workflow(doc)

    for name, policy in policy_map.items():
        for pass_name in ("assignment", "audit", "adjudication"):
            row = getattr(policy, pass_name)
            if row.get("role") not in roles:
                raise WorkflowCompileError(f"evidence policy {name!r}.{pass_name} names unknown model role {row.get('role')!r}")
            prompt = _safe_asset(row["prompt"], kind="prompt", asset_root=asset_root)
            try:
                prompt_renderer.compile_asset(prompt, root=asset_root, declared_inputs=set())
            except Exception as exc:
                raise WorkflowCompileError(f"evidence policy {name!r}.{pass_name}: {exc}") from exc

    step_docs = doc["steps"]
    ordered = _topological(step_docs)
    deps, depends_on = _dependency_helpers(step_docs)
    produced: set[str] = set()
    compiled: list[CompiledStep] = []

    self_groups = dict(doc.get("self_groups") or {})
    memberships: dict[str, list[str]] = {name: [] for name in self_groups}

    for sid in ordered:
        cfg = step_docs[sid]
        role = cfg.get("role")
        if role and role not in roles:
            raise WorkflowCompileError(f"step {sid!r} names unknown model role {role!r}")
        stage = cfg.get("stage")
        stage_obj = None
        if stage:
            try:
                if "/" in stage or "\\" in stage or stage.endswith(('.yaml','.yml')):
                    stage_path=_safe_asset(stage,kind="stage",asset_root=asset_root)
                    expected=sid if sid in {"prognosis","treatment","biomarker","germline"} else None
                    stage_obj=stage_spec.load_path(stage_path,expected_stage=expected)
                else:
                    stage_obj=stage_spec.load(stage)
            except Exception as exc:
                raise WorkflowCompileError(f"step {sid!r} has invalid stage {stage!r}: {exc}") from exc
        input_specs = cfg.get("inputs") or {}
        for name, binding in input_specs.items():
            if not isinstance(binding, dict) or not isinstance(binding.get("from"), str):
                raise WorkflowCompileError(f"step {sid!r} input {name!r} must declare a from reference")
            _validate_reference(binding["from"], produced=produced, step_id=sid)
        prompt_path = None
        if cfg.get("prompt"):
            prompt_path = _safe_asset(cfg["prompt"], kind="prompt", asset_root=asset_root)
            try:
                prompt_renderer.compile_asset(prompt_path, root=asset_root, declared_inputs=set(input_specs))
            except Exception as exc:
                raise WorkflowCompileError(f"step {sid!r} prompt invalid: {exc}") from exc
        output = dict(cfg.get("output") or {})
        if output.get("schema"):
            schema_path = _safe_asset(output["schema"], kind="schema", asset_root=asset_root)
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
        if condition and (len(condition) != 1 or next(iter(condition)) not in CONDITION_KEYS):
            raise WorkflowCompileError(f"step {sid!r} has unsupported condition {condition!r}")
        execution = dict(cfg.get("execution") or {})
        group = execution.get("self_group")
        if group:
            if group not in self_groups:
                raise WorkflowCompileError(f"step {sid!r} names unknown self_group {group!r}")
            memberships[group].append(sid)
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
        review = cfg.get("review")
        if review:
            target = review["target"]
            if target not in step_docs:
                raise WorkflowCompileError(f"step {sid!r} reviews unknown target {target!r}")
            if not depends_on(sid, target):
                raise WorkflowCompileError(f"step {sid!r} review target {target!r} must be upstream")
            on_fail = review["on_fail"]
            if on_fail.get("route_to") and on_fail["route_to"] not in step_docs:
                raise WorkflowCompileError(f"step {sid!r} review routes to unknown step {on_fail['route_to']!r}")
            exhausted = on_fail.get("exhausted") or {}
            if exhausted.get("action") == "route_to" and exhausted.get("route_to") not in step_docs:
                raise WorkflowCompileError(f"step {sid!r} exhausted review routes to unknown step {exhausted.get('route_to')!r}")
            feedback = on_fail.get("feedback")
            if feedback:
                own_artifact=(cfg.get("output") or {}).get("artifact")
                own_ref=f"artifacts.{own_artifact}" if own_artifact else None
                if feedback["from"] != own_ref:
                    _validate_reference(feedback["from"], produced=produced, step_id=sid)
                target_inputs = step_docs[target].get("inputs") or {}
                if feedback["as"] not in target_inputs:
                    raise WorkflowCompileError(
                        f"step {sid!r} review feedback alias {feedback['as']!r} is not a declared input of target {target!r}"
                    )
        artifact = output.get("artifact")
        if artifact:
            if artifact in produced:
                raise WorkflowCompileError(f"step {sid!r} collides with existing output artifact {artifact!r}")
            produced.add(artifact)
        compiled.append(CompiledStep(
            id=sid, type=cfg["type"], needs=tuple(cfg.get("needs") or ()), role=role,
            prompt=prompt_path, stage=stage, stage_spec_obj=stage_obj, inputs=dict(input_specs), output=output,
            checks=tuple(cfg.get("checks") or ()), transforms=tuple(cfg.get("transforms") or ()),
            transform=cfg.get("transform"), when=condition, review=dict(review) if review else None,
            evidence=dict(evidence) if evidence else None, execution=execution,
            barrier_for=barrier_for, raw=dict(cfg),
        ))

    # A self batch is only legal for genuinely independent logical operations.
    for group, members in memberships.items():
        for i, left in enumerate(members):
            for right in members[i + 1:]:
                if depends_on(left, right) or depends_on(right, left):
                    raise WorkflowCompileError(
                        f"self_group {group!r} contains dependent steps {left!r} and {right!r}; needs must represent real dependencies"
                    )

    barriers = {
        sid: set(cfg.get("barrier_for") or [])
        for sid, cfg in step_docs.items() if cfg.get("type") == "evidence_adjudication"
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

    referenced_assets=set()
    for step in compiled:
        if step.prompt: referenced_assets.add(step.prompt.resolve())
        if step.stage_spec_obj is not None: referenced_assets.add(step.stage_spec_obj.path.resolve())
        schema_rel=(step.output or {}).get("schema")
        if schema_rel: referenced_assets.add(_safe_asset(schema_rel,kind="schema",asset_root=asset_root).resolve())
    for policy in policy_map.values():
        for pass_name in ("assignment","audit","adjudication"):
            referenced_assets.add(_safe_asset(getattr(policy,pass_name)["prompt"],kind="prompt",asset_root=asset_root).resolve())
    asset_sha256={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(referenced_assets)}
    return CompiledWorkflow(
        workflow_id=doc["workflow_id"], source=source,
        source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(), asset_root=asset_root,
        doc=doc, steps=tuple(compiled), evidence_policies=policy_map, self_groups=self_groups,asset_sha256=asset_sha256,
    )


def describe(workflow: CompiledWorkflow | None = None) -> list[str]:
    workflow = workflow or compile_workflow()
    lines = [
        f"WORKFLOW={workflow.workflow_id}", f"WORKFLOW_FILE={workflow.source}",
        f"WORKFLOW_SHA256={workflow.source_sha256}", f"STEPS={len(workflow.steps)}",
    ]
    for i, step in enumerate(workflow.steps, 1):
        bits = [f"{i:02d} {step.id}", f"type={step.type}"]
        if step.needs: bits.append(f"needs={','.join(step.needs)}")
        if step.role: bits.append(f"role={step.role}")
        if step.execution.get("self_group"): bits.append(f"self_group={step.execution['self_group']}")
        if (step.execution.get("self") or {}).get("enabled") is False: bits.append("self=disabled")
        lines.append(" ".join(bits))
    return lines
