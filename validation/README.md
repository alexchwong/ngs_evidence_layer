# NEL validation cases

This directory contains the standalone validation corpus used to test NGS Evidence Layer behaviour.

- `case_summary.md` contains shared stems, per-variant clinical information, NEL tasks, and evaluator marking criteria.
- `cases.py` provides helpers to retrieve case inputs and marking criteria.
- Marking criteria are evaluator-only and must not be supplied to NEL during case execution.

Typical Python usage:

```python
from validation.cases import retrieve_case, retrieve_MC

retrieve_case("1")   # shared stem only
retrieve_case("1A")  # shared stem + variant clinical information
retrieve_MC("1A")    # evaluator marking criteria only
```

Command-line usage:

```bash
# List all available case IDs
python3 validation/retrieve_cli.py list

# Retrieve clinical information for a case variant
python3 validation/retrieve_cli.py case 1A

# Retrieve shared stem only (Case 1)
python3 validation/retrieve_cli.py case 1

# Retrieve marking criteria
python3 validation/retrieve_cli.py MC 1A

# Help
python3 validation/retrieve_cli.py --help
python3 validation/retrieve_cli.py case --help
python3 validation/retrieve_cli.py MC --help
python3 validation/retrieve_cli.py list --help
```
