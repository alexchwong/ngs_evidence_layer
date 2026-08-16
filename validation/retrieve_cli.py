#!/usr/bin/env python3
"""Command-line interface for validation case retrieval.

Provides subcommands:
  case    retrieve clinical information for a case variant
  MC      retrieve marking criteria for a case variant
  list    list all available case IDs

Usage:
  retrieve_cli.py case 1A
  retrieve_cli.py MC 1A
  retrieve_cli.py list
"""
import argparse
import re
import sys
from pathlib import Path

# Add parent directory to path to import validation modules
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from validation.cases import retrieve_case, retrieve_MC


def list_cases(case_file: str = "case_summary.md") -> list[str]:
    """List all available case IDs from the case file."""
    text = _read_case_file(case_file)
    
    # Find all case headers (e.g., "# Case 1", "# Case 2")
    case_headers = re.findall(r"^# Case (\d+)", text, flags=re.MULTILINE)
    
    case_ids = []
    for number in case_headers:
        # Add the stem (e.g., "1")
        case_ids.append(number)
        
        # Find all variant headers under this case (e.g., "## Case 1A", "## Case 1B")
        variant_pattern = rf"^## Case {re.escape(number)}([A-Z])\b"
        variants = re.findall(variant_pattern, text, flags=re.MULTILINE)
        for v in variants:
            case_ids.append(f"{number}{v}")
    
    return case_ids


def _read_case_file(case_file: str) -> str:
    """Read the case markdown, resolving relative paths beside this script."""
    path = Path(case_file)
    if not path.is_file() and not path.is_absolute():
        path = Path(__file__).resolve().parent / path
    if not path.is_file():
        raise FileNotFoundError(f"Case file not found: {case_file}")
    return path.read_text(encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    
    # case subcommand
    case_parser = sub.add_parser("case", help="retrieve clinical information for a case variant")
    case_parser.add_argument("case", nargs="?", default="1A",
                            help="Case identifier (e.g., '1' for shared stem, '1A' for variant)")
    case_parser.add_argument("--file", type=Path, default=None,
                           help="Custom case file path (default: validation/case_summary.md)")
    
    # MC subcommand
    mc_parser = sub.add_parser("MC", help="retrieve marking criteria for a case variant")
    mc_parser.add_argument("case", nargs="?", default="1A",
                          help="Case identifier (e.g., '1A' - must include variant letter)")
    mc_parser.add_argument("--file", type=Path, default=None,
                         help="Custom case file path (default: validation/case_summary.md)")
    
    # list subcommand
    list_parser = sub.add_parser("list", help="list all available case IDs")
    list_parser.add_argument("--file", type=Path, default=None,
                            help="Custom case file path (default: validation/case_summary.md)")
    
    args = parser.parse_args()
    
    try:
        if args.command == "case":
            if args.file:
                result = retrieve_case(args.case, str(args.file))
            else:
                result = retrieve_case(args.case)
            print(result)
        
        elif args.command == "MC":
            if args.file:
                result = retrieve_MC(args.case, str(args.file))
            else:
                result = retrieve_MC(args.case)
            print(result)
        
        elif args.command == "list":
            case_file = str(args.file) if args.file else None
            if case_file:
                cases = list_cases(case_file)
            else:
                # Default to case_summary.md in validation folder
                default_path = Path(__file__).resolve().parent / "case_summary.md"
                cases = list_cases(str(default_path))
            
            for case_id in cases:
                print(case_id)
        
    except (FileNotFoundError, KeyError, ValueError) as exc:
        sys.exit(f"Error: {exc}")


if __name__ == "__main__":
    main()
