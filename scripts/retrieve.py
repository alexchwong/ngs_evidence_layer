#!/usr/bin/env python3
"""Workflow-dispatched deterministic evidence retrieval.

The work directory is bound to a workflow by ``scripts/setup_workflow.py``.
This CLI therefore needs only the retrieval stage and work directory. Workflow-
specific card-selection policy lives under ``workflows/<workflow>/retrieval.py``;
shared corpus, blacklist, validation, provenance and tag mechanics live in
``scripts/retrieval_core.py``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
for path in (str(SCRIPT_DIR), str(REPO_ROOT)):
    if path not in sys.path:
        sys.path.insert(0, path)

from retrieval_core import *  # noqa: F401,F403,E402
from retrieval_core import _adjudication_diagnosis_card_ids  # noqa: E402
from scripts.workflow_registry import import_workflow_module, workflow_for_work_dir  # noqa: E402
from workflows.legacy_v1.retrieval import step2, step4  # noqa: E402,F401
from workflows.diagnosis_first_v1.retrieval import (  # noqa: E402,F401
    step2 as diagnosis_first_step2,
    step4 as diagnosis_first_step4,
)



# Compatibility programmatic APIs used by deterministic validators/tests. They
# delegate selection policy to legacy-v1; the skill runtime itself uses work-dir
# dispatch through run_stage().
def run_diagnosis(args):
    import json as _json
    from workflows.legacy_v1 import retrieval as legacy
    corpus, _index, digest = load_corpus(args.corpus, args.index)
    cards = blacklist_cards(flatten(corpus), args.blacklist)
    case_input = validate_case_input(args.case_input) if getattr(args, "case_input", None) else None
    genes = [g.upper() for g in args.genes] if getattr(args, "genes", None) else case_input["genes"]
    provisional = (
        args.provisional_disease if getattr(args, "provisional_disease", None) is not None
        else case_input["provisional_disease"] if case_input else vocab.UNSPECIFIED_DISEASE
    )
    case_major_category = (
        args.case_major_category if getattr(args, "case_major_category", None) is not None
        else case_input["case_major_category"] if case_input else None
    )
    if getattr(args, "case_facts", None):
        doc = _json.loads(args.case_facts.read_text(encoding="utf-8"))
        case_facts = doc.get("case_facts") if isinstance(doc, dict) else doc
    elif case_input:
        case_facts = case_input["case_facts"]
    else:
        raise ValueError("--case-facts is required unless --case-input is provided")
    result = legacy.step2(cards, genes, provisional, case_facts, case_major_category=case_major_category)
    result["card_tags"] = card_tags.build_card_tags(card["card_id"] for card in cards)
    result["corpus"] = {"path": str(args.corpus), "index": str(args.index)}
    result["provenance"] = provenance(corpus, args.corpus, args.index, digest, [c["card_id"] for c in result["diagnosis_cards"]])
    return result


def run_full(args):
    import json as _json
    from workflows.legacy_v1 import retrieval as legacy
    step2_result = load_step_json(args.diagnosis_result)
    adjudication_raw = _json.loads(Path(args.adjudication_result).read_text(encoding="utf-8"))
    adjudication = normalise_adjudication(step2_result, adjudication_raw, require_completed_review=True)
    corpus_path = Path(args.corpus or step2_result["corpus"]["path"])
    index_path = Path(args.index or step2_result["corpus"]["index"])
    corpus, _index, digest = load_corpus(corpus_path, index_path)
    genes = args.genes if getattr(args, "genes", None) is not None else step2_result["genes"]
    blacklist = getattr(args, "blacklist", DEFAULT_BLACKLIST)
    cards = blacklist_cards(flatten(corpus), blacklist)
    eligible_card_ids = {card["card_id"] for card in cards}
    current_tag_map = card_tags.build_card_tags(eligible_card_ids)
    step2_tag_map = step2_result.get("card_tags")
    step2_tags = card_tags.tag_by_id(step2_tag_map or {})
    current_tags = card_tags.tag_by_id(current_tag_map)
    changed_tags = sorted(
        card_id for card_id in {card["card_id"] for card in step2_result["diagnosis_cards"]}
        if step2_tag_map and step2_tags.get(card_id) != current_tags.get(card_id)
    )
    if changed_tags:
        raise ValueError("runtime card tags for Step-2 diagnosis evidence no longer match the current eligible corpus: " + ", ".join(changed_tags))
    newly_blocked = sorted(_adjudication_diagnosis_card_ids(adjudication) - eligible_card_ids)
    if newly_blocked:
        raise ValueError("blacklist excludes diagnosis card(s) used by the completed adjudication: " + ", ".join(newly_blocked))
    refined = adjudication["downstream_filter_disease"]
    selected = legacy.step4(cards, genes, refined, step2_result["diagnosis_cards"], adjudication=adjudication, case_major_category=step2_result["case_major_category"])
    result = {
        "step": 4,
        "genes": sorted({gene.upper() for gene in genes}),
        "case_major_category": step2_result["case_major_category"],
        "provisional_disease": step2_result["provisional_disease"],
        "refined_disease": refined,
        "diagnostic_adjudication": adjudication,
        "diagnostic_context": [dict(card) for card in cards if card["category"] == "diagnosis" and card["card_id"] in {item["card_id"] for item in step2_result["diagnosis_cards"]}],
        "runtime_card_tags": current_tag_map,
        **selected,
    }
    result["provenance"] = provenance(corpus, corpus_path, index_path, digest, [card["card_id"] for card in result["retrieved"]])
    return result

def run_stage(stage: str, work_dir: Path) -> Path:
    workflow_id, _metadata = workflow_for_work_dir(work_dir)
    retrieval = import_workflow_module(workflow_id, "retrieval")
    implementation = getattr(retrieval, stage, None)
    if implementation is None:
        raise ValueError(f"workflow {workflow_id!r} does not implement retrieval stage {stage!r}")
    return implementation(work_dir.resolve())


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("stage", choices=("diagnosis", "downstream"))
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        output = run_stage(args.stage, args.work_dir)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"retrieval failed: {exc}\n")
    print(f"wrote {output}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
