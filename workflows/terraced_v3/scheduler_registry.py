"""Discovery/validation for declarative terraced-v3 schedulers by phase."""
from __future__ import annotations
from pathlib import Path
from workflows.terraced_v3 import scheduler_engine

HERE = Path(__file__).resolve().parent
ROOT = HERE / "schedulers"
PHASES = ("diagnosis", "ptbg", "summarization")


def _paths(phase: str) -> dict[str, Path]:
    if phase not in PHASES:
        raise ValueError(f"unknown scheduler phase {phase!r}; choose one of: {', '.join(PHASES)}")
    base = ROOT / phase
    rows=[]; seen=set()
    if base.is_dir():
        for p in base.iterdir():
            if p.is_dir() and (p/"scheduler.yaml").is_file():
                plan=scheduler_engine.load_yaml(p/"scheduler.yaml", expected_phase=phase)
                if plan.scheduler_id in seen: raise ValueError(f"duplicate {phase} scheduler id {plan.scheduler_id!r}")
                seen.add(plan.scheduler_id)
                order=int((plan.doc.get("scheduler") or {}).get("order",999))
                rows.append((order,plan.scheduler_id,p/"scheduler.yaml"))
    return {sid:path for _,sid,path in sorted(rows,key=lambda row:(row[0],row[1]))}


def names(phase: str = "ptbg") -> tuple[str,...]:
    return tuple(_paths(phase))


def load(name: str, phase: str = "ptbg"):
    paths=_paths(phase)
    if name not in paths:
        raise ValueError(f"unknown terraced-v3 {phase} scheduler {name!r}; choose one of: {', '.join(paths)}")
    return scheduler_engine.load_yaml(paths[name], expected_phase=phase)


def descriptions(phase: str = "ptbg") -> dict[str,str]:
    return {name:load(name,phase).description for name in names(phase)}


def check(name: str, phase: str = "ptbg") -> scheduler_engine.SchedulerPlan:
    return load(name, phase)
