"""Revenue Operations multi-agent workflow using Agno 2.5.x."""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

from agno.workflow import Step, StepInput, StepOutput, Workflow

from app.agents.action_agent import create_action_agent
from app.agents.enrichment_agent import build_enrichment_prompt, create_enrichment_agent
from app.agents.review_agent import create_review_agent
from app.agents.triage_agent import create_triage_agent
from app.models.schemas import (
    ActionPlan, EnrichedLead, EnrichmentOutput,
    HumanApprovalResult, Lead, ReviewDecision, ReviewOutput, TriageResult, WorkflowState,
)
from app.tools.observability import ObservabilityTracker

MAX_RETRIES = 3


def _unwrap(parsed: dict, schema) -> dict:
    """If LLM wraps output in a single key (e.g. {'action_plan': {...}}), unwrap it."""
    if len(parsed) == 1:
        key = next(iter(parsed))
        val = parsed[key]
        if isinstance(val, dict):
            # Try the unwrapped version; if it validates, use it
            schema_fields = schema.model_fields.keys()
            if any(f in val for f in schema_fields):
                return val
    return parsed


def _resolve_lead_input(step_input: StepInput) -> Lead:
    """Validate runtime workflow input as a Lead model."""
    payload = step_input.input
    if payload is None:
        raise ValueError("Lead input is required to start the workflow.")

    if isinstance(payload, Lead):
        return payload
    if isinstance(payload, str):
        payload = json.loads(payload)

    return Lead.model_validate(payload)


def _start_run_context(step_input: StepInput, tracker: ObservabilityTracker, state: WorkflowState) -> Lead:
    """
    Initialize per-run lead/state for CLI and AgentOS UI execution.

    AgentOS can reuse the same workflow instance across runs, so we reset state
    when a previous run has already populated outputs or the lead changes.
    """
    lead = _resolve_lead_input(step_input)
    has_existing_run = any(
        value is not None for value in (state.triage, state.enriched, state.action_plan, state.review)
    )

    if state.lead is None or state.lead.id != lead.id or has_existing_run:
        state.start_run(lead)
        tracker.reset(lead.id)

    return lead


def _run_with_retry(agent, prompt: str, schema, agent_name: str, tracker: ObservabilityTracker, inject: dict | None = None):
    """Run an agent with retry. Returns parsed Pydantic model or raises RuntimeError."""
    last_exc = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            tracker.agent_start(agent_name)
            response = agent.run(prompt)
            content = response.content

            if isinstance(content, schema):
                result = content
            elif isinstance(content, str):
                parsed = json.loads(content)
                parsed = _unwrap(parsed, schema)
                if inject:
                    parsed.update(inject)
                result = schema.model_validate(parsed)
            else:
                if isinstance(content, dict):
                    content = _unwrap(content, schema)
                    if inject:
                        content.update(inject)
                result = schema.model_validate(content)

            tokens = 0
            if hasattr(response, "metrics") and response.metrics:
                tokens = getattr(response.metrics, "total_tokens", 0) or 0
            tracker.agent_end(agent_name, tokens=tokens)
            return result

        except Exception as exc:
            last_exc = exc
            tracker.record_error(f"{agent_name} attempt {attempt}/{MAX_RETRIES}: {exc}")
            time.sleep(0.3 * attempt)

    raise RuntimeError(f"{agent_name} failed after {MAX_RETRIES} attempts: {last_exc}")


def _build_steps(tracker: ObservabilityTracker, state: WorkflowState, interactive: bool = False) -> list:
    """Build workflow steps over a typed shared state object."""

    def triage_executor(step_input: StepInput) -> StepOutput:
        lead = _start_run_context(step_input, tracker, state)
        agent = create_triage_agent()
        triage = _run_with_retry(
            agent,
            f"Coordinate and triage this lead:\n{lead.model_dump_json(indent=2)}",
            TriageResult, "TriageAgent", tracker,
            inject={"lead_id": lead.id},
        )
        state.triage = triage
        print(
            f"  ✅ Triage → {triage.urgency.upper()} | {triage.category} | "
            f"lane={triage.workflow_lane} | score={triage.priority_score}/10"
        )
        print(f"     {triage.reason}")
        print(f"     Brief: {triage.specialist_brief}")
        return StepOutput(step_name="TriageAgent", content=triage.model_dump_json(), success=True)

    def enrichment_executor(step_input: StepInput) -> StepOutput:
        lead = state.lead
        triage = state.triage
        if lead is None or triage is None:
            return StepOutput(step_name="EnrichmentAgent", content="Skipped — no triage", success=False, stop=True)

        prompt = build_enrichment_prompt(lead.model_dump(), triage.model_dump())
        agent = create_enrichment_agent()
        enrichment_out = _run_with_retry(agent, prompt, EnrichmentOutput, "EnrichmentAgent", tracker)

        # Assemble EnrichedLead from LLM output + known lead/triage
        enriched = EnrichedLead(
            lead=lead,
            triage=triage,
            company_profile=enrichment_out.company_profile,
            risk_flags=enrichment_out.risk_flags,
        )
        state.enriched = enriched
        flags = enriched.risk_flags or ["none"]
        print(f"  ✅ Enrichment → {enriched.company_profile.company_size} | health={enriched.company_profile.health_score:.0%} | flags={flags}")
        return StepOutput(step_name="EnrichmentAgent", content=enriched.model_dump_json(), success=True)

    def action_executor(step_input: StepInput) -> StepOutput:
        lead = state.lead
        triage = state.triage
        enriched = state.enriched
        if enriched is None:
            return StepOutput(step_name="ActionAgent", content="Skipped — no enriched lead", success=False, stop=True)

        agent = create_action_agent()
        prompt = json.dumps(
            {
                "triage": triage.model_dump() if triage is not None else None,
                "enriched_lead": enriched.model_dump(),
            },
            indent=2,
        )
        plan = _run_with_retry(
            agent, prompt, ActionPlan, "ActionAgent", tracker,
            inject={"lead_id": lead.id if lead is not None else enriched.lead.id},
        )
        state.action_plan = plan
        print(f"  ✅ Actions → {len(plan.recommended_actions)} actions | close_prob={plan.estimated_close_probability:.0%}")
        print(f"     Next: {plan.next_best_action}")
        return StepOutput(step_name="ActionAgent", content=plan.model_dump_json(), success=True)

    def review_executor(step_input: StepInput) -> StepOutput:
        lead = state.lead
        triage = state.triage
        enriched = state.enriched
        plan = state.action_plan
        if lead is None or triage is None or enriched is None or plan is None:
            return StepOutput(step_name="ReviewAgent", content="Skipped — missing inputs", success=False, stop=True)

        prompt = json.dumps(
            {
                "triage": triage.model_dump(),
                "enriched_lead": enriched.model_dump(),
                "action_plan": plan.model_dump(),
            },
            indent=2,
        )
        agent = create_review_agent()
        decision = _run_with_retry(agent, prompt, ReviewDecision, "ReviewAgent", tracker)

        # Assemble ReviewOutput with the existing action plan
        review = ReviewOutput(
            lead_id=lead.id,
            approved=decision.approved,
            quality_score=decision.quality_score,
            feedback=decision.feedback,
            final_action_plan=plan,
            escalate_to_manager=decision.escalate_to_manager,
        )
        state.review = review
        status = "✅ APPROVED" if review.approved else "⚠️  NEEDS REVISION"
        escalate = " 🚨 ESCALATE" if review.escalate_to_manager else ""
        print(f"  {status} | quality={review.quality_score:.0%}{escalate}")
        print(f"     {review.feedback}")
        return StepOutput(step_name="ReviewAgent", content=review.model_dump_json(), success=True)

    def human_approval_executor(step_input: StepInput) -> StepOutput:  # noqa: ARG001
        review = state.review
        lead = state.lead
        if review is None or lead is None:
            return StepOutput(step_name="HumanApproval", content="Skipped — no review", success=False, stop=True)

        needs_approval = review.escalate_to_manager or not review.approved
        ts = datetime.now(timezone.utc).isoformat()

        if not needs_approval:
            result = HumanApprovalResult(
                lead_id=lead.id,
                decision="skipped",
                triggered_by="auto_skipped",
                timestamp=ts,
            )
            state.human_approval = result
            print("  ✅ Human Approval → skipped (no escalation required)")
            return StepOutput(step_name="HumanApproval", content=result.model_dump_json(), success=True)

        # Determine why approval is needed
        if review.escalate_to_manager and not review.approved:
            triggered_by = "escalate_to_manager"
        elif review.escalate_to_manager:
            triggered_by = "escalate_to_manager"
        else:
            triggered_by = "review_rejected"

        # Print approval summary
        reasons = []
        if review.escalate_to_manager:
            reasons.append("escalate_to_manager=True")
        if not review.approved:
            reasons.append(f"review not approved (quality={review.quality_score:.0%})")
        reason_str = " | ".join(reasons)

        print(f"\n  {'=' * 56}")
        print(f"  ⚠️  HUMAN APPROVAL REQUIRED")
        print(f"  {'=' * 56}")
        print(f"  Lead     : {lead.name} @ {lead.company}")
        print(f"  Reason   : {reason_str}")
        print(f"  Quality  : {review.quality_score:.0%}  |  Feedback: {review.feedback}")
        print(f"  {'=' * 56}")

        if not interactive:
            result = HumanApprovalResult(
                lead_id=lead.id,
                decision="approved",
                comment="Auto-approved (non-interactive mode)",
                triggered_by=triggered_by,
                timestamp=ts,
            )
            state.human_approval = result
            print("  ✅ Human Approval → auto-approved (non-interactive mode)")
            return StepOutput(step_name="HumanApproval", content=result.model_dump_json(), success=True)

        # Blocking CLI prompt
        try:
            raw = input("\n  Approve? [y/n] (optional comment after space): ").strip()
        except EOFError:
            raw = "y"

        parts = raw.split(" ", 1)
        answer = parts[0].lower()
        comment = parts[1] if len(parts) > 1 else ""
        decision = "approved" if answer in ("y", "yes") else "rejected"

        result = HumanApprovalResult(
            lead_id=lead.id,
            decision=decision,
            comment=comment,
            triggered_by=triggered_by,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )
        state.human_approval = result

        icon = "✅" if decision == "approved" else "❌"
        print(f"\n  {icon} Human Approval → {decision.upper()}" + (f" — {comment}" if comment else ""))
        return StepOutput(step_name="HumanApproval", content=result.model_dump_json(), success=True)

    return [
        Step(name="TriageAgent", executor=triage_executor, on_error="skip"),
        Step(name="EnrichmentAgent", executor=enrichment_executor, on_error="skip"),
        Step(name="ActionAgent", executor=action_executor, on_error="skip"),
        Step(name="ReviewAgent", executor=review_executor, on_error="skip"),
        Step(name="HumanApproval", executor=human_approval_executor, on_error="skip"),
    ]


def build_revops_workflow(session_id: str = "revops-ui") -> Workflow:
    """Return a Workflow instance for AgentOS UI with runtime lead input."""
    tracker = ObservabilityTracker(lead_id="ui-pending")
    state = WorkflowState()
    return Workflow(
        id="revops-workflow",
        name="RevOps Workflow",
        description="Revenue Operations: Intake/Triage → Enrichment → Action Planning → Review",
        session_id=session_id,
        steps=_build_steps(tracker, state),
        input_schema=Lead,
    )


def run_revops(lead_data: dict, session_id: str = "revops", interactive: bool | None = None) -> dict:
    """
    Validate lead, run 4-agent pipeline, return result dict.

    Failure scenario 1: malformed lead → caught before any agent runs.
    Failure scenario 2: LLM failure → retried up to MAX_RETRIES times per agent.
    """
    # Failure scenario 1: malformed / missing lead fields
    try:
        lead = Lead(**lead_data)
    except Exception as exc:
        return {"error": f"Invalid lead data: {exc}", "lead_id": lead_data.get("id")}

    tracker = ObservabilityTracker(lead_id=lead.id)
    state = WorkflowState()
    state.start_run(lead)

    print(
        f"\n🚀 RevOps [{tracker.workflow_id}] — "
        f"{lead.name} @ {lead.company} | ${lead.deal_value:,.0f} | {lead.stage}"
    )

    workflow = Workflow(
        name="RevOps Workflow",
        description="Revenue Operations: Intake/Triage → Enrichment → Action Planning → Review",
        session_id=f"{session_id}-{lead.id}",
        steps=_build_steps(tracker, state, interactive=sys.stdin.isatty() if interactive is None else interactive),
        input_schema=Lead,
    )

    workflow.run(input=lead)

    obs = tracker.finalize()
    tracker.log(obs)

    def _dump(obj):
        return obj.model_dump() if obj is not None else None

    return {
        "lead_id": lead.id,
        "lead_name": lead.name,
        "company": lead.company,
        "triage": _dump(state.triage),
        "enriched": _dump(state.enriched),
        "action_plan": _dump(state.action_plan),
        "review": _dump(state.review),
        "human_approval": _dump(state.human_approval),
        "observability": obs.model_dump(),
    }
