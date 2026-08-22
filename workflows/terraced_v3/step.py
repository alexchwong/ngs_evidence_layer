#!/usr/bin/env python3
"""Scripted terraced-v3 hard-fact workflow runner."""
from __future__ import annotations

import argparse
import contextlib
import json
import shutil
import sys
import tempfile
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.core import citations, corpus
from scripts.core import retrieval as core_retrieval
from scripts.core import validated_model_task
from scripts.core import syntax_repair
from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import read_workflow_state, write_workflow_state
from validation.package_marking import package_marking_bundle
from validation import cases as validation_cases
from workflows.terraced_v3 import card_identity, layout, model_client, model_registry, rendering, runtime
from workflows.terraced_v3 import scheduler_engine, scheduler_registry, scheduler_primitives

WORKFLOW_ID = "terraced-v3"
HERE = Path(__file__).resolve().parent
PROMPTS = HERE / "prompts"
SETTINGS_PATH = HERE / "settings.json"
SETTINGS_TEMPLATE_PATH = HERE / "settings.json.template"
EXIT_OK = 0
EXIT_FAILURE = 1
EXIT_HANDOFF = 10
VALIDATION_MODES = {"nel-validate", "nel-validate-function", "nel-validate-brief"}
MARKING_PREFIX = {
    "nel-validate": "nel-validation",
    "nel-validate-function": "nel-validation-function",
    "nel-validate-brief": "nel-validation-brief",
}
_EXECUTION_STARTED_AT: float | None = None


class StepFailure(RuntimeError):
    pass


class Handoff(RuntimeError):
    def __init__(self, call_id: str, prompt: Path, output: Path):
        self.call_id = call_id; self.prompt = prompt; self.output = output
        super().__init__(call_id)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _atomic_write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(text, encoding="utf-8")
    temporary.replace(path)
    return path


def load_settings() -> dict:
    path = SETTINGS_PATH if SETTINGS_PATH.is_file() else SETTINGS_TEMPLATE_PATH
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise StepFailure(f"invalid terraced-v3 settings {path}: {exc}") from exc
    if doc.get("schema_version") != 1:
        raise StepFailure(f"unsupported terraced-v3 settings schema in {path}")
    return doc


def configured_profile() -> str | None:
    value = load_settings().get("model_profile")
    return value if isinstance(value, str) and value else None


class _LoggedStream:
    def __init__(self, terminal, log_handle, *, mask_terminal: bool):
        self.terminal=terminal; self.log_handle=log_handle; self.mask_terminal=mask_terminal; self.buffer=""
    def write(self,text:str)->int:
        self.log_handle.write(text); self.log_handle.flush()
        if not self.mask_terminal:
            self.terminal.write(text); self.terminal.flush(); return len(text)
        self.buffer += text
        while "\n" in self.buffer:
            line,self.buffer=self.buffer.split("\n",1)
            if not (line.startswith("[retrieve]") or line.startswith("[terraced render]") or "validation pass" in line.lower()):
                self.terminal.write(line+"\n"); self.terminal.flush()
        return len(text)
    def flush(self): self.log_handle.flush(); self.terminal.flush()
    def __getattr__(self,name): return getattr(self.terminal,name)


@contextlib.contextmanager
def _cli_logging(work: Path):
    path=work/"workflow.log"; path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as handle:
        with contextlib.redirect_stdout(_LoggedStream(sys.stdout,handle,mask_terminal=False)), contextlib.redirect_stderr(_LoggedStream(sys.stderr,handle,mask_terminal=True)):
            yield


def _elapsed()->int:
    global _EXECUTION_STARTED_AT
    now=time.time()
    if _EXECUTION_STARTED_AT is None: _EXECUTION_STARTED_AT=now
    return max(0,int(now-_EXECUTION_STARTED_AT))


def _status(message:str)->None:
    print(f"[ {_elapsed():04d} ] - {message}",file=sys.stderr)


def _require_work(work:Path)->dict:
    state=read_workflow_state(work)
    if state.get("workflow_id")!=WORKFLOW_ID:
        raise StepFailure(f"work directory is bound to {state.get('workflow_id')!r}, not {WORKFLOW_ID!r}")
    return state


def _run_state_path(work:Path)->Path: return layout.state(work,"terraced-v3-run.json",existing=False)
def _load_run_state(work:Path)->dict: return json.loads(_read(_run_state_path(work)))
def _save_run_state(work:Path,state:dict)->None: _atomic_write(_run_state_path(work),json.dumps(state,indent=2,ensure_ascii=False)+"\n")
def _profile(work:Path,selector:str|None,role:str): return model_registry.resolve(role,selector,work)


def _bundle_paths(work:Path,call_id:str)->tuple[Path,Path,Path]:
    safe="".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in call_id)
    root=layout.model_step_dir(work,safe,existing=False)
    return root,root/"prompt.md",root/"messages.json"


def _render_bundle(call_id:str,messages:list[dict[str,str]],output:Path,validator_error:str|None=None)->str:
    lines=[f"# Terraced-v3 model operation — {call_id}",""]
    for i,msg in enumerate(messages,1): lines.extend([f"## Message {i} — {msg['role']}","",msg["content"].rstrip(),""])
    if validator_error: lines.extend(["## Deterministic validator error","",validator_error,"",validated_model_task.retry_instruction(ValueError(validator_error)),""])
    lines.extend(["## Output","",f"Write only the requested artifact to: `{output}`","Do not modify any other file.",""])
    return "\n".join(lines)


def _syntax_repair_callback(*,binding,root:Path,call_id:str):
    repair_root=root/"syntax-repair"; repair_root.mkdir(parents=True,exist_ok=True)

    def repair(prompt:str,attempt:int)->str:
        _status(f"  {call_id}: syntax repair {attempt}/2")
        prompt_path=repair_root/f"attempt-{attempt}.prompt.md"
        output_path=repair_root/f"attempt-{attempt}.output"
        _atomic_write(prompt_path,prompt)
        if binding.is_self:
            if output_path.is_file():
                return _read(output_path)
            raise Handoff(f"{call_id}-syntax-repair-{attempt}",prompt_path,output_path)
        try:
            completion=model_client.complete_messages(binding,[
                {"role":"system","content":syntax_repair.SYNTAX_REPAIR_SYSTEM_PROMPT},
                {"role":"user","content":prompt},
            ])
        except model_client.TruncatedCompletion as exc:
            response=exc.content
        except RuntimeError as exc:
            raise StepFailure(str(exc)) from exc
        else:
            response=completion.content if isinstance(completion,model_client.Completion) else completion
        _atomic_write(output_path,response.rstrip()+"\n")
        return response
    return repair


def _log_syntax_attempts(root:Path,attempts)->None:
    repair_root=root/"syntax-repair"; repair_root.mkdir(parents=True,exist_ok=True)
    for attempt in attempts:
        if attempt.parser_error:
            _atomic_write(repair_root/f"attempt-{attempt.index}.parser-error.txt",attempt.parser_error+"\n")
        if attempt.preservation_error:
            _atomic_write(repair_root/f"attempt-{attempt.index}.preservation-error.txt",attempt.preservation_error+"\n")


def _log_syntax_result(root:Path,result:syntax_repair.SyntaxRepairResult)->None:
    repair_root=root/"syntax-repair"; repair_root.mkdir(parents=True,exist_ok=True)
    if result.deterministic_repairs:
        _atomic_write(repair_root/"deterministic-repairs.txt","\n".join(result.deterministic_repairs)+"\n")
    _log_syntax_attempts(root,result.model_attempts)


def _reserialize_structured(*,binding,root:Path,call_id:str,raw:str,format_name:str,error:syntax_repair.SyntaxRepairExhausted)->str:
    repair_root=root/"syntax-repair"; repair_root.mkdir(parents=True,exist_ok=True)
    prompt=syntax_repair.reserialization_prompt(
        format_name=format_name,
        broken_text=error.candidate,
        parser_error=error.parser_error,
    )
    prompt_path=repair_root/"reserialization.prompt.md"; output_path=repair_root/"reserialization.output"
    _atomic_write(prompt_path,prompt)
    _status(f"  {call_id}: syntax repair exhausted; short reserialization")
    if binding.is_self:
        if not output_path.is_file():
            raise Handoff(f"{call_id}-reserialize",prompt_path,output_path)
        response=_read(output_path)
    else:
        try:
            completion=model_client.complete_messages(binding,[
                {"role":"system","content":syntax_repair.SYNTAX_REPAIR_SYSTEM_PROMPT},
                {"role":"user","content":prompt},
            ])
        except model_client.TruncatedCompletion as exc:
            response=exc.content
        except RuntimeError as exc:
            raise StepFailure(str(exc)) from exc
        else:
            response=completion.content if isinstance(completion,model_client.Completion) else completion
        _atomic_write(output_path,response.rstrip()+"\n")
    preserved=syntax_repair.preservation_error(error.candidate,response)
    if preserved:
        _atomic_write(repair_root/"reserialization.preservation-error.txt",preserved+"\n")
        raise ValueError("short reserialization changed informational content and was rejected: "+preserved)
    result=syntax_repair.repair_structured_output(response,format_name=format_name,model_attempts=0)
    _log_syntax_result(root,result)
    return result.text


def _prepare_candidate(*,raw:str,structured_format:str|None,binding,root:Path,call_id:str)->tuple[str,list[str]]:
    if structured_format is None:
        candidate,repairs=validated_model_task.safe_representation_repair(raw)
        return candidate,repairs
    try:
        result=syntax_repair.repair_structured_output(
            raw,
            format_name=structured_format,
            model_repair=_syntax_repair_callback(binding=binding,root=root,call_id=call_id),
            model_attempts=2,
        )
    except syntax_repair.SyntaxRepairExhausted as exc:
        _log_syntax_attempts(root,exc.attempts)
        candidate=_reserialize_structured(
            binding=binding,root=root,call_id=call_id,raw=raw,
            format_name=structured_format,error=exc,
        )
        return candidate,[]
    _log_syntax_result(root,result)
    return result.text,list(result.deterministic_repairs)


def _model_call(work:Path,*,call_id:str,role:str,messages:list[dict[str,str]],output:Path,validator,profile:str|None,structured_format:str|None=None)->str:
    binding=_profile(work,profile,role); root,prompt_path,messages_path=_bundle_paths(work,call_id); attempts=int(load_settings().get("structural_attempts",10))
    if binding.is_self:
        error=None
        if output.is_file():
            try:
                candidate,repairs=_prepare_candidate(raw=_read(output),structured_format=structured_format,binding=binding,root=root,call_id=call_id)
                msg=validator(candidate)
                _atomic_write(output,candidate)
                if repairs: _atomic_write(root/"deterministic-repairs.txt","\n".join(repairs)+"\n")
                _atomic_write(root/"validated.txt",msg+"\n"); return msg
            except Handoff:
                raise
            except (ValueError,OSError,KeyError) as exc:
                error=validated_model_task.retry_instruction(exc); _atomic_write(root/"attempt-self.validation.txt",error+"\n")
                _status(f"  {call_id}: validation failed; correction handoff required")
        _atomic_write(messages_path,json.dumps(messages,indent=2,ensure_ascii=False)+"\n")
        _atomic_write(prompt_path,_render_bundle(call_id,messages,output,error))
        raise Handoff(call_id,prompt_path,output)

    last_error=""; previous=None; stagnation=validated_model_task.RetryStagnationGuard()
    for attempt in range(1,attempts+1):
        _status(f"  {call_id}: answering" if attempt==1 else f"  {call_id}: retry {attempt-1}/{attempts-1}")
        call_messages=list(messages)
        if previous is not None:
            call_messages.extend([{"role":"assistant","content":previous},{"role":"user","content":last_error}])
        _atomic_write(messages_path,json.dumps(call_messages,indent=2,ensure_ascii=False)+"\n")
        _atomic_write(prompt_path,_render_bundle(call_id,call_messages,output,last_error or None))
        try:
            completion=model_client.complete_messages(binding,call_messages)
        except model_client.TruncatedCompletion as exc:
            previous=exc.content; last_error=validated_model_task.retry_instruction(exc); _atomic_write(root/f"attempt-{attempt}.validation.txt",last_error+"\n"); continue
        except RuntimeError as exc: raise StepFailure(str(exc)) from exc
        raw=completion.content if isinstance(completion,model_client.Completion) else completion
        _atomic_write(root/f"attempt-{attempt}.raw",raw.rstrip()+"\n")
        candidate=None
        try:
            candidate,repairs=_prepare_candidate(raw=raw,structured_format=structured_format,binding=binding,root=root,call_id=call_id)
            msg=validator(candidate)
        except Handoff:
            raise
        except (ValueError,OSError,KeyError) as exc:
            previous=candidate if candidate is not None else validated_model_task.safe_representation_repair(raw)[0]
            base_error=validated_model_task.retry_instruction(exc)
            repeat_count=stagnation.observe(previous,base_error)
            last_error=base_error
            if repeat_count:
                last_error += validated_model_task.stagnation_instruction(repeat_count)
            _atomic_write(root/f"attempt-{attempt}.validation.txt",last_error+"\n")
            if repeat_count >= 2:
                raise StepFailure(
                    f"model operation {call_id} repeated the same invalid artifact three times; "
                    "stopped early instead of exhausting the retry budget: "+base_error
                )
            continue
        _atomic_write(root/f"attempt-{attempt}.output",candidate)
        if repairs: _atomic_write(root/f"attempt-{attempt}.deterministic-repairs.txt","\n".join(repairs)+"\n")
        _atomic_write(output,candidate); _atomic_write(root/"validated.txt",msg+"\n"); return msg
    raise StepFailure(f"model operation {call_id} failed validation after {attempts} attempts: {last_error}")


def _safe_slug(text:str)->str:
    out="".join(ch.lower() if ch.isalnum() else "-" for ch in text).strip("-")
    while "--" in out: out=out.replace("--","-")
    return out or "case"


def _timestamped_work_dir(root:Path,label:str)->Path:
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ"); base=root/f"{_safe_slug(label)}-{stamp}"; candidate=base; suffix=2
    while candidate.exists(): candidate=Path(f"{base}-{suffix}"); suffix+=1
    return candidate


def run_setup(args:argparse.Namespace)->int:
    registry=model_registry.load_registry(); model_profile=model_registry.resolve_profile(args.model_profile or configured_profile(),None,registry)
    for role in registry["roles"]: model_registry.resolve(role,model_profile,None,registry)
    scheduler=args.scheduler or load_settings().get("scheduler","domain")
    if scheduler not in scheduler_registry.names():
        raise StepFailure(f"unknown scheduler {scheduler!r}; choose one of: {', '.join(scheduler_registry.names())}")
    label=args.mode
    if args.mode=="ngs-report" and args.case_file: label += "-"+args.case_file.stem
    elif args.mode=="nel-demo" and args.example is not None: label += f"-{args.example}"
    elif args.case_id: label += f"-{args.case_id}"
    if args.work_dir: work_arg=args.work_dir
    else:
        root=HERE/"runs"; root.mkdir(parents=True,exist_ok=True); work_arg=_timestamped_work_dir(root,label)
    work,demo_case,demo_expected=setup_workflow(workflow=WORKFLOW_ID,mode=args.mode,work_dir=work_arg,project=False,example=args.example,case_id=args.case_id)
    write_workflow_state(work,WORKFLOW_ID,args.mode,model_profile=model_profile)
    case_path=layout.input(work,"case.md",existing=False)
    if args.case_file:
        supplied=args.case_file.expanduser().resolve()
        if not supplied.is_file(): raise StepFailure(f"--case-file not found: {supplied}")
        shutil.copyfile(supplied,case_path)
    elif args.mode=="nel-demo" and demo_case: shutil.copyfile(demo_case,case_path)
    if not case_path.is_file() or not _read(case_path).strip(): raise StepFailure(f"authoritative case.md is missing or empty: {case_path}")
    if demo_expected: shutil.copyfile(demo_expected,layout.setup(work,"demo-expected.md",existing=False))
    _save_run_state(work,{"schema_version":1,"workflow_id":WORKFLOW_ID,"mode":args.mode,"validation_case":args.case_id,"model_profile":model_profile,"scheduler":scheduler,"created_at":datetime.now(timezone.utc).isoformat()})
    with _cli_logging(work): print(work); print(f"MODEL_PROFILE={model_profile}"); print(f"SCHEDULER={scheduler}")
    return EXIT_OK


def _existing_or_new(existing:Path,new:Path)->Path:
    return existing if existing.exists() else new


def _case_json(work:Path)->Path:
    return _existing_or_new(layout.input(work,"case.json"),layout.input(work,"case.json",existing=False))

def _icc_final(work:Path)->Path:
    return _existing_or_new(layout.diagnosis(work,"icc","ICC_FINAL.yaml"),layout.diagnosis(work,"icc","ICC_FINAL.yaml",existing=False))

def _icc_frozen_marker(work:Path)->Path:
    return _existing_or_new(layout.diagnosis(work,"icc","ICC_FROZEN.marker"),layout.diagnosis(work,"icc","ICC_FROZEN.marker",existing=False))

def _who5_final(work:Path)->Path:
    return _existing_or_new(layout.diagnosis(work,"who5","WHO5_FINAL.yaml"),layout.diagnosis(work,"who5","WHO5_FINAL.yaml",existing=False))

def _who5_routing(work:Path)->Path:
    return _existing_or_new(layout.diagnosis(work,"who5","ROUTING.json"),layout.diagnosis(work,"who5","ROUTING.json",existing=False))

def _domain_final(work:Path,domain:str)->Path:
    return _existing_or_new(layout.domain(work,domain,"FINAL_STATE.yaml"),layout.domain(work,domain,"FINAL_STATE.yaml",existing=False))


def module_structure_case(work:Path,stage:dict,profile:str|None)->None:
    del stage
    output=_case_json(work)
    if output.is_file(): runtime.validate_case_text(_read(output)); return
    messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":_read(PROMPTS/"structure_case.md")+"\n\n# Authoritative case.md\n"+_read(layout.input(work,"case.md"))+"\n\n# Allowed bootstrap CMCs\n"+_read(layout.input(work,"case-major-categories.json"))+"\n\n# NGS assay scope\n"+_read(layout.input(work,"ngs-panel-scope.md"))}]
    _model_call(work,call_id="structure-case",role="structure",messages=messages,output=output,validator=runtime.validate_case_text,profile=profile,structured_format="json")


def _load_corpus()->tuple[list[dict],list[dict],str,dict]:
    corpus_doc,_index,digest=corpus.load_corpus(corpus.DEFAULT_CORPUS,corpus.DEFAULT_INDEX); all_cards=corpus.flatten(corpus_doc)
    try: eligible=corpus.blacklist_cards(all_cards,corpus.DEFAULT_BLACKLIST)
    except ValueError as exc:
        if "blacklist names unknown publication_key" not in str(exc): raise
        raw=json.loads(Path(corpus.DEFAULT_BLACKLIST).read_text(encoding="utf-8")); present={c.get("publication_key") for c in all_cards}; filtered=dict(raw); filtered["papers"]={k:v for k,v in (raw.get("papers") or {}).items() if k in present}
        with tempfile.NamedTemporaryFile("w",suffix=".json",encoding="utf-8",delete=False) as handle: json.dump(filtered,handle); temporary=Path(handle.name)
        try: eligible=corpus.blacklist_cards(all_cards,temporary)
        finally: temporary.unlink(missing_ok=True)
    manifest=card_identity.build_manifest(all_cards,corpus_sha256=digest); return all_cards,eligible,digest,manifest


def _manifest_path(work:Path)->Path:
    return _existing_or_new(layout.evidence(work,"card-identity-manifest.json"),layout.evidence(work,"card-identity-manifest.json",existing=False))
def _configure_manifest(work:Path)->dict:
    path=_manifest_path(work)
    if not path.is_file(): raise StepFailure("corpus identity has not been initialised")
    return json.loads(_read(path))


def module_initialise_corpus(work:Path,stage:dict,profile:str|None)->None:
    del stage,profile; path=_manifest_path(work)
    if path.is_file(): return
    all_cards,_eligible,_digest,manifest=_load_corpus(); _atomic_write(path,json.dumps(manifest,indent=2,ensure_ascii=False)+"\n"); _status(f"  corpus identity: {len(all_cards)} cards, sha256 tags initialised")


def _render_cards(cards:list[dict],manifest:dict)->str:
    tag_by_id=card_identity.tag_by_id(manifest)
    if not cards: return "No eligible evidence cards were retrieved."
    blocks=[]
    for card in cards:
        lines=[f"### [card:{tag_by_id[card['card_id']]}] {card.get('card_id')}",f"category: {card.get('category')}",f"genes: {', '.join(card.get('genes') or []) or 'none'}",f"diseases: {', '.join(card.get('diseases') or []) or 'none'}"]
        if card.get("matched_diagnosis_ids") is not None: lines.append(f"matched_diagnosis_ids: {', '.join(card.get('matched_diagnosis_ids') or []) or 'none'}")
        if card.get("matched_case_major_categories") is not None: lines.append(f"matched_cmcs: {', '.join(card.get('matched_case_major_categories') or []) or 'none'}")
        lines.extend([f"evidence_tier: {card.get('evidence_tier') or 'unspecified'}",f"interpretation: {card.get('interpretation') or ''}",f"source: {card.get('paper_nickname') or ''} ({card.get('publication_year') or ''})"])
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _draw_diagnosis_cards(eligible:list[dict],genes:list[str],cmcs:list[str])->list[dict]:
    wanted=set(genes); hits=[]
    for source in eligible:
        if source.get("category")!="diagnosis": continue
        matched_genes=core_retrieval.match_genes(source,wanted); matched_cmcs=core_retrieval._matches_case_major_category(source,cmcs)
        if not matched_genes and not matched_cmcs: continue
        row=dict(source); row["matched_genes"]=matched_genes; row["matched_case_major_categories"]=matched_cmcs; hits.append(row)
    return sorted(hits,key=lambda r:r.get("card_id") or "")


def _render_evidence_bundle(work:Path,name:str,cards:list[dict],*,cmcs:list[str],diagnoses:list[str],digest:str,manifest:dict)->tuple[Path,Path,list[dict]]:
    bundle={"workflow_profile":WORKFLOW_ID,"terraced_domain":name,"genes":runtime.case_genes(runtime.read_json(_case_json(work))),"provisional_cmcs":cmcs,"accepted_schema_diseases":diagnoses,"diagnostic_context":[],"retrieved":cards,"runtime_card_tags":card_identity.runtime_tag_map(manifest),"provenance":{"corpus_version":None,"corpus_sha256":digest,"retrieved_at":datetime.now(timezone.utc).isoformat()}}
    bundle_path=layout.evidence(work,f"{name}-bundle.json",existing=False); evidence_path=layout.evidence(work,f"evidence-{name}.md",existing=False); tag_path=layout.evidence(work,f"card-tags-{name}.json",existing=False)
    _atomic_write(bundle_path,json.dumps(bundle,indent=2,ensure_ascii=False)+"\n")
    result=rendering.render_to_files(bundle_path,output=evidence_path,card_tag_output=tag_path,retrieved_only=True); ids={r["card_id"] for r in result.get("rendered_cards") or []}
    return evidence_path,tag_path,[c for c in cards if c.get("card_id") in ids]


def _permitted_tags(cards:list[dict],manifest:dict)->set[str]:
    by_id=card_identity.tag_by_id(manifest); return {by_id[c["card_id"]] for c in cards}


def module_icc_diagnosis(work:Path,stage:dict,profile:str|None)->None:
    del stage; output=_icc_final(work)
    if output.is_file(): return
    case=runtime.read_json(_case_json(work)); _all,eligible,digest,manifest=_load_corpus(); bootstrap=list(case["bootstrap_cmcs"]); cards=_draw_diagnosis_cards(eligible,runtime.case_genes(case),bootstrap)
    evidence_path,tag_path,visible=_render_evidence_bundle(work,"icc",cards,cmcs=bootstrap,diagnoses=[],digest=digest,manifest=manifest); permitted=_permitted_tags(visible,manifest)
    context="# Structured immutable case\n```json\n"+json.dumps(case,indent=2,ensure_ascii=False)+"\n```\n\n# NGS assay scope\n"+_read(layout.input(work,"ngs-panel-scope.md"))+"\n\n# Independent diagnostic evidence\n"+_render_cards(visible,manifest)
    messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":_read(PROMPTS/"icc_diagnosis.md")+"\n\n"+context}]
    _model_call(work,call_id="icc-independent",role="diagnosis",messages=messages,output=output,validator=lambda t:runtime.validate_icc_text(t,permitted),profile=profile,structured_format="yaml")
    _atomic_write(_icc_frozen_marker(work),"ICC result is frozen and excluded from WHO5/downstream reasoning until final evidence/prose assembly.\n")


def module_who5_stabilisation(work:Path,stage:dict,profile:str|None)->None:
    del stage; final_path=_who5_final(work); routing_path=_who5_routing(work)
    if final_path.is_file() and routing_path.is_file(): return
    case=runtime.read_json(_case_json(work)); _all,eligible,digest,manifest=_load_corpus(); genes=runtime.case_genes(case)
    history=[]
    for cmc in case["bootstrap_cmcs"]:
        if cmc not in history: history.append(cmc)
    previous=None; phase="main"; max_passes=int(load_settings().get("max_who5_passes",7)); cmc_transitions=0; audit=[]; seen_cards={}
    final_doc=None
    for pass_index in range(1,max_passes+1):
        cards=_draw_diagnosis_cards(eligible,genes,history)
        for c in cards: seen_cards.setdefault(c["card_id"],c)
        permitted=_permitted_tags(cards,manifest)
        instruction={
            "main":"Initial WHO5 pass. Build the complete diagnosis state from the case and evidence without assuming the provisional diagnosis is correct.",
            "reconsider":"Targeted reconsideration pass. Re-evaluate the complete prior WHO5 state using the cumulative evidence from every CMC encountered. Preserve it exactly when still correct; otherwise return the complete corrected state.",
            "review":"Adversarial confirmation pass. Actively look for supplied WHO5 criteria/evidence that would overturn, narrow, broaden, or add a concurrent diagnosis. If no material change is warranted, copy the complete prior state exactly.",
        }[phase]
        context="# Structured immutable case\n```json\n"+json.dumps(case,indent=2,ensure_ascii=False)+"\n```\n\n# Allowed WHO5 schema diseases\n"+_read(layout.input(work,"allowed-schema-diseases.json"))+"\n\n# NGS assay scope\n"+_read(layout.input(work,"ngs-panel-scope.md"))+"\n\n# Cumulative diagnosis evidence\n"+_render_cards(cards,manifest)
        if previous is not None: context += "\n\n# Prior validated WHO5 state\n```yaml\n"+yaml.safe_dump(previous,sort_keys=False,allow_unicode=True,width=110)+"```\n"
        context += "\n\n# Current pass\n"+instruction
        call_dir=layout.diagnosis_pass_dir(work,f"pass_{pass_index:02d}_{phase}",existing=False); output=call_dir/"OUTPUT.yaml"
        _atomic_write(call_dir/"INPUT_cards.json",json.dumps(cards,indent=2,ensure_ascii=False)+"\n"); _atomic_write(call_dir/"INPUT_context.md",context+"\n")
        _status(f"  WHO5 pass {pass_index}: {phase}; {len(cards)} cards; cumulative CMC evidence {' | '.join(history)}")
        messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":_read(PROMPTS/"who5_diagnosis.md")+"\n\n"+context}]
        _model_call(work,call_id=f"who5-{pass_index:02d}-{phase}",role="diagnosis",messages=messages,output=output,validator=lambda t,p=permitted:runtime.validate_who5_text(t,p),profile=profile,structured_format="yaml")
        state=runtime.parse_yaml_mapping(_read(output),"WHO5 diagnosis"); cmcs=runtime.derive_cmcs(state); sig=runtime.who5_signature(state)
        prev_cmcs=runtime.derive_cmcs(previous) if previous is not None else None; prev_sig=runtime.who5_signature(previous) if previous is not None else None
        if prev_cmcs is not None and cmcs!=prev_cmcs: cmc_transitions += 1
        new_cmcs=[]
        for cmc in cmcs:
            if cmc not in history: history.append(cmc); new_cmcs.append(cmc)
        audit.append({"pass":pass_index,"phase":phase,"who5_signature":sig,"derived_cmcs":cmcs,"new_cmc_evidence_added":new_cmcs,"cumulative_cmc_history":list(history),"card_count":len(cards)})
        if cmc_transitions>4: raise StepFailure("WHO5/CMC routing oscillated through more than four CMC transitions; refusing to select the last state")
        if previous is None:
            previous=state; phase="reconsider"; continue
        unchanged=(sig==prev_sig)
        previous=state
        if phase=="review" and unchanged:
            final_doc=state; break
        if phase=="review" and not unchanged:
            phase="reconsider"; continue
        if phase=="reconsider" and unchanged:
            phase="review"; continue
        phase="reconsider"
    if final_doc is None: raise StepFailure(f"WHO5 diagnosis did not stabilise within {max_passes} passes")
    final_cmcs=runtime.derive_cmcs(final_doc); _atomic_write(final_path,yaml.safe_dump(final_doc,sort_keys=False,allow_unicode=True,width=110))
    _atomic_write(routing_path,json.dumps({"schema_version":1,"final_cmcs":final_cmcs,"diagnostic_cmc_history":history,"passes":audit},indent=2,ensure_ascii=False)+"\n")
    final_cards=[seen_cards[k] for k in sorted(seen_cards)]; _render_evidence_bundle(work,"diagnosis",final_cards,cmcs=history,diagnoses=[r["schema_disease"] for r in runtime.active_who5_diagnoses(final_doc)],digest=digest,manifest=manifest)


def _disease_matches(card:dict,disease:str,category:str)->bool:
    allowed={disease,*runtime.vocab.retrieval_related_diseases(disease,category)}
    return bool(set(card.get("diseases") or []) & allowed)


def _retrieve_downstream(work:Path,category:str)->tuple[list[dict],str,dict]:
    case=runtime.read_json(_case_json(work)); diagnoses=runtime.active_who5_diagnoses(runtime.parse_yaml_mapping(_read(_who5_final(work)),"WHO5 diagnosis")); genes=set(runtime.case_genes(case)); _all,cards,digest,manifest=_load_corpus(); hits=[]
    for source in cards:
        if source.get("category")!=category: continue
        matched_genes=core_retrieval.match_genes(source,genes)
        if category=="germline":
            if not matched_genes: continue
            matched_dx=[]
        else:
            matched_dx=[d["diagnosis_id"] for d in diagnoses if _disease_matches(source,d["schema_disease"],category)]
            if not matched_dx: continue
            if category=="treatment" and source.get("genes") and not matched_genes: continue
        row=dict(source); row["matched_genes"]=matched_genes; row["matched_diagnosis_ids"]=matched_dx; hits.append(row)
    return sorted(hits,key=lambda r:r.get("card_id") or ""),digest,manifest


def module_clinical_tasks(work:Path,stage:dict,profile:str|None)->None:
    del stage
    run_state=_load_run_state(work)
    scheduler_name=run_state.get("scheduler") or load_settings().get("scheduler","domain")
    try:
        scheduler_plan=scheduler_registry.load(scheduler_name)
    except ValueError as exc:
        raise StepFailure(str(exc)) from exc
    case=runtime.read_json(_case_json(work))
    who5=runtime.parse_yaml_mapping(_read(_who5_final(work)),"WHO5 diagnosis")
    diagnoses=runtime.active_who5_diagnoses(who5)
    routing=json.loads(_read(_who5_routing(work)))
    evidence_cache={}

    def ensure_evidence(domain:str)->scheduler_primitives.EvidenceView:
        if domain in evidence_cache:
            return evidence_cache[domain]
        cards,digest,manifest=_retrieve_downstream(work,domain)
        evidence_path,tag_path,visible=_render_evidence_bundle(
            work,domain,cards,cmcs=routing["final_cmcs"],
            diagnoses=[d["schema_disease"] for d in diagnoses],digest=digest,manifest=manifest
        )
        view=scheduler_primitives.EvidenceView(
            domain=domain,cards=visible,manifest=manifest,
            permitted_tags=_permitted_tags(visible,manifest),text=_render_cards(visible,manifest)
        )
        evidence_cache[domain]=view
        return view

    def call_yaml(*,call_id:str,prompt:str,output:Path,validator)->None:
        messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":prompt}]
        _model_call(work,call_id=call_id,role="answer",messages=messages,output=output,validator=validator,profile=profile,structured_format="yaml")

    ctx=scheduler_primitives.SchedulerContext(
        work=work,case=case,diagnoses=diagnoses,final_cmcs=routing["final_cmcs"],profile=profile,
        call_yaml=call_yaml,ensure_evidence=ensure_evidence,read_text=_read,write_text=_atomic_write,status=_status,
    )
    _status(f"  scheduler: {scheduler_name} — {scheduler_plan.description}")
    scheduler_engine.execute(scheduler_plan,ctx)
    for domain in scheduler_primitives.DOMAINS:
        output=_domain_final(work,domain)
        if not output.is_file():
            raise StepFailure(f"scheduler {scheduler_name!r} did not produce {output}")
        view=ensure_evidence(domain)
        runtime.validate_domain_text(_read(output),domain=domain,spec=ctx.specs[domain],permitted_tags=view.permitted_tags)


def _load_bundle_cards(work:Path,name:str)->list[dict]:
    path=layout.evidence(work,f"{name}-bundle.json")
    return (json.loads(_read(path)).get("retrieved") or []) if path.is_file() else []


def _visible_ids(work:Path,name:str)->set[str]:
    path=layout.evidence(work,f"card-tags-{name}.json")
    if not path.is_file(): return set()
    return {r["card_id"] for r in json.loads(_read(path)).get("tags") or []}


def _permitted_by_fact(work:Path,name:str,facts:list[dict],manifest:dict)->dict[str,set[str]]:
    visible=_visible_ids(work,name); cards=[c for c in _load_bundle_cards(work,name) if c.get("card_id") in visible]; tag_by_id=card_identity.tag_by_id(manifest); result={}
    for fact in facts:
        dx_ids=set((fact.get("subject") or {}).get("diagnosis_ids") or []); allowed=set()
        for card in cards:
            card_scope=card.get("matched_diagnosis_ids")
            if dx_ids and card_scope is not None and not (dx_ids & set(card_scope or [])): continue
            allowed.add(tag_by_id[card["card_id"]])
        result[fact["fact_id"]]=allowed
    return result


def _align_fact_group(work:Path,name:str,facts:list[dict],manifest:dict,profile:str|None)->list[dict]:
    if not facts: return []
    permitted=_permitted_by_fact(work,name,facts,manifest); cards=[c for c in _load_bundle_cards(work,name) if c.get("card_id") in _visible_ids(work,name)]
    output=layout.synthesis(work,f"alignment-{name}.yaml",existing=False)
    input_facts=[{k:f[k] for k in ("fact_id","domain","subject","decision","fact","reason","candidate_card_tags")} for f in facts]
    prompt=_read(PROMPTS/"evidence_alignment.md")+"\n\n# Surfaced facts\n```yaml\n"+yaml.safe_dump({"facts":input_facts},sort_keys=False,allow_unicode=True,width=110)+"```\n\n# Evidence cards\n"+_render_cards(cards,manifest)
    messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":prompt}]
    _model_call(work,call_id=f"align-{name}",role="evidence_alignment",messages=messages,output=output,validator=lambda t:runtime.validate_evidence_alignment_text(t,facts,permitted),profile=profile,structured_format="yaml")
    return runtime.apply_alignment(facts,runtime.parse_yaml_mapping(_read(output),"evidence alignment"))


def module_evidence_alignment(work:Path,stage:dict,profile:str|None)->None:
    del stage; manifest=_configure_manifest(work); who5=runtime.parse_yaml_mapping(_read(_who5_final(work)),"WHO5 diagnosis"); icc=runtime.parse_yaml_mapping(_read(_icc_final(work)),"ICC diagnosis")
    raw_groups={"diagnosis":runtime.facts_from_who5(who5),"icc":runtime.facts_from_icc(icc)}
    for domain in ("prognosis","treatment","biomarker","germline"):
        raw_groups[domain]=runtime.facts_from_domain(domain,runtime.parse_yaml_mapping(_read(_domain_final(work,domain)),f"{domain} task"))
    raw=[f for name in ("diagnosis","icc","prognosis","treatment","biomarker","germline") for f in raw_groups[name]]; _atomic_write(layout.synthesis(work,"fact-ledger-raw.yaml",existing=False),yaml.safe_dump({"facts":raw},sort_keys=False,allow_unicode=True,width=110))
    cited=[]
    for name in ("diagnosis","icc","prognosis","treatment","biomarker","germline"):
        cited.extend(_align_fact_group(work,name,raw_groups[name],manifest,profile))
    _atomic_write(layout.synthesis(work,"fact-ledger-cited.yaml",existing=False),yaml.safe_dump({"facts":cited},sort_keys=False,allow_unicode=True,width=110))


def module_prose_synthesis(work:Path,stage:dict,profile:str|None)->None:
    del stage; ledger=runtime.parse_yaml_mapping(_read(layout.synthesis(work,"fact-ledger-cited.yaml")),"fact ledger"); facts=ledger.get("facts") or []
    if not facts: raise StepFailure("fact ledger contains no surfaced facts")
    summary_feedback=""; max_cycles=2
    for cycle in range(1,max_cycles+1):
        draft=layout.synthesis(work,"report-draft.md",existing=False); summary_input=[{"fact_id":f["fact_id"],"domain":f["domain"],"fact":f["fact"]} for f in facts]
        suffix=""
        if summary_feedback: suffix="\n\n# Required correction from prior semantic alignment\nThe prior draft omitted these locked facts. Rewrite the complete report so all are represented:\n"+summary_feedback
        messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":_read(PROMPTS/"final_summary.md")+suffix+"\n\n# Locked surfaced facts\n```yaml\n"+yaml.safe_dump({"facts":summary_input},sort_keys=False,allow_unicode=True,width=110)+"```\n"}]
        _model_call(work,call_id=f"summary-{cycle}",role="summarisation",messages=messages,output=draft,validator=runtime.validate_summary_text,profile=profile)
        sentences=runtime.sentence_manifest(_read(draft)); alignment=layout.synthesis(work,"sentence-fact-alignment.yaml",existing=False); align_input={"sentences":sentences,"facts":summary_input}
        messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":_read(PROMPTS/"sentence_fact_alignment.md")+"\n\n# Sentence and fact manifest\n```yaml\n"+yaml.safe_dump(align_input,sort_keys=False,allow_unicode=True,width=110)+"```\n"}]
        _model_call(work,call_id=f"sentence-facts-{cycle}",role="sentence_alignment",messages=messages,output=alignment,validator=lambda t:runtime.validate_sentence_alignment_text(t,sentences,facts),profile=profile,structured_format="yaml")
        align_doc=runtime.parse_yaml_mapping(_read(alignment),"sentence-to-fact alignment"); uncovered=runtime.uncovered_fact_ids(align_doc,facts)
        if not uncovered:
            _atomic_write(layout.synthesis(work,"report-cited.md",existing=False),runtime.render_cited_report(_read(draft),align_doc,facts)); return
        summary_feedback=yaml.safe_dump({"omitted_facts":[next(x for x in summary_input if x["fact_id"]==fid) for fid in uncovered]},sort_keys=False,allow_unicode=True,width=110)
        draft.rename(layout.synthesis(work,f"report-draft-unmatched-{cycle}.md",existing=False)); alignment.rename(layout.synthesis(work,f"sentence-fact-alignment-unmatched-{cycle}.yaml",existing=False))
    raise StepFailure("final prose remained semantically incomplete after two synthesis cycles")


def _combined_evidence(work:Path,names:list[str])->tuple[Path,Path]:
    manifest=_configure_manifest(work); seen={}; digest=None
    for name in names:
        path=layout.evidence(work,f"{name}-bundle.json")
        if not path.is_file(): continue
        bundle=json.loads(_read(path)); digest=digest or (bundle.get("provenance") or {}).get("corpus_sha256")
        visible=_visible_ids(work,name)
        for card in bundle.get("retrieved") or []:
            if card.get("card_id") in visible: seen.setdefault(card["card_id"],card)
    bundle={"workflow_profile":WORKFLOW_ID,"terraced_domain":"all","genes":runtime.case_genes(runtime.read_json(_case_json(work))),"provisional_cmcs":json.loads(_read(_who5_routing(work)))["final_cmcs"],"accepted_schema_diseases":[],"diagnostic_context":[],"retrieved":[seen[k] for k in sorted(seen)],"runtime_card_tags":card_identity.runtime_tag_map(manifest),"provenance":{"corpus_version":None,"corpus_sha256":digest,"retrieved_at":datetime.now(timezone.utc).isoformat()}}
    bundle_path=layout.evidence(work,"all-bundle.json",existing=False); evidence_path=layout.evidence(work,"evidence-all.md",existing=False); tag_path=layout.evidence(work,"card-tags.json",existing=False); _atomic_write(bundle_path,json.dumps(bundle,indent=2,ensure_ascii=False)+"\n"); rendering.render_to_files(bundle_path,output=evidence_path,card_tag_output=tag_path,retrieved_only=True); return evidence_path,tag_path


def _package_debug(work:Path)->Path:
    output=work/"terraced-v3-debug.zip"
    with zipfile.ZipFile(output,"w",compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(work.rglob("*")):
            if not path.is_file() or path==output or path.suffix==".zip": continue
            archive.write(path,path.relative_to(work))
    return output


def module_finalise_report(work:Path,stage:dict,profile:str|None)->None:
    del stage,profile
    cited=_read(layout.synthesis(work,"report-cited.md"))
    evidence,tags=_combined_evidence(work,["diagnosis","icc","prognosis","treatment","biomarker","germline"])
    rendered=citations.render(cited,_read(evidence),_read(tags),require_citation_after_full_stop=False)
    case=runtime.read_json(_case_json(work))
    runtime.validate_case_text(json.dumps(case,ensure_ascii=False))
    rendered=case["detected_variants_summary"]+"\n\n"+rendered.lstrip()
    report=work/"report-final.md"
    _atomic_write(report,rendered)
    run_state=_load_run_state(work); mode=run_state.get("mode")
    if mode in VALIDATION_MODES:
        case_id=run_state.get("validation_case"); output=work/f"{MARKING_PREFIX[mode]}-{case_id}.zip"; package_marking_bundle(case_id,report,output,case_file=validation_cases.VALIDATION_CASE_FILES[mode])
    _package_debug(work)


MODULES={"structure_case":module_structure_case,"initialise_corpus":module_initialise_corpus,"icc_diagnosis":module_icc_diagnosis,"who5_stabilisation":module_who5_stabilisation,"clinical_tasks":module_clinical_tasks,"evidence_alignment":module_evidence_alignment,"prose_synthesis":module_prose_synthesis,"finalise_report":module_finalise_report}


def run_pipeline(work:Path,*,profile:str|None=None,only_stage:str|None=None)->int:
    _require_work(work); stages=runtime.load_pipeline()["pipeline"]
    if only_stage and only_stage not in {s["id"] for s in stages}: raise StepFailure(f"unknown stage {only_stage!r}")
    for i,stage in enumerate(stages,1):
        if only_stage and stage["id"]!=only_stage: continue
        module=MODULES.get(stage["module"])
        if module is None: raise StepFailure(f"workflow.yaml names unsupported module {stage['module']!r}")
        _status(f"Stage {i} of {len(stages)} — {stage.get('description') or stage['id']}"); module(work,stage,profile); _status(f"Stage {i} of {len(stages)} — complete")
    return EXIT_OK


def run_provider(model_profile:str|None)->int:
    registry=model_registry.load_registry(); configured=configured_profile()
    if model_profile is not None:
        model_profile=model_registry.resolve_profile(model_profile,None,registry)
        for role in registry["roles"]: model_registry.resolve(role,model_profile,None,registry)
        settings=load_settings(); settings["model_profile"]=model_profile; _atomic_write(SETTINGS_PATH,json.dumps(settings,indent=2,ensure_ascii=False)+"\n"); configured=model_profile
    effective=model_registry.resolve_profile(configured,None,registry); print(f"MODEL_PROFILE={effective}"); print(f"SCHEDULER={load_settings().get('scheduler','domain')}"); return EXIT_OK


def build_parser()->argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest="command",required=True)
    setup=sub.add_parser("setup"); setup.add_argument("--mode",required=True,choices=["ngs-report","nel-demo","nel-validate","nel-validate-function","nel-validate-brief"]); setup.add_argument("--case-file",type=Path); setup.add_argument("--example",type=int); setup.add_argument("--case-id"); setup.add_argument("--work-dir",type=Path); setup.add_argument("--model-profile"); setup.add_argument("--scheduler",choices=scheduler_registry.names())
    sub.add_parser("schedulers")
    check=sub.add_parser("scheduler-check"); check.add_argument("--scheduler",required=True,choices=scheduler_registry.names())
    plan=sub.add_parser("scheduler-plan"); plan.add_argument("--scheduler",required=True,choices=scheduler_registry.names())
    run=sub.add_parser("run"); run.add_argument("--work-dir",type=Path); run.add_argument("--profile"); run.add_argument("--stage")
    provider=sub.add_parser("provider"); provider.add_argument("model_profile",nargs="?")
    return parser


def main(argv:list[str]|None=None)->int:
    global _EXECUTION_STARTED_AT; _EXECUTION_STARTED_AT=time.time(); args=build_parser().parse_args(argv)
    try:
        if args.command=="setup":
            if args.mode=="ngs-report" and args.case_file is None: raise StepFailure("ngs-report requires --case-file case.md")
            if args.mode=="nel-demo" and args.example is None: raise StepFailure("nel-demo requires --example N")
            if args.mode in VALIDATION_MODES and not args.case_id: raise StepFailure(f"{args.mode} requires --case-id ID")
            return run_setup(args)
        if args.command=="provider": return run_provider(args.model_profile)
        if args.command=="schedulers":
            for name,description in scheduler_registry.descriptions().items(): print(f"{name}: {description}")
            return EXIT_OK
        if args.command=="scheduler-check":
            plan=scheduler_registry.check(args.scheduler); print(f"OK {plan.scheduler_id}: {plan.path}"); return EXIT_OK
        if args.command=="scheduler-plan":
            plan=scheduler_registry.load(args.scheduler); print(f"SCHEDULER={plan.scheduler_id}");
            for line in scheduler_engine.describe(plan): print(line)
            return EXIT_OK
        work=args.work_dir.expanduser().resolve() if args.work_dir else None
        if work is None:
            root=HERE/"runs"; candidates=sorted([p for p in root.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True) if root.is_dir() else []
            if not candidates: raise StepFailure("no --work-dir given and no terraced-v3 runs exist")
            work=candidates[0]; _status(f"using most recent run directory: {work}")
        with _cli_logging(work): return run_pipeline(work,profile=args.profile,only_stage=args.stage)
    except Handoff as h:
        print(f"HANDOFF={h.call_id}"); print(f"PROMPT={h.prompt}"); print(f"OUTPUT={h.output}"); return EXIT_HANDOFF
    except (StepFailure,ValueError,OSError,KeyError,json.JSONDecodeError,yaml.YAMLError) as exc:
        print(f"terraced-v3 failed: {exc}",file=sys.stderr); return EXIT_FAILURE


if __name__=="__main__": raise SystemExit(main())
