"""Domain scheduler: one compact validated model call per clinical domain."""
from __future__ import annotations

from workflows.terraced_v3 import layout, runtime
from workflows.terraced_v3.schedulers import common

SCHEDULER_ID = "domain"
DESCRIPTION = "One compact model task each for prognosis, treatment, MRD and germline."

# Backwards-compatible exports used by tests/developer utilities.
task_specs = common.task_specs
contract = common.contract


def run(ctx: common.SchedulerContext) -> None:
    for domain, spec in ctx.specs.items():
        existing_output = layout.domain(ctx.work, domain, "FINAL_STATE.yaml")
        if existing_output.is_file():
            continue
        evidence = ctx.ensure_evidence(domain)
        output = layout.domain(ctx.work, domain, "FINAL_STATE.yaml", existing=False)
        context = ctx.base_context(spec, evidence.text)
        prompt = ctx.domain_task_prompt + "\n\n" + common.contract(domain, ctx.case, ctx.diagnoses) + "\n\n" + context
        call_dir = layout.domain_dir(ctx.work, domain, existing=False) / "call_01_domain"
        call_dir.mkdir(parents=True, exist_ok=True)
        ctx.write_text(call_dir / "INPUT_context.md", context + "\n")
        ctx.write_text(call_dir / "INPUT_cards.json", __import__("json").dumps(evidence.cards, indent=2, ensure_ascii=False) + "\n")
        ctx.call_yaml(
            call_id=f"{domain}-domain",
            prompt=prompt,
            output=output,
            validator=lambda t, d=domain, s=spec, p=evidence.permitted_tags: runtime.validate_domain_text(t, domain=d, spec=s, permitted_tags=p),
        )
