"""Legacy-v1 diagnosis adjudication policy and validation."""
from __future__ import annotations

import json

from scripts import vocab
from scripts.core import card_tags
from scripts.core.retrieval import (
    _field_mismatch_message,
    _normalise_genes,
    _validate_case_disease,
    _validate_case_major_category,
    validate_case_facts,
)

def _validate_user_review(
    adjudication, genes, allowed_refined_diseases, retrieved_card_ids, *,
    require_completed_review
):
    """Validate automatic or manual Step 3 review state."""
    review = adjudication.get("user_review")
    model_refined = adjudication["refined_disease"]
    model_label = adjudication["diagnostic_label"]
    downstream = adjudication["downstream_filter_disease"]

    if review == "automatic":
        if downstream != model_refined:
            raise ValueError(
                "automatic user_review requires downstream_filter_disease to exactly "
                "equal refined_disease"
            )
        return review

    if review is None:
        if require_completed_review:
            raise ValueError("user_review is required before Step 4")
        if downstream != model_refined:
            raise ValueError(
                "without user_review, downstream_filter_disease must exactly equal "
                "refined_disease"
            )
        return None

    review_keys = {"decision", "diagnostic_label", "refined_disease", "reason", "card_ids"}
    if not isinstance(review, dict) or set(review) != review_keys:
        raise ValueError(
            "user_review must be 'automatic' or contain exactly: "
            + ", ".join(sorted(review_keys))
        )
    decision = review["decision"]
    if decision not in {"pending", "agree", "disagree"}:
        raise ValueError(f"invalid user_review decision {decision!r}")
    reviewed_label = review["diagnostic_label"]
    if reviewed_label is not None and (
        not isinstance(reviewed_label, str) or not reviewed_label.strip()
    ):
        raise ValueError(
            "user_review diagnostic_label must be null or a non-empty string"
        )
    reviewed_refined = review["refined_disease"]
    if reviewed_refined is not None:
        _validate_case_disease(
            reviewed_refined,
            genes,
            field="user_review refined_disease",
        )
        if reviewed_refined not in allowed_refined_diseases:
            raise ValueError(
                f"user_review.refined_disease {reviewed_refined!r} is not allowed. Replace it with one "
                f"of: {', '.join(allowed_refined_diseases)}"
            )
    reviewed_reason = review["reason"]
    reviewed_cards = review["card_ids"]
    if reviewed_reason is not None and (
        not isinstance(reviewed_reason, str) or not reviewed_reason.strip()
    ):
        raise ValueError("user_review reason must be null or a non-empty string")
    if not isinstance(reviewed_cards, list) or any(
        not isinstance(card_id, str) or not card_id for card_id in reviewed_cards
    ):
        raise ValueError("user_review card_ids must be an array of non-empty strings")
    if len(reviewed_cards) != len(set(reviewed_cards)):
        raise ValueError("user_review card_ids must be unique")
    if any(card_id not in retrieved_card_ids for card_id in reviewed_cards):
        invalid = [card_id for card_id in reviewed_cards if card_id not in retrieved_card_ids]
        raise ValueError(
            "user_review.card_ids contains unretrieved diagnosis card ID(s): " + ", ".join(invalid)
            + ". Replace/remove only those IDs using exact six-character card tags shown in diagnostic_evidence.md."
        )

    if decision == "pending":
        if (
            reviewed_label is not None
            or reviewed_refined is not None
            or reviewed_reason is not None
            or reviewed_cards
        ):
            raise ValueError(
                "pending user_review must have null diagnostic_label, refined_disease, "
                "and reason, with empty card_ids"
            )
        if downstream != model_refined:
            raise ValueError(
                "pending user_review must preserve the model refined_disease as the "
                "downstream_filter_disease"
            )
        if require_completed_review:
            raise ValueError("user review is pending; Step 4 is blocked")
        return review
    if reviewed_refined is None:
        raise ValueError("completed user_review requires refined_disease")
    if downstream != reviewed_refined:
        raise ValueError(
            "downstream_filter_disease must exactly equal user_review.refined_disease"
        )
    if decision == "agree":
        if (
            reviewed_refined != model_refined
            or reviewed_label != model_label
            or reviewed_reason != adjudication["reason"]
            or reviewed_cards != adjudication["driven_by"]
        ):
            raise ValueError(
                "an agreeing user_review must copy the model diagnostic_label, "
                "refined_disease, reason, and driven_by cards exactly"
            )
    else:
        if reviewed_label is None:
            raise ValueError(
                "a disagreeing user_review requires the user's integrated diagnostic_label"
            )
        if reviewed_reason is None or not reviewed_cards:
            raise ValueError(
                "a disagreeing user_review requires an evidence-grounded reason and card_ids"
            )
    return review


def _translate_model_card_tags(step2_result, adjudication):
    """Translate Step-3 model-facing card tags to private stable card IDs.

    Returns a deep JSON-compatible copy. Already-translated stable IDs are accepted
    for internal callers/tests, but model-facing six-character values must resolve
    through the private Step-2 tag table.
    """
    translated = json.loads(json.dumps(adjudication))
    mapping = card_tags.id_by_tag(step2_result.get("card_tags") or {})
    stable_ids = {card["card_id"] for card in step2_result.get("diagnosis_cards", [])}

    def one(value, field):
        if not isinstance(value, str) or not value:
            raise ValueError(
                f"{field} must contain non-empty six-character card tags copied from diagnostic_evidence.md."
            )
        if value in stable_ids:
            return value
        if value in mapping:
            return mapping[value]
        raise ValueError(
            f"{field} contains unknown diagnosis card tag {value!r}. "
            "Replace it with an exact six-character [card:xxxxxx] tag shown in diagnostic_evidence.md."
        )

    driven = translated.get("driven_by")
    if isinstance(driven, list):
        translated["driven_by"] = [one(value, "adjudication.driven_by") for value in driven]
    assessments = translated.get("criterion_assessment")
    if isinstance(assessments, list):
        for index, item in enumerate(assessments):
            if isinstance(item, dict):
                if "card_tags" in item and "card_ids" in item:
                    raise ValueError(
                        f"criterion_assessment[{index}] must contain card_tags in model output, not both card_tags and card_ids."
                    )
                values = item.get("card_tags", item.get("card_ids"))
                if values is not None:
                    item["card_ids"] = [one(value, f"criterion_assessment[{index}].card_tags") for value in values]
                    item.pop("card_tags", None)
    review = translated.get("user_review")
    if isinstance(review, dict):
        if "card_tags" in review and "card_ids" in review:
            raise ValueError(
                "user_review must contain card_tags in model output, not both card_tags and card_ids."
            )
        values = review.get("card_tags", review.get("card_ids"))
        if values is not None:
            review["card_ids"] = [one(value, "user_review.card_tags") for value in values]
            review.pop("card_tags", None)
    return translated


def normalise_adjudication(step2_result, adjudication, *, require_completed_review=False):
    """Translate model card tags, validate, and return private stable-ID JSON."""
    translated = _translate_model_card_tags(step2_result, adjudication)
    validate_adjudication(
        step2_result, translated, require_completed_review=require_completed_review
    )
    return translated


def validate_adjudication(step2_result, adjudication, *, require_completed_review=False):
    base_keys = {
        "status", "provisional_disease", "refined_disease",
        "downstream_filter_disease", "diagnostic_label", "driven_by",
        "criterion_assessment", "reason",
    }
    allowed_key_sets = {frozenset(base_keys), frozenset(base_keys | {"user_review"})}
    if not isinstance(adjudication, dict) or frozenset(adjudication) not in allowed_key_sets:
        expected = base_keys | ({"user_review"} if "user_review" in adjudication else set()) if isinstance(adjudication, dict) else base_keys
        actual = adjudication.keys() if isinstance(adjudication, dict) else []
        raise ValueError(
            _field_mismatch_message("adjudication.json", actual, expected)
            + ". Restore the exact adjudication schema from the Step 3 prompt; do not add explanatory fields."
        )
    status = adjudication["status"]
    if status not in {"criteria_met", "criteria_not_met", "indeterminate"}:
        raise ValueError(
            f"adjudication.status has invalid value {status!r}; use exactly one of: "
            "criteria_met, criteria_not_met, indeterminate."
        )
    provisional = step2_result["provisional_disease"]
    if not isinstance(provisional, str) or not provisional.strip():
        raise ValueError("step2 provisional_disease must be a non-empty string")
    genes = _normalise_genes(step2_result["genes"], field="step2 genes")
    case_major_category = step2_result.get("case_major_category")
    _validate_case_major_category(case_major_category, genes, field="step2 case_major_category")
    allowed_refined_diseases = step2_result.get("allowed_refined_diseases", [])
    if not isinstance(allowed_refined_diseases, list) or any(
        disease not in vocab.CASE_DISEASE_SET for disease in allowed_refined_diseases
    ):
        raise ValueError("step2 allowed_refined_diseases is invalid")
    if adjudication["provisional_disease"] != provisional:
        raise ValueError(
            f"adjudication.provisional_disease is {adjudication['provisional_disease']!r}, but "
            f"diagnostic_evidence.md supplies {provisional!r}. Copy the provisional disease exactly; "
            "do not reinterpret it in this field."
        )
    refined = adjudication["refined_disease"]
    _validate_case_disease(refined, genes, field="adjudication refined_disease")
    if refined not in allowed_refined_diseases:
        raise ValueError(
            f"adjudication.refined_disease {refined!r} is not allowed. Replace it with exactly one "
            f"of the allowed refined diseases from diagnostic_evidence.md: {', '.join(allowed_refined_diseases)}"
        )
    downstream = adjudication["downstream_filter_disease"]
    _validate_case_disease(
        downstream,
        genes,
        field="adjudication downstream_filter_disease",
    )
    if downstream not in allowed_refined_diseases:
        raise ValueError(
            f"adjudication.downstream_filter_disease {downstream!r} is not allowed. Replace it with "
            f"the applicable refined disease from this allowed list: {', '.join(allowed_refined_diseases)}"
        )
    label = adjudication["diagnostic_label"]
    if label is not None and (not isinstance(label, str) or not label.strip()):
        raise ValueError("diagnostic_label must be null or a non-empty string")
    if not isinstance(adjudication["reason"], str) or not adjudication["reason"].strip():
        raise ValueError("adjudication reason must be a non-empty string")
    retrieved_card_ids = {card["card_id"] for card in step2_result["diagnosis_cards"]}
    driven_by = adjudication["driven_by"]
    if not isinstance(driven_by, list) or any(card_id not in retrieved_card_ids for card_id in driven_by):
        invalid = [card_id for card_id in driven_by if card_id not in retrieved_card_ids] if isinstance(driven_by, list) else [repr(driven_by)]
        raise ValueError(
            "adjudication.driven_by contains invalid diagnosis card ID(s): " + ", ".join(map(str, invalid))
            + ". Replace/remove only those IDs using exact six-character card tags shown in diagnostic_evidence.md."
        )
    if len(driven_by) != len(set(driven_by)):
        duplicates = sorted({card_id for card_id in driven_by if driven_by.count(card_id) > 1})
        raise ValueError(
            "adjudication.driven_by repeats card ID(s): " + ", ".join(duplicates)
            + ". Keep each cited diagnosis card ID once."
        )
    supplied_fact_ids = {fact["fact_id"] for fact in validate_case_facts(step2_result["case_facts"])}
    assessments = adjudication["criterion_assessment"]
    if not isinstance(assessments, list):
        raise ValueError("criterion_assessment must be an array")
    required_assessments = []
    for index, item in enumerate(assessments):
        item_keys = {"criterion", "required", "status", "card_ids", "case_fact_ids"}
        if not isinstance(item, dict) or set(item) != item_keys:
            raise ValueError(
                _field_mismatch_message(
                    f"criterion_assessment[{index}]",
                    item.keys() if isinstance(item, dict) else [],
                    item_keys,
                )
                + ". That assessment must contain exactly: " + ", ".join(sorted(item_keys))
            )
        if not isinstance(item["criterion"], str) or not item["criterion"].strip():
            raise ValueError(f"criterion_assessment[{index}].criterion must be non-empty")
        if not isinstance(item["required"], bool):
            raise ValueError(f"criterion_assessment[{index}].required must be boolean")
        if item["status"] not in {"met", "not_met", "unknown"}:
            raise ValueError(
                f"criterion_assessment[{index}].status has invalid value {item['status']!r}; "
                "use exactly one of: met, not_met, unknown."
            )
        if not isinstance(item["card_ids"], list) or not item["card_ids"]:
            raise ValueError(f"criterion_assessment[{index}] must cite a diagnosis card")
        if any(card_id not in retrieved_card_ids for card_id in item["card_ids"]):
            invalid = [card_id for card_id in item["card_ids"] if card_id not in retrieved_card_ids]
            raise ValueError(
                f"criterion_assessment[{index}].card_ids contains unretrieved ID(s): "
                + ", ".join(invalid)
                + ". Replace/remove only those IDs using exact six-character diagnosis card tags shown in diagnostic_evidence.md."
            )
        if not isinstance(item["case_fact_ids"], list):
            raise ValueError(f"criterion_assessment[{index}].case_fact_ids must be an array")
        if any(fact_id not in supplied_fact_ids for fact_id in item["case_fact_ids"]):
            invalid = [fact_id for fact_id in item["case_fact_ids"] if fact_id not in supplied_fact_ids]
            raise ValueError(
                f"criterion_assessment[{index}].case_fact_ids cites an unsupplied case fact; "
                "unknown fact ID(s): "
                + ", ".join(invalid)
                + ". Replace/remove only those IDs using exact fact IDs shown in diagnostic_evidence.md."
            )
        if item["status"] != "unknown" and not item["case_fact_ids"]:
            raise ValueError(f"criterion_assessment[{index}] must cite a case fact")
        if item["required"]:
            required_assessments.append(item)
    if status == "criteria_met" and any(
        item["status"] != "met" for item in required_assessments
    ):
        bad = [
            f"criterion_assessment[{i}]={item['status']} ({item['criterion']})"
            for i, item in enumerate(assessments) if item.get("required") and item.get("status") != "met"
        ]
        raise ValueError(
            "adjudication.status is 'criteria_met', but every required criterion must be met; "
            "these required criteria are not met: "
            + "; ".join(bad)
            + ". Either correct the individual criterion status if supported by the cited facts/cards, "
              "or change adjudication.status to criteria_not_met or indeterminate."
        )
    changed_major_category = not vocab.disease_matches_case_major_category(
        refined, case_major_category
    )
    if status != "criteria_met" and changed_major_category:
        raise ValueError(
            f"adjudication.status is {status!r}, so refined_disease {refined!r} cannot move outside "
            f"the original case_major_category {case_major_category!r}. Keep refined_disease within "
            "the original major category unless all required diagnostic criteria for the new category are met."
        )
    if changed_major_category:
        if not driven_by:
            raise ValueError("a changed major category requires at least one driving card")
        if not required_assessments:
            raise ValueError("a changed major category requires at least one required criterion")
        if any(item["status"] != "met" for item in required_assessments):
            raise ValueError("a changed major category requires every required criterion to be met")
    _validate_user_review(
        adjudication,
        genes,
        allowed_refined_diseases,
        retrieved_card_ids,
        require_completed_review=require_completed_review,
    )
    return adjudication


def _adjudication_diagnosis_card_ids(adjudication):
    """Return diagnosis cards actually cited/used by Step 3, preserving no extras."""
    selected = set(adjudication.get("driven_by") or [])
    for assessment in adjudication.get("criterion_assessment") or []:
        selected.update(assessment.get("card_ids") or [])
    review = adjudication.get("user_review")
    if isinstance(review, dict) and review.get("decision") in {"agree", "disagree"}:
        selected.update(review.get("card_ids") or [])
    return selected
