"""Minimal terraced-v5 run-directory layout."""
from __future__ import annotations
import re
from pathlib import Path
MODEL_STEPS_DIR='model_steps'; INTERMEDIATES_DIR='intermediates'; LOGS_DIR='logs'; _NUMBERED_RE=re.compile(r'^(\d{3})_(.+)$')

def ensure_dirs(work:Path)->None:
    work=Path(work); (work/MODEL_STEPS_DIR).mkdir(parents=True,exist_ok=True); (work/INTERMEDIATES_DIR).mkdir(parents=True,exist_ok=True); (work/LOGS_DIR/'errors').mkdir(parents=True,exist_ok=True)
def _slug(text:str)->str:
    s=''.join(c.lower() if c.isalnum() else '_' for c in str(text)).strip('_')
    while '__' in s:s=s.replace('__','_')
    return s or 'artifact'
def _find(parent:Path,name:str):
    slug=_slug(name); found=[]
    if parent.is_dir():
        for p in parent.iterdir():
            m=_NUMBERED_RE.fullmatch(p.name)
            if p.is_dir() and m and m.group(2)==slug: found.append((int(m.group(1)),p))
    return sorted(found)[0][1] if found else None
def _next(parent:Path):
    nums=[]
    if parent.is_dir():
        for p in parent.iterdir():
            m=_NUMBERED_RE.fullmatch(p.name)
            if p.is_dir() and m: nums.append(int(m.group(1)))
    return max(nums,default=0)+1
def _numbered(work:Path,namespace:str,name:str,create:bool):
    parent=Path(work)/namespace
    if create: parent.mkdir(parents=True,exist_ok=True)
    existing=_find(parent,name)
    if existing is not None:return existing
    p=parent/f'{_next(parent):03d}_{_slug(name)}'
    if create:p.mkdir(parents=True,exist_ok=True)
    return p
def intermediate_dir(work:Path,logical_name:str,*,existing:bool=True)->Path: return _numbered(work,INTERMEDIATES_DIR,logical_name,not existing)
def model_step_dir(work:Path,call_id:str,*,existing:bool=True)->Path: return _numbered(work,MODEL_STEPS_DIR,call_id,not existing)
def _file(work:Path,group:str,name:str,existing:bool,legacy:list[Path]|None=None)->Path:
    d=intermediate_dir(work,group,existing=existing); p=d/name
    if existing and not p.exists():
        for old in legacy or []:
            q=Path(work)/old
            if q.exists(): return q
    return p
def input(work:Path,name:str,*,existing:bool=True)->Path:
    if name=='case.md': return Path(work)/'case.md'
    return _file(work,'structured_case' if name=='case.json' else 'setup',name,existing,[Path(name),Path('input')/name])
def setup(work:Path,name:str,*,existing:bool=True)->Path: return _file(work,'setup',name,existing,[Path(name),Path('input')/name])
def logs(work:Path)->Path:
    p=Path(work)/LOGS_DIR; p.mkdir(parents=True,exist_ok=True); return p
def errors(work:Path)->Path:
    p=logs(work)/'errors'; p.mkdir(parents=True,exist_ok=True); return p
