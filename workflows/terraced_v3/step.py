#!/usr/bin/env python3
"""Scripted terraced-v3 clinical-statement workflow runner."""
from __future__ import annotations

import argparse
from collections import Counter
import contextlib
import hashlib
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
from scripts.core.validated_model_task import ValidationFailure, ValidationIssue
from scripts.core import syntax_repair
from scripts.setup_workflow import setup_workflow
from scripts.workflow_registry import read_workflow_state, write_workflow_state
from validation.package_marking import package_marking_bundle
from validation import cases as validation_cases
from workflows.terraced_v3 import card_identity, contract_registry, evidence_resolution, layout, model_client, module_registry, pipeline_registry, rendering, runtime
from workflows.terraced_v3 import scheduler_engine, scheduler_registry, scheduler_primitives

WORKFLOW_ID = "terraced-v3"
RUN_STATE_SCHEMA_VERSION = 4
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


def configured_pipeline() -> str:
    value = load_settings().get("pipeline", "self")
    return value if isinstance(value, str) and value else "self"


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
    # The immutable cited-statement ledger changes checkpoint semantics.  Refuse
    # incompatible pre-refactor runs immediately instead of discovering the
    # mismatch after some modules have already resumed.
    _load_run_state(work)
    return state


def _run_state_path(work:Path)->Path: return layout.state(work,"terraced-v3-run.json",existing=False)
def _load_run_state(work:Path)->dict:
    doc=json.loads(_read(_run_state_path(work)))
    if doc.get("schema_version") != RUN_STATE_SCHEMA_VERSION:
        raise StepFailure(
            f"incompatible terraced-v3 run-state schema {doc.get('schema_version')!r}; "
            f"this statement-ledger architecture requires schema {RUN_STATE_SCHEMA_VERSION}. Start a fresh terraced-v3 run."
        )
    return doc
def _save_run_state(work:Path,state:dict)->None: _atomic_write(_run_state_path(work),json.dumps(state,indent=2,ensure_ascii=False)+"\n")
def _pipeline_id(work:Path, selector:str|None=None)->str:
    if selector:
        return selector
    try:
        state=_load_run_state(work)
        value=state.get("pipeline")
        if isinstance(value,str) and value:
            return value
    except (OSError,ValueError,KeyError,json.JSONDecodeError):
        pass
    return configured_pipeline()

def _resolved_pipeline_path(work:Path)->Path:
    return layout.setup(work,"pipeline-resolved.yaml")

def _plan_for_work(work:Path,selector:str|None=None):
    if selector:
        return pipeline_registry.load(selector)
    resolved=_resolved_pipeline_path(work)
    if resolved.is_file():
        return pipeline_registry.load_yaml(resolved)
    return pipeline_registry.load(_pipeline_id(work,None))

def _profile(work:Path,selector:str|None,role:str):
    return pipeline_registry.binding(_plan_for_work(work,selector),role)


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
        if structured_format in {"yaml", "json"}:
            candidate,tag_repairs=runtime.normalize_model_card_tag_syntax(candidate,format_name=structured_format)
            return candidate,tag_repairs
        return candidate,[]
    _log_syntax_result(root,result)
    candidate=result.text
    repairs=list(result.deterministic_repairs)
    if structured_format in {"yaml", "json"}:
        candidate,tag_repairs=runtime.normalize_model_card_tag_syntax(candidate,format_name=structured_format)
        repairs.extend(tag_repairs)
    return candidate,repairs


def _model_call(work:Path,*,call_id:str,role:str,messages:list[dict[str,str]],output:Path,validator,profile:str|None,structured_format:str|None=None)->str:
    binding=_profile(work,profile,role); syntax_binding=_profile(work,profile,"syntax_repair"); root,prompt_path,messages_path=_bundle_paths(work,call_id); attempts=int(load_settings().get("structural_attempts",10))
    last_error=""; previous=None

    # Resume always re-enters the normal model-call validation boundary.  This is
    # essential when a nested reject-only guard (for example the local fact/card
    # support checker) invalidates an already-written originating artifact: the
    # originating task must receive correction feedback rather than failing outside
    # its retry loop.
    if output.is_file():
        candidate=None
        try:
            candidate,repairs=_prepare_candidate(raw=_read(output),structured_format=structured_format,binding=syntax_binding,root=root,call_id=call_id)
            msg=validator(candidate)
            _atomic_write(output,candidate)
            if repairs: _atomic_write(root/"deterministic-repairs.txt","\n".join(repairs)+"\n")
            _atomic_write(root/"validated.txt",msg+"\n"); return msg
        except Handoff:
            raise
        except (ValueError,OSError,KeyError) as exc:
            previous=candidate if candidate is not None else _read(output)
            last_error=validated_model_task.retry_instruction(exc)
            _atomic_write(root/"attempt-resume.validation.txt",last_error+"\n")
            if binding.is_self:
                _status(f"  {call_id}: validation failed; correction handoff required")
                _atomic_write(messages_path,json.dumps(messages,indent=2,ensure_ascii=False)+"\n")
                _atomic_write(prompt_path,_render_bundle(call_id,messages,output,last_error))
                raise Handoff(call_id,prompt_path,output)

    if binding.is_self:
        _atomic_write(messages_path,json.dumps(messages,indent=2,ensure_ascii=False)+"\n")
        _atomic_write(prompt_path,_render_bundle(call_id,messages,output,None))
        raise Handoff(call_id,prompt_path,output)

    stagnation=validated_model_task.RetryStagnationGuard()
    for attempt in range(1,attempts+1):
        _status(f"  {call_id}: answering" if attempt==1 and previous is None else f"  {call_id}: retry {attempt-1 if previous is None else attempt}/{attempts-1}")
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
            candidate,repairs=_prepare_candidate(raw=raw,structured_format=structured_format,binding=syntax_binding,root=root,call_id=call_id)
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


def _selected_pipeline_plan(args:argparse.Namespace):
    pipeline_id=(getattr(args,"pipeline",None) or getattr(args,"model_profile",None) or configured_pipeline())
    try:
        plan=pipeline_registry.load(pipeline_id)
        overrides={
            "diagnosis":getattr(args,"diagnosis_scheduler",None),
            "ptbg":getattr(args,"ptbg_scheduler",None) or getattr(args,"scheduler",None),
            "summarization":getattr(args,"summarization_scheduler",None),
        }
        if any(overrides.values()):
            plan=pipeline_registry.with_scheduler_overrides(plan,overrides)
        return plan
    except ValueError as exc:
        raise StepFailure(str(exc)) from exc

def run_setup(args:argparse.Namespace)->int:
    plan=_selected_pipeline_plan(args); pipeline_id=plan.pipeline_id; schedulers=plan.schedulers
    label=args.mode
    if args.mode=="ngs-report" and args.case_file: label += "-"+args.case_file.stem
    elif args.mode=="nel-demo" and args.example is not None: label += f"-{args.example}"
    elif args.case_id: label += f"-{args.case_id}"
    if args.work_dir: work_arg=args.work_dir
    else:
        root=HERE/"runs"; root.mkdir(parents=True,exist_ok=True); work_arg=_timestamped_work_dir(root,label)
    work,demo_case,demo_expected=setup_workflow(workflow=WORKFLOW_ID,mode=args.mode,work_dir=work_arg,project=False,example=args.example,case_id=args.case_id)
    # Keep the existing workflow registry field populated for compatibility, but the run-state `pipeline` is authoritative.
    write_workflow_state(work,WORKFLOW_ID,args.mode,model_profile=pipeline_id)
    case_path=layout.input(work,"case.md",existing=False)
    if args.case_file:
        supplied=args.case_file.expanduser().resolve()
        if not supplied.is_file(): raise StepFailure(f"--case-file not found: {supplied}")
        shutil.copyfile(supplied,case_path)
    elif args.mode=="nel-demo" and demo_case: shutil.copyfile(demo_case,case_path)
    if not case_path.is_file() or not _read(case_path).strip(): raise StepFailure(f"authoritative case.md is missing or empty: {case_path}")
    if demo_expected: shutil.copyfile(demo_expected,layout.setup(work,"demo-expected.md",existing=False))
    _save_run_state(work,{
        "schema_version":RUN_STATE_SCHEMA_VERSION,"workflow_id":WORKFLOW_ID,"mode":args.mode,"validation_case":args.case_id,
        "pipeline":pipeline_id,"schedulers":schedulers,"created_at":datetime.now(timezone.utc).isoformat(),
    })
    _atomic_write(layout.setup(work,"pipeline-resolved.yaml",existing=False),yaml.safe_dump(plan.doc,sort_keys=False,allow_unicode=True,width=110))
    _atomic_write(layout.setup(work,"pipeline-compiled.md",existing=False),pipeline_registry.compiled_markdown(plan))
    with _cli_logging(work):
        print(work); print(f"PIPELINE={pipeline_id}")
        print(f"DIAGNOSIS_SCHEDULER={schedulers['diagnosis']}")
        print(f"PTBG_SCHEDULER={schedulers['ptbg']}")
        print(f"SUMMARIZATION_SCHEDULER={schedulers['summarization']}")
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
    template=_read(PROMPTS/"structure_case.md")
    contract=contract_registry.load("core.case.structured").model_text
    prompt=template.replace("{{output_contract}}",contract)+"\n\n# Authoritative case.md\n"+_read(layout.input(work,"case.md"))+"\n\n# Allowed bootstrap CMCs\n"+_read(layout.input(work,"case-major-categories.json"))+"\n\n# NGS assay scope\n"+_read(layout.input(work,"ngs-panel-scope.md"))
    messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":prompt}]
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
    all_cards,_eligible,_digest,manifest=_load_corpus()
    evidence_resolution.validate_configured_publications(all_cards)
    _atomic_write(path,json.dumps(manifest,indent=2,ensure_ascii=False)+"\n"); _status(f"  corpus identity: {len(all_cards)} cards, sha256 tags initialised")


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


def _statement_ledger_path(work:Path)->Path:
    return layout.synthesis(work,"statement-ledger.yaml",existing=False)


def _read_statement_ledger(work:Path)->dict:
    return runtime.load_statement_ledger(layout.synthesis(work,"statement-ledger.yaml"))


def _commit_statement_snapshot(work:Path,*,snapshot_key:str,candidates:list[dict],source:str)->None:
    ledger=_read_statement_ledger(work)
    runtime.reconcile_statement_snapshot(ledger,snapshot_key,candidates,source=source)
    _atomic_write(_statement_ledger_path(work),yaml.safe_dump(ledger,sort_keys=False,allow_unicode=True,width=110))


def _guard_paraphrase(work:Path,profile:str|None,*,sentence_plan:dict,sentence:str,source:str)->None:
    payload={
        "draft_sentence":sentence_plan["draft_sentence"],
        "source_statements":sentence_plan["source_statements"],
        "split_source_statement_ids":sentence_plan.get("split_source_statement_ids") or [],
        "paraphrased_sentence":sentence,
    }
    digest=hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode("utf-8")).hexdigest()[:12]
    call_id=f"paraphrase-check-{digest}"
    root,_,_=_bundle_paths(work,call_id); output=root/"output.yaml"
    template=_read(PROMPTS/"paraphrase_preservation_check.md")
    contract=contract_registry.load("core.report.paraphrase-check").model_text
    prompt=template.replace("{{output_contract}}",contract)+"\n\n# Planned meaning and paraphrased sentence\n```yaml\n"+yaml.safe_dump(payload,sort_keys=False,allow_unicode=True,width=110)+"```\n"
    messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":prompt}]
    _model_call(work,call_id=call_id,role="semantic_preservation_check",messages=messages,output=output,validator=runtime.validate_semantic_preservation_check_text,profile=profile,structured_format="yaml")
    result=runtime.parse_yaml_mapping(_read(output),"paraphrase semantic-preservation check")
    if result["preserved"] is False:
        raise ValidationFailure(
            f"semantic preservation for {source}",
            [ValidationIssue(
                "paraphrased sentence",
                result["issue"],
                "rewrite the sentence so it is self-contained, preserves the complete planned meaning, preserves every unsplit source statement, and adds no new clinical proposition",
            )],
        )


def _statement_callbacks(work:Path,profile:str|None):
    # Diagnosis and PTBG evidence support are resolved outside the originating
    # model validator so semantic disagreement cannot trigger whole-artifact retries.
    return (
        None,
        lambda **kwargs:_commit_statement_snapshot(work,**kwargs),
        lambda **kwargs:_guard_paraphrase(work,profile,**kwargs),
    )

def module_diagnosis_scheduler(work:Path,stage:dict,profile:str|None)->None:
    uses=str(stage.get("uses") or "")
    scheduler_name=uses.split(".",2)[2] if uses.startswith("scheduler.diagnosis.") else (_load_run_state(work).get("schedulers") or {}).get("diagnosis")
    if not scheduler_name: raise StepFailure("pipeline module is missing diagnosis scheduler selection")
    try: plan=scheduler_registry.load(scheduler_name,"diagnosis")
    except ValueError as exc: raise StepFailure(str(exc)) from exc
    final_path=_who5_final(work); icc_path=_icc_final(work); routing_path=_who5_routing(work)
    if final_path.is_file() and icc_path.is_file() and routing_path.is_file(): return
    case=runtime.read_json(_case_json(work)); _all,eligible,digest,manifest=_load_corpus(); genes=runtime.case_genes(case); bootstrap=list(case.get("bootstrap_cmcs") or [])
    corpus_settings=evidence_resolution.load_settings()
    evidence_resolution.validate_configured_publications(_all,settings=corpus_settings)
    bootstrap_cards=_draw_diagnosis_cards(eligible,genes,bootstrap)
    icc_bootstrap_cards=evidence_resolution.filter_diagnosis_cards(bootstrap_cards,"icc",settings=corpus_settings)
    who5_bootstrap_cards=evidence_resolution.filter_diagnosis_cards(bootstrap_cards,"who5",settings=corpus_settings)
    _evidence_path,_tags_path,visible_bootstrap=_render_evidence_bundle(work,"icc",icc_bootstrap_cards,cmcs=bootstrap,diagnoses=[],digest=digest,manifest=manifest)
    bootstrap_view=scheduler_primitives.EvidenceView(domain="diagnosis",cards=visible_bootstrap,manifest=manifest,permitted_tags=_permitted_tags(visible_bootstrap,manifest),text=_render_cards(visible_bootstrap,manifest))
    _who5_bootstrap_path,_who5_tags_path,visible_who5_bootstrap=_render_evidence_bundle(work,"who5-bootstrap",who5_bootstrap_cards,cmcs=bootstrap,diagnoses=[],digest=digest,manifest=manifest)
    who5_bootstrap_view=scheduler_primitives.EvidenceView(domain="diagnosis",cards=visible_who5_bootstrap,manifest=manifest,permitted_tags=_permitted_tags(visible_who5_bootstrap,manifest),text=_render_cards(visible_who5_bootstrap,manifest))
    last_diag_view=who5_bootstrap_view

    def ensure_diag(cmcs:list[str])->scheduler_primitives.EvidenceView:
        nonlocal last_diag_view
        cards=_draw_diagnosis_cards(eligible,genes,cmcs)
        cards=evidence_resolution.filter_diagnosis_cards(cards,"who5",settings=corpus_settings)
        view=scheduler_primitives.EvidenceView(domain="diagnosis",cards=cards,manifest=manifest,permitted_tags=_permitted_tags(cards,manifest),text=_render_cards(cards,manifest))
        last_diag_view=view; return view

    def empty_domain(_domain:str)->scheduler_primitives.EvidenceView:
        raise ValueError("downstream evidence is unavailable inside a diagnosis scheduler")

    def call_model(*,call_id:str,role:str,prompt:str,output:Path,validator,format_name:str)->None:
        messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":prompt}]
        _model_call(work,call_id=call_id,role=role,messages=messages,output=output,validator=validator,profile=profile,structured_format=None if format_name=="text" else format_name)

    allowed=runtime.read_json(layout.input(work,"allowed-schema-diseases.json"))
    values={
        "panel_scope":_read(layout.input(work,"ngs-panel-scope.md")),
        "allowed_who5_diseases":allowed,
        "bootstrap_evidence":bootstrap_view,
        "who5_bootstrap_evidence":who5_bootstrap_view,
        "max_who5_passes":int(load_settings().get("max_who5_passes",7)),
    }
    statement_guard,statement_commit,paraphrase_guard=_statement_callbacks(work,profile)
    ctx=scheduler_primitives.SchedulerContext(
        work=work,case=case,diagnoses=[],final_cmcs=[],pipeline_id=_pipeline_id(work,profile),call_model=call_model,
        ensure_evidence=empty_domain,read_text=_read,write_text=_atomic_write,status=_status,phase="diagnosis",values=values,ensure_diagnosis_evidence=ensure_diag,
        statement_guard=statement_guard,statement_commit=statement_commit,paraphrase_guard=paraphrase_guard
    )
    _status(f"  diagnosis scheduler: {scheduler_name} — {plan.description}")
    outputs=scheduler_engine.execute(plan,ctx)
    icc=scheduler_engine.output_by_semantic_type(plan,outputs,"diagnosis.icc.state")
    who5=scheduler_engine.output_by_semantic_type(plan,outputs,"diagnosis.who5.state")
    routing=scheduler_engine.output_by_semantic_type(plan,outputs,"diagnosis.routing.state")
    runtime.validate_icc_text(yaml.safe_dump(icc,sort_keys=False,allow_unicode=True,width=110),bootstrap_view.permitted_tags,runtime.case_reference_ids(case))
    runtime.validate_who5_text(yaml.safe_dump(who5,sort_keys=False,allow_unicode=True,width=110),last_diag_view.permitted_tags,runtime.case_reference_ids(case))
    derived=runtime.derive_cmcs(who5)
    if routing.get("final_cmcs")!=derived:
        raise StepFailure(f"diagnosis scheduler routing final_cmcs {routing.get('final_cmcs')!r} does not equal deterministic WHO5-derived CMCs {derived!r}")
    history=routing.get("diagnostic_cmc_history")
    if not isinstance(history,list) or any(c not in history for c in derived):
        raise StepFailure("diagnosis scheduler routing history must contain every final WHO5-derived CMC")
    _atomic_write(icc_path,yaml.safe_dump(icc,sort_keys=False,allow_unicode=True,width=110)); _atomic_write(_icc_frozen_marker(work),"ICC result is frozen and excluded from WHO5/downstream reasoning until final reporting.\n")
    _atomic_write(final_path,yaml.safe_dump(who5,sort_keys=False,allow_unicode=True,width=110)); _atomic_write(routing_path,json.dumps(routing,indent=2,ensure_ascii=False)+"\n")
    # Persist exactly the WHO5 evidence environment exposed by the diagnosis scheduler, never a broader post-hoc draw.
    _render_evidence_bundle(work,"diagnosis",last_diag_view.cards,cmcs=history,diagnoses=[d["schema_disease"] for d in runtime.active_who5_diagnoses(who5)],digest=digest,manifest=manifest)


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


def module_ptbg_scheduler(work:Path,stage:dict,profile:str|None)->None:
    uses=str(stage.get("uses") or "")
    scheduler_name=uses.split(".",2)[2] if uses.startswith("scheduler.ptbg.") else (_load_run_state(work).get("schedulers") or {}).get("ptbg")
    if not scheduler_name:
        raise StepFailure("run state is missing PTBG scheduler selection")
    try:
        scheduler_plan=scheduler_registry.load(scheduler_name,"ptbg")
    except ValueError as exc:
        raise StepFailure(str(exc)) from exc
    case=runtime.read_json(_case_json(work))
    who5=runtime.parse_yaml_mapping(_read(_who5_final(work)),"WHO5 diagnosis")
    diagnoses=runtime.active_who5_diagnoses(who5)
    routing=json.loads(_read(_who5_routing(work)))
    evidence_cache={}

    def ensure_evidence(domain:str)->scheduler_primitives.EvidenceView:
        if domain in evidence_cache: return evidence_cache[domain]
        cards,digest,manifest=_retrieve_downstream(work,domain)
        _evidence_path,_tag_path,visible=_render_evidence_bundle(
            work,domain,cards,cmcs=routing["final_cmcs"],
            diagnoses=[d["schema_disease"] for d in diagnoses],digest=digest,manifest=manifest
        )
        view=scheduler_primitives.EvidenceView(domain=domain,cards=visible,manifest=manifest,permitted_tags=_permitted_tags(visible,manifest),text=_render_cards(visible,manifest))
        evidence_cache[domain]=view; return view

    def call_model(*,call_id:str,role:str,prompt:str,output:Path,validator,format_name:str)->None:
        messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":prompt}]
        _model_call(work,call_id=call_id,role=role,messages=messages,output=output,validator=validator,profile=profile,structured_format=None if format_name=="text" else format_name)

    statement_guard,statement_commit,paraphrase_guard=_statement_callbacks(work,profile)
    ctx=scheduler_primitives.SchedulerContext(
        work=work,case=case,diagnoses=diagnoses,final_cmcs=routing["final_cmcs"],pipeline_id=_pipeline_id(work,profile),
        call_model=call_model,ensure_evidence=ensure_evidence,read_text=_read,write_text=_atomic_write,status=_status,phase="ptbg",
        statement_guard=statement_guard,statement_commit=statement_commit,paraphrase_guard=paraphrase_guard
    )
    _status(f"  PTBG scheduler: {scheduler_name} — {scheduler_plan.description}")
    outputs=scheduler_engine.execute(scheduler_plan,ctx)
    semantic={"prognosis":"ptbg.prognosis.state","treatment":"ptbg.treatment.state","biomarker":"ptbg.biomarker.state","germline":"ptbg.germline.state"}
    for domain in scheduler_primitives.DOMAINS:
        state=scheduler_engine.output_by_semantic_type(scheduler_plan,outputs,semantic[domain])
        output=_domain_final(work,domain); text=yaml.safe_dump(state,sort_keys=False,allow_unicode=True,width=110)
        view=ensure_evidence(domain); runtime.validate_domain_text(text,domain=domain,spec=ctx.specs[domain],permitted_tags=view.permitted_tags,permitted_case_refs=runtime.case_reference_ids(case))
        _atomic_write(output,text)


def _load_bundle_cards(work:Path,name:str)->list[dict]:
    path=layout.evidence(work,f"{name}-bundle.json")
    return (json.loads(_read(path)).get("retrieved") or []) if path.is_file() else []


def _visible_ids(work:Path,name:str)->set[str]:
    path=layout.evidence(work,f"card-tags-{name}.json")
    if not path.is_file(): return set()
    return {r["card_id"] for r in json.loads(_read(path)).get("tags") or []}


def module_collect_statement_ledger(work:Path,stage:dict,profile:str|None)->None:
    """Publish the active immutable statement ledger after deterministic consistency checks."""
    del stage,profile
    ledger=_read_statement_ledger(work)
    active=runtime.active_ledger_statements(ledger)
    if not active:
        raise StepFailure("statement ledger is empty; statement-producing scheduler outputs must be locally evidence-checked and reconciled before collection")

    who5=runtime.parse_yaml_mapping(_read(_who5_final(work)),"WHO5 diagnosis")
    icc=runtime.parse_yaml_mapping(_read(_icc_final(work)),"ICC diagnosis")
    expected=runtime.statements_from_who5(who5)+runtime.statements_from_icc(icc)
    for domain in scheduler_primitives.DOMAINS:
        expected.extend(runtime.statements_from_domain(domain,runtime.parse_yaml_mapping(_read(_domain_final(work,domain)),f"{domain} task")))

    expected_counts=Counter(runtime.statement_signature(row) for row in expected)
    active_counts=Counter(runtime.statement_signature(row) for row in active)
    if expected_counts != active_counts:
        missing=list((expected_counts-active_counts).elements())
        stale=list((active_counts-expected_counts).elements())
        detail=[]
        if missing: detail.append(f"{len(missing)} final reportable statement(s) are missing from the active ledger")
        if stale: detail.append(f"{len(stale)} withdrawn/replaced statement(s) remain incorrectly active")
        raise StepFailure("final scheduler states do not match the immutable statement ledger: "+"; ".join(detail))
    for row in active:
        if row.get("evidence_check") != "supported":
            raise StepFailure(f"statement {row.get('statement_id')} has invalid evidence-check status {row.get('evidence_check')!r}; every reportable statement must pass local provenance/support review")

    published={"statements":runtime.reportable_active_statements(ledger)}
    _atomic_write(layout.synthesis(work,"statement-ledger-active.yaml",existing=False),yaml.safe_dump(published,sort_keys=False,allow_unicode=True,width=110))


def _summary_interpretation_map(work:Path)->dict[str,str]:
    manifest=_configure_manifest(work); tag_by_id=card_identity.tag_by_id(manifest); seen={}
    for name in ("diagnosis","icc","prognosis","treatment","biomarker","germline"):
        for card in _load_bundle_cards(work,name):
            cid=card.get("card_id")
            if cid in tag_by_id and cid in _visible_ids(work,name):
                interpretation=card.get("interpretation")
                if isinstance(interpretation,str) and interpretation.strip():
                    seen[f"[card:{tag_by_id[cid]}]"]=interpretation.strip()
    return seen


def module_summarization_scheduler(work:Path,stage:dict,profile:str|None)->None:
    uses=str(stage.get("uses") or "")
    scheduler_name=uses.split(".",2)[2] if uses.startswith("scheduler.summarization.") else (_load_run_state(work).get("schedulers") or {}).get("summarization")
    if not scheduler_name: raise StepFailure("run state is missing summarization scheduler selection")
    try: plan=scheduler_registry.load(scheduler_name,"summarization")
    except ValueError as exc: raise StepFailure(str(exc)) from exc
    ledger=runtime.parse_yaml_mapping(_read(layout.synthesis(work,"statement-ledger-active.yaml")),"active statement ledger"); statements=ledger.get("statements") or []
    if not statements: raise StepFailure("statement ledger contains no surfaced statements")

    def unavailable(_domain:str): raise ValueError("clinical evidence retrieval is unavailable inside the summarization scheduler")
    def call_model(*,call_id:str,role:str,prompt:str,output:Path,validator,format_name:str)->None:
        messages=[{"role":"system","content":model_client.SYSTEM_PROMPT},{"role":"user","content":prompt}]
        _model_call(work,call_id=call_id,role=role,messages=messages,output=output,validator=validator,profile=profile,structured_format=None if format_name=="text" else format_name)

    who5=runtime.parse_yaml_mapping(_read(_who5_final(work)),"WHO5 diagnosis"); routing=json.loads(_read(_who5_routing(work)))
    statement_guard,statement_commit,paraphrase_guard=_statement_callbacks(work,profile)
    ctx=scheduler_primitives.SchedulerContext(
        work=work,case=runtime.read_json(_case_json(work)),diagnoses=runtime.active_who5_diagnoses(who5),final_cmcs=routing["final_cmcs"],
        pipeline_id=_pipeline_id(work,profile),call_model=call_model,ensure_evidence=unavailable,read_text=_read,write_text=_atomic_write,status=_status,
        phase="summarization",values={"cited_statements":statements},statement_guard=statement_guard,statement_commit=statement_commit,paraphrase_guard=paraphrase_guard
    )
    _status(f"  summarization scheduler: {scheduler_name} — {plan.description}")
    outputs=scheduler_engine.execute(plan,ctx); summary=scheduler_engine.output_by_semantic_type(plan,outputs,"report.summary.sentences")
    runtime.validate_canonical_summary_doc(summary,statements)
    summary_path=layout.synthesis(work,"summary-final.yaml",existing=False); _atomic_write(summary_path,yaml.safe_dump(summary,sort_keys=False,allow_unicode=True,width=110))
    _atomic_write(layout.synthesis(work,"report-cited.md",existing=False),runtime.render_canonical_summary(summary))


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
    summary=runtime.parse_yaml_mapping(_read(layout.synthesis(work,"summary-final.yaml")),"canonical summary")
    paired=runtime.sentence_card_interpretations(summary,_summary_interpretation_map(work))
    _atomic_write(layout.synthesis(work,"sentence-card-interpretations.yaml",existing=False),yaml.safe_dump(paired,sort_keys=False,allow_unicode=True,width=110))
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


MODULES={"structure_case":module_structure_case,"initialise_corpus":module_initialise_corpus,"diagnosis_scheduler":module_diagnosis_scheduler,"ptbg_scheduler":module_ptbg_scheduler,"collect_statement_ledger":module_collect_statement_ledger,"summarization_scheduler":module_summarization_scheduler,"finalise_report":module_finalise_report}

def _handler_for_uses(uses:str):
    if uses.startswith("core."):
        spec=module_registry.load_core(uses); handler=spec.handler
    elif uses.startswith("scheduler."):
        _prefix,phase,_name=uses.split(".",2); handler=f"{phase}_scheduler"
    elif uses.startswith("adapter."):
        spec=module_registry.load_adapter(uses); handler=spec.handler
    else:
        raise StepFailure(f"unsupported pipeline module reference {uses!r}")
    module=MODULES.get(handler)
    if module is None:
        raise StepFailure(f"pipeline module {uses!r} requires unregistered Python handler {handler!r}")
    return module

def run_pipeline(work:Path,*,profile:str|None=None,only_stage:str|None=None)->int:
    _require_work(work); plan=_plan_for_work(work,profile); stages=list(plan.modules)
    if only_stage and only_stage not in {s.module_id for s in stages}: raise StepFailure(f"unknown stage {only_stage!r}")
    for i,node in enumerate(stages,1):
        if only_stage and node.module_id!=only_stage: continue
        module=_handler_for_uses(node.uses); stage={"id":node.module_id,"uses":node.uses,"inputs":node.inputs}
        _status(f"Stage {i} of {len(stages)} — {node.module_id}: {node.uses}"); module(work,stage,profile); _status(f"Stage {i} of {len(stages)} — complete")
    return EXIT_OK

def _check_pipeline(name:str):
    return pipeline_registry.validate(pipeline_registry.load(name))


def run_pipeline_setting(pipeline_id:str|None)->int:
    if pipeline_id is not None:
        plan=_check_pipeline(pipeline_id); settings=load_settings(); settings["pipeline"]=plan.pipeline_id
        _atomic_write(SETTINGS_PATH,json.dumps(settings,indent=2,ensure_ascii=False)+"\n")
    plan=_check_pipeline(configured_pipeline()); print(f"PIPELINE={plan.pipeline_id}")
    for phase,name in plan.schedulers.items(): print(f"{phase.upper()}_SCHEDULER={name}")
    return EXIT_OK


def build_parser()->argparse.ArgumentParser:
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest="command",required=True)
    setup=sub.add_parser("setup")
    setup.add_argument("--mode",required=True,choices=["ngs-report","nel-demo","nel-validate","nel-validate-function","nel-validate-brief"]); setup.add_argument("--case-file",type=Path); setup.add_argument("--example",type=int); setup.add_argument("--case-id"); setup.add_argument("--work-dir",type=Path)
    setup.add_argument("--pipeline",choices=pipeline_registry.names(),help="pipeline YAML selecting provider, phase schedulers and model-role bindings")
    setup.add_argument("--diagnosis-scheduler",choices=scheduler_registry.names("diagnosis"),help="developer override of the pipeline diagnosis scheduler")
    setup.add_argument("--ptbg-scheduler",choices=scheduler_registry.names("ptbg"),help="developer override of the pipeline PTBG scheduler")
    setup.add_argument("--summarization-scheduler",choices=scheduler_registry.names("summarization"),help="developer override of the pipeline summarization scheduler")
    setup.add_argument("--model-profile",help=argparse.SUPPRESS); setup.add_argument("--scheduler",help=argparse.SUPPRESS)
    sub.add_parser("pipelines")
    sub.add_parser("contracts")
    contract=sub.add_parser("contract"); contract.add_argument("ref")
    pcheck=sub.add_parser("pipeline-check"); pcheck.add_argument("--pipeline",required=True,choices=pipeline_registry.names())
    pplan=sub.add_parser("pipeline-plan"); pplan.add_argument("--pipeline",required=True,choices=pipeline_registry.names())
    pset=sub.add_parser("pipeline"); pset.add_argument("pipeline_id",nargs="?",choices=pipeline_registry.names())
    slist=sub.add_parser("schedulers"); slist.add_argument("--phase",choices=scheduler_registry.PHASES)
    check=sub.add_parser("scheduler-check"); check.add_argument("--phase",required=True,choices=scheduler_registry.PHASES); check.add_argument("--scheduler",required=True)
    plan=sub.add_parser("scheduler-plan"); plan.add_argument("--phase",required=True,choices=scheduler_registry.PHASES); plan.add_argument("--scheduler",required=True)
    run=sub.add_parser("run"); run.add_argument("--work-dir",type=Path); run.add_argument("--stage"); run.add_argument("--profile",help=argparse.SUPPRESS)
    return parser


def main(argv:list[str]|None=None)->int:
    global _EXECUTION_STARTED_AT; _EXECUTION_STARTED_AT=time.time(); args=build_parser().parse_args(argv)
    try:
        if args.command=="setup":
            if args.mode=="ngs-report" and args.case_file is None: raise StepFailure("ngs-report requires --case-file case.md")
            if args.mode=="nel-demo" and args.example is None: raise StepFailure("nel-demo requires --example N")
            if args.mode in VALIDATION_MODES and not args.case_id: raise StepFailure(f"{args.mode} requires --case-id ID")
            return run_setup(args)
        if args.command=="contracts":
            for ref in contract_registry.core_refs(): print(ref)
            return EXIT_OK
        if args.command=="contract":
            contract=contract_registry.load(args.ref)
            for line in contract_registry.describe(contract): print(line)
            print()
            print(contract.model_text)
            return EXIT_OK
        if args.command=="pipeline": return run_pipeline_setting(args.pipeline_id)
        if args.command=="pipelines":
            for name,description in pipeline_registry.descriptions().items(): print(f"{name}: {description}")
            return EXIT_OK
        if args.command=="pipeline-check":
            plan=_check_pipeline(args.pipeline); print(f"OK {plan.pipeline_id}: {plan.path}"); return EXIT_OK
        if args.command=="pipeline-plan":
            plan=_check_pipeline(args.pipeline); print(f"PIPELINE={plan.pipeline_id}")
            for line in pipeline_registry.describe(plan): print(line)
            for phase,name in plan.schedulers.items():
                sched=scheduler_registry.load(name,phase); print(f"\n[{phase}] {name}")
                for line in scheduler_engine.describe(sched): print("  "+line)
            return EXIT_OK
        if args.command=="schedulers":
            phases=[args.phase] if args.phase else list(scheduler_registry.PHASES)
            for phase in phases:
                print(f"[{phase}]")
                for name,description in scheduler_registry.descriptions(phase).items(): print(f"{name}: {description}")
            return EXIT_OK
        if args.command=="scheduler-check":
            plan=scheduler_registry.check(args.scheduler,args.phase); print(f"OK {plan.phase}/{plan.scheduler_id}: {plan.path}"); return EXIT_OK
        if args.command=="scheduler-plan":
            plan=scheduler_registry.load(args.scheduler,args.phase); print(f"SCHEDULER={plan.phase}/{plan.scheduler_id}")
            for line in scheduler_engine.describe(plan): print(line)
            return EXIT_OK
        work=args.work_dir.expanduser().resolve() if args.work_dir else None
        if work is None:
            root=HERE/"runs"; candidates=sorted([p for p in root.iterdir() if p.is_dir()],key=lambda p:p.stat().st_mtime,reverse=True) if root.is_dir() else []
            if not candidates: raise StepFailure("no --work-dir given and no terraced-v3 runs exist")
            work=candidates[0]; _status(f"using most recent run directory: {work}")
        with _cli_logging(work): return run_pipeline(work,profile=None,only_stage=args.stage)
    except Handoff as h:
        print(f"HANDOFF={h.call_id}"); print(f"PROMPT={h.prompt}"); print(f"OUTPUT={h.output}"); return EXIT_HANDOFF
    except (StepFailure,ValueError,OSError,KeyError,json.JSONDecodeError,yaml.YAMLError) as exc:
        print(f"terraced-v3 failed: {exc}",file=sys.stderr); return EXIT_FAILURE


if __name__=="__main__": raise SystemExit(main())
