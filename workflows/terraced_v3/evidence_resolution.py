"""Small-context evidence resolution for terraced-v3 diagnosis tasks.

The model never generates immutable runtime card IDs during relevance selection or
statement/card pairing. Relevance selection uses deterministic local ``CARD nn`` IDs
that are rendered with each complete original card block. A second pass reviews only
the cards not selected in the first pass. Python maps the selected local IDs back to
runtime card tags before a separate reasonable-support review.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Callable

import yaml

from scripts.core.validated_model_task import ValidationIssue, fail
from workflows.terraced_v3 import card_identity, contract_registry, runtime
from workflows.terraced_v3.scheduler_primitives import EvidenceView

HERE = Path(__file__).resolve().parent
DEFAULT_SETTINGS = HERE / "corpus_filters.yaml"
PROMPTS = HERE / "prompts"
_LOCAL_RE = re.compile(r"^CARD \d{2}$")


@dataclass(frozen=True)
class LocalEvidence:
    view: EvidenceView
    label_to_card: dict[str, dict]
    block_by_label: dict[str, str]


def load_settings(path: Path = DEFAULT_SETTINGS) -> dict:
    try:
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise ValueError(f"cannot read terraced-v3 corpus filters {path}: {exc}") from exc
    if not isinstance(doc, dict) or doc.get("schema_version") != 1:
        raise ValueError(f"{path} must contain schema_version: 1")
    diagnosis = doc.get("diagnosis")
    if not isinstance(diagnosis, dict) or set(diagnosis) != {"icc", "who5"}:
        raise ValueError(f"{path} diagnosis must map exactly icc and who5")
    for authority in ("icc", "who5"):
        row = diagnosis[authority]
        keys = row.get("publication_keys") if isinstance(row, dict) else None
        if not isinstance(keys, list) or not keys or any(not isinstance(x, str) or not x for x in keys):
            raise ValueError(f"{path} diagnosis.{authority}.publication_keys must be a non-empty string list")
    resolution = doc.get("evidence_resolution")
    if not isinstance(resolution, dict):
        raise ValueError(f"{path} evidence_resolution must be a mapping")
    max_cards = resolution.get("max_relevant_cards")
    repair = resolution.get("unsupported_repair_attempts")
    if not isinstance(max_cards, int) or not (1 <= max_cards <= 99):
        raise ValueError(f"{path} evidence_resolution.max_relevant_cards must be 1..99")
    if not isinstance(repair, int) or repair < 0 or repair > 3:
        raise ValueError(f"{path} evidence_resolution.unsupported_repair_attempts must be 0..3")
    return doc


def filter_diagnosis_cards(cards: list[dict], authority: str, *, settings: dict | None = None) -> list[dict]:
    settings = settings or load_settings()
    if authority not in {"icc", "who5"}:
        raise ValueError(f"unknown diagnosis authority {authority!r}")
    allowed = set(settings["diagnosis"][authority]["publication_keys"])
    return [card for card in cards if card.get("publication_key") in allowed]


def validate_configured_publications(cards: list[dict], *, settings: dict | None = None) -> None:
    settings = settings or load_settings()
    present = {card.get("publication_key") for card in cards}
    missing: list[str] = []
    for authority in ("icc", "who5"):
        for key in settings["diagnosis"][authority]["publication_keys"]:
            if key not in present:
                missing.append(f"{authority}:{key}")
    if missing:
        raise ValueError("configured diagnosis publication_key(s) are absent from the corpus: " + ", ".join(missing))


def _source_label(card: dict) -> str:
    nickname = str(card.get("paper_nickname") or card.get("publication_key") or "")
    year = str(card.get("publication_year") or "")
    return f"{nickname} ({year})".strip()


def render_local_blocks(cards: list[dict]) -> tuple[str, dict[str, dict], dict[str, str]]:
    """Render contiguous blocks without immutable/legacy card IDs."""
    blocks: list[str] = []
    label_to_card: dict[str, dict] = {}
    block_by_label: dict[str, str] = {}
    for index, card in enumerate(cards, 1):
        label = f"CARD {index:02d}"
        block = "\n".join([
            f"<<<{label}>>>",
            f"category: {card.get('category') or ''}",
            f"genes: {', '.join(card.get('genes') or []) or 'none'}",
            f"diseases: {', '.join(card.get('diseases') or []) or 'none'}",
            f"evidence_tier: {card.get('evidence_tier') or 'unspecified'}",
            f"interpretation: {card.get('interpretation') or ''}",
            f"source: {_source_label(card)}",
            f"<<<END {label}>>>",
        ])
        blocks.append(block)
        label_to_card[label] = card
        block_by_label[label] = block
    return "\n\n".join(blocks), label_to_card, block_by_label


def render_relevance_blocks(cards: list[dict]) -> tuple[str, dict[str, dict], dict[str, str]]:
    """Render complete card blocks keyed by deterministic local ``CARD nn`` IDs."""
    return render_local_blocks(cards)


def parse_relevance_output(text: str, *, allowed_card_ids: set[str], max_cards: int) -> list[str]:
    try:
        doc = yaml.safe_load(text.strip())
    except yaml.YAMLError as exc:
        raise ValueError(f"relevance extraction must be valid YAML: {exc}") from exc
    if not isinstance(doc, dict) or set(doc) != {"relevant_card_ids"}:
        raise ValueError("relevance extraction must return exactly relevant_card_ids")
    rows = doc.get("relevant_card_ids")
    if not isinstance(rows, list):
        raise ValueError("relevant_card_ids must be a list; use [] when no cards are relevant")
    labels: list[str] = []
    seen: set[str] = set()
    for i, label in enumerate(rows):
        if not isinstance(label, str) or not _LOCAL_RE.fullmatch(label):
            raise ValueError(f"relevant_card_ids[{i}] must copy one supplied CARD nn ID exactly")
        if label not in allowed_card_ids:
            raise ValueError(f"relevant_card_ids[{i}] uses unknown or unavailable card ID {label!r}")
        if label in seen:
            raise ValueError(f"relevance extraction duplicated card ID {label}")
        seen.add(label)
        labels.append(label)
    if len(labels) > max_cards:
        raise ValueError(f"relevance extraction returned {len(labels)} cards; maximum per pass is {max_cards}")
    return labels


def local_evidence(full: EvidenceView, selected_cards: list[dict]) -> LocalEvidence:
    text, label_to_card, block_by_label = render_local_blocks(selected_cards)
    tag_by_id = card_identity.tag_by_id(full.manifest)
    permitted = {tag_by_id[card["card_id"]] for card in selected_cards}
    view = EvidenceView(
        domain=full.domain,
        cards=selected_cards,
        manifest=full.manifest,
        permitted_tags=permitted,
        text=text or "No potentially relevant evidence cards were selected.",
    )
    return LocalEvidence(view=view, label_to_card=label_to_card, block_by_label=block_by_label)


def _without_card_tags(value: Any) -> Any:
    if isinstance(value,list):
        return [_without_card_tags(item) for item in value]
    if not isinstance(value,dict):
        return value
    return {key:_without_card_tags(child) for key,child in value.items() if key != "card_tags"}


def _collect_card_tags(value: Any) -> set[str]:
    found:set[str]=set()
    if isinstance(value,list):
        for item in value: found.update(_collect_card_tags(item))
    elif isinstance(value,dict):
        for key,child in value.items():
            if key == "card_tags" and isinstance(child,list):
                found.update(tag for tag in child if isinstance(tag,str))
            else:
                found.update(_collect_card_tags(child))
    return found


def _retain_prior_cards(selected:list[dict], *, evidence:EvidenceView, prior_state:Any)->list[dict]:
    required=_collect_card_tags(prior_state)
    if not required: return selected
    tag_by_id=card_identity.tag_by_id(evidence.manifest)
    by_token={f"[card:{tag_by_id[card['card_id']]}]":card for card in evidence.cards}
    missing=sorted(required-set(by_token))
    if missing:
        raise ValueError(f"prior diagnosis state cites card(s) outside the current authority-filtered evidence draw: {missing}")
    seen={card['card_id'] for card in selected}; out=list(selected)
    for tag in sorted(required):
        card=by_token[tag]
        if card['card_id'] not in seen:
            out.append(card); seen.add(card['card_id'])
    return out


def localize_prior_state(value:Any, *, local:LocalEvidence)->Any:
    if value is None: return None
    tag_by_id=card_identity.tag_by_id(local.view.manifest)
    tag_to_label={f"[card:{tag_by_id[card['card_id']]}]":label for label,card in local.label_to_card.items()}
    def walk(node:Any,path:str=""):
        if isinstance(node,list): return [walk(item,f"{path}[{i}]") for i,item in enumerate(node)]
        if not isinstance(node,dict): return node
        out={}
        for key,child in node.items():
            loc=f"{path}.{key}" if path else key
            if key == "card_tags":
                if not isinstance(child,list): raise ValueError(f"{loc} must be a list")
                refs=[]
                for tag in child:
                    if tag not in tag_to_label:
                        raise ValueError(f"{loc} cites {tag!r}, which is unavailable in the reduced evidence bundle")
                    refs.append(tag_to_label[tag])
                out["card_refs"]=refs
            else:
                out[key]=walk(child,loc)
        return out
    return walk(value)


def build_relevance_prompt(*, question: str, case: dict, task_context: Any, cards_text: str, max_cards: int, pass_instruction: str) -> str:
    template = (PROMPTS / "evidence_relevance_extract.md").read_text(encoding="utf-8")
    public_context=_without_card_tags(task_context)
    context = yaml.safe_dump(public_context, sort_keys=False, allow_unicode=True, width=110).rstrip() if public_context else "none"
    return (template
        .replace("{{question}}", question)
        .replace("{{max_cards}}", str(max_cards))
        .replace("{{pass_instruction}}", pass_instruction)
        .replace("{{case}}", json.dumps(case, indent=2, ensure_ascii=False))
        .replace("{{task_context}}", context)
        .replace("{{cards}}", cards_text))


def select_relevant_cards(
    *,
    ctx,
    evidence: EvidenceView,
    authority: str | None,
    question: str,
    task_context: Any,
    call_id: str,
    root: Path,
    settings: dict | None = None,
    role: str = "diagnosis",
) -> LocalEvidence:
    settings = settings or load_settings()
    filtered = filter_diagnosis_cards(evidence.cards, authority, settings=settings) if authority in {"icc", "who5"} else list(evidence.cards)
    max_cards = int(settings["evidence_resolution"]["max_relevant_cards"])
    _cards_text, label_to_card, block_by_label = render_relevance_blocks(filtered)
    root.mkdir(parents=True, exist_ok=True)
    if not filtered:
        empty = "relevant_card_ids: []\n"
        (root / "relevance-pass-1.yaml").write_text(empty, encoding="utf-8")
        (root / "relevance-pass-2.yaml").write_text(empty, encoding="utf-8")
        ctx.status(f"  {call_id}-relevance: 0 authority-filtered cards")
        return local_evidence(evidence, [])

    all_labels = list(label_to_card)

    def run_pass(*, pass_no: int, candidate_labels: list[str]) -> list[str]:
        if not candidate_labels:
            output = root / f"relevance-pass-{pass_no}.yaml"
            output.write_text("relevant_card_ids: []\n", encoding="utf-8")
            return []
        cards_text = "\n\n".join(block_by_label[label] for label in candidate_labels)
        pass_instruction = (
            "First relevance pass over the supplied candidate cards."
            if pass_no == 1
            else "Second relevance pass over only cards not selected in pass 1. Select any additional relevant cards; selecting zero cards is valid."
        )
        prompt = build_relevance_prompt(
            question=question,
            case=ctx.case,
            task_context=task_context,
            cards_text=cards_text,
            max_cards=max_cards,
            pass_instruction=pass_instruction,
        )
        output = root / f"relevance-pass-{pass_no}.yaml"
        allowed = set(candidate_labels)
        validator = lambda text: (parse_relevance_output(text, allowed_card_ids=allowed, max_cards=max_cards) and "relevance extraction validated") or "relevance extraction validated"
        ctx.call_model(
            call_id=f"{call_id}-relevance-pass-{pass_no}",
            role=role,
            prompt=prompt,
            output=output,
            validator=validator,
            format_name="yaml",
        )
        return parse_relevance_output(ctx.read_text(output), allowed_card_ids=allowed, max_cards=max_cards)

    pass_1_labels = run_pass(pass_no=1, candidate_labels=all_labels)
    pass_1_set = set(pass_1_labels)
    remaining_labels = [label for label in all_labels if label not in pass_1_set]
    pass_2_labels = run_pass(pass_no=2, candidate_labels=remaining_labels)
    labels = pass_1_labels + pass_2_labels
    extracted = [label_to_card[label] for label in labels]
    selected = _retain_prior_cards(extracted,evidence=evidence,prior_state=task_context.get("prior_state") if isinstance(task_context,dict) else None)
    (root / "relevance-selection.yaml").write_text(
        yaml.safe_dump({
            "authority": authority or evidence.domain,
            "input_card_count": len(filtered),
            "max_relevant_cards_per_pass": max_cards,
            "pass_1_selected_card_ids": pass_1_labels,
            "pass_1_selected_count": len(pass_1_labels),
            "pass_2_input_card_count": len(remaining_labels),
            "pass_2_selected_card_ids": pass_2_labels,
            "pass_2_selected_count": len(pass_2_labels),
            "selected_card_ids": labels,
            "extracted_card_count": len(extracted),
            "final_card_count": len(selected),
            "prior_cards_retained": len(selected)-len(extracted),
        }, sort_keys=False),
        encoding="utf-8",
    )
    suffix=f" (+{len(selected)-len(extracted)} prior)" if len(selected)>len(extracted) else ""
    ctx.status(
        f"  {call_id}: evidence relevance {len(filtered)} -> {len(pass_1_labels)} pass-1 + "
        f"{len(pass_2_labels)} pass-2 = {len(extracted)} extracted cards{suffix}"
    )
    return local_evidence(evidence, selected)


def _resolve_refs(value: Any, *, label_to_tag: dict[str, str], path: str = "") -> Any:
    if isinstance(value, list):
        return [_resolve_refs(item, label_to_tag=label_to_tag, path=f"{path}[{i}]") for i, item in enumerate(value)]
    if not isinstance(value, dict):
        return value
    if "card_tags" in value:
        raise ValueError(f"{path or 'output'} must use local card_refs during pairing; do not emit card_tags")
    out: dict[str, Any] = {}
    for key, child in value.items():
        loc = f"{path}.{key}" if path else key
        if key == "card_refs":
            if not isinstance(child, list):
                raise ValueError(f"{loc} must be a list of supplied local CARD labels")
            seen: set[str] = set(); tags: list[str] = []
            for i, label in enumerate(child):
                if not isinstance(label, str) or not _LOCAL_RE.fullmatch(label) or label not in label_to_tag:
                    raise ValueError(f"{loc}[{i}] uses unknown local card label {label!r}; copy one supplied CARD nn label")
                if label in seen:
                    raise ValueError(f"{loc}[{i}] duplicates {label}")
                seen.add(label); tags.append(label_to_tag[label])
            out["card_tags"] = tags
        else:
            out[key] = _resolve_refs(child, label_to_tag=label_to_tag, path=loc)
    return out


def resolve_pairing_text(text: str, *, local: LocalEvidence) -> tuple[dict, str]:
    doc = runtime.parse_yaml_mapping(text, "diagnosis statement/card pairing")
    tag_by_id = card_identity.tag_by_id(local.view.manifest)
    label_to_tag = {label: f"[card:{tag_by_id[card['card_id']]}]" for label, card in local.label_to_card.items()}
    resolved = _resolve_refs(doc, label_to_tag=label_to_tag)
    rendered = yaml.safe_dump(resolved, sort_keys=False, allow_unicode=True, width=110)
    return resolved, rendered


def validate_pairing_text(text: str, *, local: LocalEvidence, authority: str, case_refs: set[str]) -> str:
    _doc, rendered = resolve_pairing_text(text, local=local)
    if authority == "icc":
        runtime.validate_icc_text(rendered, local.view.permitted_tags, case_refs)
    elif authority == "who5":
        runtime.validate_who5_text(rendered, local.view.permitted_tags, case_refs)
    else:
        raise ValueError(f"unknown diagnosis authority {authority!r}")
    return f"{authority} statement/card pairing validated"



def validate_statement_pairing_text(text: str, *, candidate_ids: list[str], local: LocalEvidence) -> str:
    """Validate generic statement-to-local-card pairing without exposing runtime IDs."""
    doc=runtime.parse_yaml_mapping(text,"statement/card pairing"); issues=[]
    if set(doc)!={"pairings"}:
        issues.append(ValidationIssue("Top level",f"received fields {sorted(doc)}","return exactly pairings"))
    rows=doc.get("pairings")
    if not isinstance(rows,list):
        issues.append(ValidationIssue("pairings",f"expected list, received {type(rows).__name__}","return one pairing per supplied candidate in order")); rows=[]
    if len(rows)!=len(candidate_ids):
        issues.append(ValidationIssue("pairings",f"expected {len(candidate_ids)} rows, received {len(rows)}","return every supplied candidate exactly once in order"))
    labels=set(local.label_to_card)
    for i,cid in enumerate(candidate_ids):
        if i>=len(rows) or not isinstance(rows[i],dict): continue
        row=rows[i]; loc=f"pairings[{i}]"
        if set(row)!={"candidate_id","card_refs"}:
            issues.append(ValidationIssue(loc,f"received fields {sorted(row)}","return exactly candidate_id and card_refs"))
        if row.get("candidate_id")!=cid:
            issues.append(ValidationIssue(f"{loc}.candidate_id",f"received {row.get('candidate_id')!r}",f"copy exact candidate_id {cid!r}"))
        refs=row.get("card_refs")
        if not isinstance(refs,list):
            issues.append(ValidationIssue(f"{loc}.card_refs",f"expected list, received {type(refs).__name__}","return [] or unique supplied CARD nn labels")); continue
        seen=set()
        for j,label in enumerate(refs):
            if not isinstance(label,str) or label not in labels:
                issues.append(ValidationIssue(f"{loc}.card_refs[{j}]",f"unknown local card label {label!r}","copy one supplied CARD nn label"))
            elif label in seen:
                issues.append(ValidationIssue(f"{loc}.card_refs[{j}]",f"duplicate {label}","list each card once"))
            seen.add(label)
    fail("statement/card pairing",issues)
    return "statement/card pairing validated"


def pair_statements_to_cards(*,ctx,rows:list[dict],local:LocalEvidence,call_id:str,root:Path,role:str="ptbg")->list[list[str]]:
    """Pair frozen statement+reason rows to local cards, then resolve tags deterministically."""
    ids=[f"C{i}" for i in range(1,len(rows)+1)]
    if not rows: return []
    if not local.label_to_card:
        return [[] for _ in rows]
    payload={"statements":[{
        "candidate_id":cid,
        "statement":row.get("statement"),
        "reason":row.get("reason"),
        "case_refs":list(row.get("case_refs") or []),
    } for cid,row in zip(ids,rows)]}
    template=(PROMPTS/"evidence_statement_pairing.md").read_text(encoding="utf-8")
    contract=contract_registry.load("core.statements.card-pairing").model_text
    prompt=(template.replace("{{output_contract}}",contract)
        .replace("{{statements}}",yaml.safe_dump(payload,sort_keys=False,allow_unicode=True,width=110).rstrip())
        .replace("{{cards}}",local.view.text))
    output=root/"pairing.yaml"
    ctx.call_model(
        call_id=f"{call_id}-pairing",role=role,prompt=prompt,output=output,
        validator=lambda text:validate_statement_pairing_text(text,candidate_ids=ids,local=local),format_name="yaml",
    )
    doc=runtime.parse_yaml_mapping(ctx.read_text(output),"statement/card pairing")
    tag_by_id=card_identity.tag_by_id(local.view.manifest)
    label_to_tag={label:f"[card:{tag_by_id[card['card_id']]}]" for label,card in local.label_to_card.items()}
    return [[label_to_tag[label] for label in row["card_refs"]] for row in doc["pairings"]]


def _fact_rows(doc: dict, authority: str) -> list[dict]:
    if authority == "icc":
        return list(doc.get("diagnoses") or [])
    if authority == "who5":
        return list(doc.get("diagnoses") or [])
    raise ValueError(authority)


def _audit_payload(doc: dict, *, authority: str, local: LocalEvidence, candidate_ids: set[str] | None = None) -> tuple[str, dict[str, dict]]:
    tag_by_id = card_identity.tag_by_id(local.view.manifest)
    by_tag = {f"[card:{tag_by_id[card['card_id']]}]": card for card in local.view.cards}
    rows = _fact_rows(doc, authority)
    pairs: list[str] = []; by_candidate: dict[str, dict] = {}
    for i, row in enumerate(rows, 1):
        cid = f"C{i}"
        if candidate_ids is not None and cid not in candidate_ids:
            continue
        by_candidate[cid] = row
        lines = [f"## {cid}", f"Statement: {row.get('statement') or ''}", f"Reason: {row.get('reason') or ''}", f"Patient sources: {', '.join(row.get('case_refs') or []) or 'none'}"]
        tags = list(row.get("card_tags") or [])
        if not tags:
            lines.append("Interpretation: none selected")
        else:
            for j, tag in enumerate(tags, 1):
                card = by_tag.get(tag)
                if card is None:
                    raise ValueError(f"audit cannot resolve selected card {tag}")
                lines.append(f"Selected card {j}: {tag}")
                lines.append(f"Interpretation {j}: {card.get('interpretation') or ''}")
        lines.append("Question: Does this interpretation reasonably support the statement? Treat patient observations as given.")
        pairs.append("\n".join(lines))
    return "\n\n".join(pairs), by_candidate


def validate_support_audit_text(text: str, candidate_ids: list[str]) -> str:
    doc = runtime.parse_yaml_mapping(text, "reasonable support check")
    issues: list[ValidationIssue] = []
    if set(doc) != {"assessments"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly assessments"))
    rows = doc.get("assessments")
    if not isinstance(rows, list):
        issues.append(ValidationIssue("assessments", f"expected list, received {type(rows).__name__}", "return one assessment per candidate")); rows = []
    seen: set[str] = set()
    allowed_ids = set(candidate_ids)
    for i, row in enumerate(rows):
        loc = f"assessments[{i}]"
        if not isinstance(row, dict):
            issues.append(ValidationIssue(loc, f"expected mapping, received {type(row).__name__}", "return candidate_id, assessment, reason")); continue
        if set(row) != {"candidate_id", "assessment", "reason"}:
            issues.append(ValidationIssue(loc, f"received fields {sorted(row)}", "return exactly candidate_id, assessment, reason"))
        cid = row.get("candidate_id")
        if cid not in allowed_ids:
            issues.append(ValidationIssue(f"{loc}.candidate_id", f"unknown candidate {cid!r}", "copy one supplied candidate ID"))
        elif cid in seen:
            issues.append(ValidationIssue(f"{loc}.candidate_id", f"duplicate candidate {cid}", "return each candidate once"))
        else:
            seen.add(cid)
        if row.get("assessment") not in {"supported", "unsupported"}:
            issues.append(ValidationIssue(f"{loc}.assessment", f"invalid value {row.get('assessment')!r}", "use supported or unsupported"))
        if not isinstance(row.get("reason"), str) or not row["reason"].strip():
            issues.append(ValidationIssue(f"{loc}.reason", "blank or not a string", "give one brief reason"))
    missing = [cid for cid in candidate_ids if cid not in seen]
    if missing:
        issues.append(ValidationIssue("assessments", f"missing candidates {missing}", "return one row for every supplied candidate"))
    fail("reasonable support check", issues)
    return "reasonable support check validated"


def build_support_audit_prompt(pairs: str) -> str:
    template = (PROMPTS / "evidence_support_audit.md").read_text(encoding="utf-8")
    contract = contract_registry.load("core.statements.reasonable-support-check").model_text
    return template.replace("{{output_contract}}", contract).replace("{{pairs}}", pairs)


def run_support_audit(*, ctx, doc: dict, authority: str, local: LocalEvidence, call_id: str, root: Path, candidate_ids: set[str] | None = None) -> dict[str, dict]:
    pairs, by_candidate = _audit_payload(doc, authority=authority, local=local, candidate_ids=candidate_ids)
    ids = list(by_candidate)
    if not ids:
        return {}
    output = root / ("audit.yaml" if candidate_ids is None else "audit-repair.yaml")
    prompt = build_support_audit_prompt(pairs)
    ctx.call_model(
        call_id=call_id,
        role="statement_evidence_check",
        prompt=prompt,
        output=output,
        validator=lambda text: validate_support_audit_text(text, ids),
        format_name="yaml",
    )
    result = runtime.parse_yaml_mapping(ctx.read_text(output), "reasonable support check")
    return {row["candidate_id"]: row for row in result["assessments"]}


def validate_repair_text(text: str, candidate_ids: list[str], labels: set[str]) -> str:
    doc = runtime.parse_yaml_mapping(text, "local card-pairing repair")
    issues: list[ValidationIssue] = []
    if set(doc) != {"repairs"}:
        issues.append(ValidationIssue("Top level", f"received fields {sorted(doc)}", "return exactly repairs"))
    rows = doc.get("repairs")
    if not isinstance(rows, list):
        issues.append(ValidationIssue("repairs", f"expected list, received {type(rows).__name__}", "return one repair per candidate")); rows = []
    seen: set[str] = set(); allowed_ids = set(candidate_ids)
    for i, row in enumerate(rows):
        loc = f"repairs[{i}]"
        if not isinstance(row, dict):
            issues.append(ValidationIssue(loc, f"expected mapping, received {type(row).__name__}", "return candidate_id and card_refs")); continue
        if set(row) != {"candidate_id", "card_refs"}:
            issues.append(ValidationIssue(loc, f"received fields {sorted(row)}", "return exactly candidate_id and card_refs"))
        cid = row.get("candidate_id")
        if cid not in allowed_ids:
            issues.append(ValidationIssue(f"{loc}.candidate_id", f"unknown candidate {cid!r}", "copy one supplied candidate ID"))
        elif cid in seen:
            issues.append(ValidationIssue(f"{loc}.candidate_id", f"duplicate candidate {cid}", "return each candidate once"))
        else:
            seen.add(cid)
        refs = row.get("card_refs")
        if not isinstance(refs, list):
            issues.append(ValidationIssue(f"{loc}.card_refs", "must be a list", "return [] or supplied CARD nn labels")); continue
        if any(ref not in labels for ref in refs):
            issues.append(ValidationIssue(f"{loc}.card_refs", f"contains unknown label(s) {refs!r}", "use only supplied CARD nn labels"))
        if len(refs) != len(set(refs)):
            issues.append(ValidationIssue(f"{loc}.card_refs", "contains duplicate labels", "list each local card once"))
    missing = [cid for cid in candidate_ids if cid not in seen]
    if missing:
        issues.append(ValidationIssue("repairs", f"missing candidates {missing}", "return one row for every supplied candidate"))
    fail("local card-pairing repair", issues)
    return "local card-pairing repair validated"


def _tag_for_label(local: LocalEvidence, label: str) -> str:
    tag_by_id = card_identity.tag_by_id(local.view.manifest)
    return f"[card:{tag_by_id[local.label_to_card[label]['card_id']]}]"


def _apply_repairs(doc: dict, *, authority: str, repairs: dict[str, list[str]], local: LocalEvidence) -> dict:
    out = deepcopy(doc)
    rows = _fact_rows(out, authority)
    for i, row in enumerate(rows, 1):
        cid = f"C{i}"
        if cid in repairs:
            row["card_tags"] = [_tag_for_label(local, label) for label in repairs[cid]]
    return out


def audit_and_repair(
    *,
    ctx,
    doc: dict,
    authority: str,
    local: LocalEvidence,
    call_id: str,
    root: Path,
    settings: dict | None = None,
    repair_role: str = "diagnosis",
) -> tuple[dict, dict]:
    """Audit pairings without feeding semantic rejection into whole-artifact retries.

    Unsupported rows receive bounded card-only repair.  A repair is adopted only
    when the re-audit improves it to supported.  Remaining unsupported
    rows are retained and explicitly recorded as warnings rather than causing the
    diagnosis model to regenerate the complete clinical state.
    """
    settings = settings or load_settings()
    root.mkdir(parents=True, exist_ok=True)
    initial = run_support_audit(ctx=ctx, doc=doc, authority=authority, local=local, call_id=f"{call_id}-audit", root=root)
    current = deepcopy(doc)
    final = dict(initial)
    repair_log: list[dict] = []
    unsupported = {cid for cid, row in initial.items() if row["assessment"] == "unsupported"}
    attempts = int(settings["evidence_resolution"]["unsupported_repair_attempts"])
    for attempt in range(1, attempts + 1):
        if not unsupported or not local.label_to_card:
            break
        rows = _fact_rows(current, authority)
        frozen = []
        for i, row in enumerate(rows, 1):
            cid = f"C{i}"
            if cid in unsupported:
                frozen.append({"candidate_id": cid, "statement": row.get("statement"), "reason": row.get("reason"), "case_refs": row.get("case_refs") or [], "current_card_tags": row.get("card_tags") or []})
        labels = set(local.label_to_card)
        prompt = (PROMPTS / "evidence_card_repair.md").read_text(encoding="utf-8")
        prompt = prompt.replace("{{statements}}", yaml.safe_dump(frozen, sort_keys=False, allow_unicode=True, width=110).rstrip())
        prompt = prompt.replace("{{cards}}", local.view.text)
        output = root / f"repair-{attempt}.yaml"
        ids = [row["candidate_id"] for row in frozen]
        ctx.call_model(
            call_id=f"{call_id}-repair-{attempt}", role=repair_role, prompt=prompt, output=output,
            validator=lambda text, ids=ids, labels=labels: validate_repair_text(text, ids, labels), format_name="yaml",
        )
        repair_doc = runtime.parse_yaml_mapping(ctx.read_text(output), "local card-pairing repair")
        repairs = {row["candidate_id"]: row["card_refs"] for row in repair_doc["repairs"]}
        tentative = _apply_repairs(current, authority=authority, repairs=repairs, local=local)
        reaudit = run_support_audit(
            ctx=ctx, doc=tentative, authority=authority, local=local,
            call_id=f"{call_id}-repair-{attempt}-audit", root=root, candidate_ids=set(ids),
        )
        accepted: set[str] = set()
        for cid in ids:
            if reaudit[cid]["assessment"] == "supported":
                accepted.add(cid); final[cid] = reaudit[cid]
        if accepted:
            accepted_repairs = {cid: repairs[cid] for cid in accepted}
            current = _apply_repairs(current, authority=authority, repairs=accepted_repairs, local=local)
        for cid in ids:
            repair_log.append({
                "candidate_id": cid,
                "attempt": attempt,
                "proposed_card_refs": repairs[cid],
                "assessment": reaudit[cid]["assessment"],
                "accepted": cid in accepted,
            })
        unsupported = {cid for cid in unsupported if cid not in accepted}
    summary = {
        "initial": [dict(row) for row in initial.values()],
        "repairs": repair_log,
        "final": [dict(row) for row in final.values()],
        "unresolved_unsupported": sorted(unsupported),
        "policy": "unsupported gets bounded card-only repair; unresolved unsupported is warned and does not regenerate the clinical artifact",
    }
    (root / "audit-summary.yaml").write_text(yaml.safe_dump(summary, sort_keys=False, allow_unicode=True, width=110), encoding="utf-8")
    counts = {name: sum(1 for row in final.values() if row["assessment"] == name) for name in ("supported", "unsupported")}
    ctx.status(f"  {call_id}: evidence audit supported={counts['supported']} unsupported={counts['unsupported']}")
    if unsupported:
        ctx.status(f"  {call_id}: warning — unresolved unsupported statement/card pairings: {', '.join(sorted(unsupported))}")
    return current, summary


def _ptbg_bindings(doc: dict, domain: str) -> list[tuple[dict, str, str, str, str]]:
    """Return mutable surfaced statement bindings: row, statement, reason, refs, tags keys."""
    out=[]
    if domain in {"prognosis","biomarker"}:
        for row in doc.get("decisions") or []:
            if row.get("surface"): out.append((row,"statement","reason","case_refs","card_tags"))
    elif domain=="treatment":
        for row in doc.get("decisions") or []:
            if row.get("target_surface"): out.append((row,"target_statement","target_reason","target_case_refs","target_card_tags"))
            if row.get("resistance_surface"): out.append((row,"resistance_statement","resistance_reason","resistance_case_refs","resistance_card_tags"))
    elif domain=="germline":
        for row in doc.get("variant_decisions") or []:
            if row.get("surface"): out.append((row,"statement","reason","case_refs","card_tags"))
        cp=doc.get("clinical_picture") or {}
        if cp.get("surface"): out.append((cp,"statement","reason","case_refs","card_tags"))
    else: raise ValueError(f"unknown PTBG domain {domain!r}")
    return out


def audit_ptbg_domain_and_repair(*, ctx, doc: dict, domain: str, evidence: EvidenceView, call_id: str, root: Path, settings: dict | None = None) -> tuple[dict, dict]:
    """Freeze PTBG statements, reduce evidence, pair local cards, audit, and repair cards only."""
    current=deepcopy(doc); bindings=_ptbg_bindings(current,domain)
    if not bindings:
        summary={"initial":[],"repairs":[],"final":[],"unresolved_unsupported":[],"policy":"no surfaced statements"}
        return current,summary
    # Ignore any model-emitted card tags from the clinical reasoning pass. Citation
    # assignment is a separate local-card task and runtime IDs are resolved by Python.
    synthetic={"diagnoses":[{
        "statement":row[skey],"reason":row[rkey],"case_refs":list(row.get(refkey) or []),"card_tags":[]
    } for row,skey,rkey,refkey,tagkey in bindings]}
    question=f"Which evidence cards may be relevant to the surfaced {domain} statements?"
    local=select_relevant_cards(
        ctx=ctx,evidence=evidence,authority=None,question=question,
        task_context={"statements":[{"statement":r["statement"],"reason":r["reason"]} for r in synthetic["diagnoses"]]},
        call_id=call_id,root=root,settings=settings,role="ptbg",
    )
    paired_tags=pair_statements_to_cards(ctx=ctx,rows=synthetic["diagnoses"],local=local,call_id=call_id,root=root,role="ptbg")
    for row,tags in zip(synthetic["diagnoses"],paired_tags): row["card_tags"]=tags
    repaired,summary=audit_and_repair(ctx=ctx,doc=synthetic,authority="icc",local=local,call_id=call_id,root=root,settings=settings,repair_role="ptbg")
    for binding,repaired_row in zip(bindings,repaired["diagnoses"]):
        row,_skey,_rkey,_refkey,tagkey=binding
        row[tagkey]=list(repaired_row.get("card_tags") or [])
    return current,summary

