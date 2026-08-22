"""Discovery/validation for declarative terraced-v3 schedulers."""
from __future__ import annotations
from pathlib import Path
from workflows.terraced_v3 import scheduler_engine

HERE=Path(__file__).resolve().parent
ROOT=HERE/"schedulers"


def _paths():
    rows=[]
    seen=set()
    if ROOT.is_dir():
        for p in ROOT.iterdir():
            if p.is_dir() and (p/"scheduler.yaml").is_file():
                plan=scheduler_engine.load_yaml(p/"scheduler.yaml")
                if plan.scheduler_id in seen: raise ValueError(f"duplicate scheduler id {plan.scheduler_id!r}")
                seen.add(plan.scheduler_id)
                order=int((plan.doc.get("scheduler") or {}).get("order",999))
                rows.append((order,plan.scheduler_id,p/"scheduler.yaml"))
    return {sid:path for _,sid,path in sorted(rows,key=lambda row:(row[0],row[1]))}


def names()->tuple[str,...]: return tuple(_paths())

def load(name:str):
    paths=_paths()
    if name not in paths: raise ValueError(f"unknown terraced-v3 scheduler {name!r}; choose one of: {', '.join(paths)}")
    return scheduler_engine.load_yaml(paths[name])

def descriptions()->dict[str,str]: return {name:load(name).description for name in names()}

def check(name:str)->scheduler_engine.SchedulerPlan: return load(name)
