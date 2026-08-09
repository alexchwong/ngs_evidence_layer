#!/usr/bin/env python3
import argparse

EXAMPLES = {
    1: "01-escalation-fires.md",
    2: "02-escalation-does-not-fire.md",
    3: "03-ambiguous-disease.md",
    4: "04-genes-the-corpus-cannot-address.md",
    5: "05-germline-architecture.md",
    6: "06-sf3b1-diagnostic-adjudication.md",
}

parser = argparse.ArgumentParser()
parser.add_argument("example", type=int, choices=EXAMPLES)
args = parser.parse_args()
name = EXAMPLES[args.example]
print(f"examples/cases/{name}")
print(f"examples/expected/{name}")
