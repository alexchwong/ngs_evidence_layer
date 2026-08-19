"""Retrieve clinical case text or marking criteria from ``case_summary.md``."""

from pathlib import Path
import re


VALIDATION_CASE_FILES = {
    "nel-validate": "case_summary.md",
    "nel-validate-function": "case_functional.md",
    "nel-validate-brief": "validation_brief.md",
}


def case_file_for_mode(mode: str) -> str:
    """Return the validation case source associated with a public validation mode."""
    try:
        return VALIDATION_CASE_FILES[mode]
    except KeyError as exc:
        raise ValueError(f"Unsupported validation mode: {mode!r}") from exc


def _read_case_file(case_file: str = "case_summary.md") -> str:
    """Read the case markdown, resolving relative paths beside this script."""
    path = Path(case_file)
    if not path.is_file() and not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    if not path.is_file():
        raise FileNotFoundError(f"Case file not found: {case_file}")
    return path.read_text(encoding="utf-8")


def retrieve_case(case: str = "1A", case_file: str = "case_summary.md") -> str:
    """Return only clinical information for a standalone case, stem, or variant.

    ``retrieve_case("1")`` returns either a standalone Case 1 clinical section
    (used by ``validation_brief.md``) or the shared stem for a legacy variant
    suite. ``retrieve_case("1A")`` returns the Case 1 stem followed by the
    clinical information specific to variant 1A. NEL tasks and marking
    criteria are never included.
    """
    case_id = str(case).strip().upper()
    match = re.fullmatch(r"(\d+)([A-Z]?)", case_id)
    if not match:
        raise ValueError(f"Invalid case identifier: {case!r}")

    case_number, variant = match.groups()
    text = _read_case_file(case_file)

    case_block_match = re.search(
        rf"^# Case {re.escape(case_number)}\b.*?$(.*?)(?=^# Case \d+\b|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not case_block_match:
        raise KeyError(f"Case {case_number} not found")
    case_block = case_block_match.group(1)

    standalone_match = re.search(
        r"^## Clinical information\s*\n(.*?)(?=^## NEL task\s*$)",
        case_block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if standalone_match:
        if variant:
            raise KeyError(f"Case {case_number} is standalone and has no variant {variant}")
        return standalone_match.group(1).strip()

    stem_match = re.search(
        r"^## Shared stem\s*\n(.*?)(?=^## Case \d+[A-Z]\b|\Z)",
        case_block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not stem_match:
        raise ValueError(f"Case {case_number} has no shared stem")
    stem = stem_match.group(1).strip()

    if not variant:
        return stem

    variant_id = f"{case_number}{variant}"
    variant_match = re.search(
        rf"^## Case {re.escape(variant_id)}\b.*?^### Clinical information\s*\n"
        rf"(.*?)(?=^### NEL task\s*$)",
        case_block,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not variant_match:
        raise KeyError(f"Case variant {variant_id} not found")

    clinical_information = variant_match.group(1).strip()
    return f"{stem}\n\n{clinical_information}".strip()


def retrieve_MC(case: str = "1A", case_file: str = "case_summary.md") -> str:
    """Return only the marking criteria for a standalone case or case variant."""
    case_id = str(case).strip().upper()
    match = re.fullmatch(r"(\d+)([A-Z]?)", case_id)
    if not match:
        raise ValueError("retrieve_MC requires a case identifier such as '1' or '1A'")

    case_number, variant = match.groups()
    text = _read_case_file(case_file)

    if not variant:
        standalone_match = re.search(
            rf"^# Case {re.escape(case_number)}\b.*?^## Marking criteria\s*\n"
            rf"(.*?)(?=^---\s*$|^# Case \d+\b|^# Source notes\b|\Z)",
            text,
            flags=re.MULTILINE | re.DOTALL,
        )
        if standalone_match:
            return standalone_match.group(1).strip()
        raise ValueError(
            f"retrieve_MC requires a variant identifier for Case {case_number}; "
            "this case file does not define standalone marking criteria"
        )

    criteria_match = re.search(
        rf"^## Case {re.escape(case_id)}\b.*?^### Marking criteria\s*\n"
        rf"(.*?)(?=^## Case \d+[A-Z]\b|^---\s*$|^# Case \d+\b|^# Source notes\b|\Z)",
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not criteria_match:
        raise KeyError(f"Marking criteria for case variant {case_id} not found")

    return criteria_match.group(1).strip()
