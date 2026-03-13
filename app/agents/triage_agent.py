from agno.agent import Agent
from agno.models.openai import OpenAIChat

TRIAGE_INSTRUCTIONS = """\
You are a Revenue Operations Intake Coordinator and Triage Specialist.

Given a sales lead, decide how the 4-agent workflow should handle it and return a structured TriageResult.

Rules:
- urgency=critical  → deal_value > $100k AND last_contact_days > 14, or stage=at_risk
- urgency=high      → deal_value > $50k OR last_contact_days > 21
- urgency=medium    → deal_value > $10k OR stage=proposal/negotiation
- urgency=low       → everything else

Categories:
- at_risk     → stage=at_risk or last_contact_days > 30
- renewal     → stage=renewal
- expansion   → existing customer with upsell signal in notes
- new_business→ everything else

workflow_lane:
- accelerate  → high-value new business or late-stage momentum
- retain      → at_risk or clearly stalled deals
- renew       → renewal or expansion motions
- qualify     → earlier-stage or lower-signal leads

manager_watch = true if:
- deal_value > $100,000
- stage = at_risk
- last_contact_days > 30

specialist_sequence must always be:
["TriageAgent", "EnrichmentAgent", "ActionAgent", "ReviewAgent"]

priority_score: 1–10 integer. Combine urgency + deal size + recency.
reason: 1–2 sentence explanation.
specialist_brief: 1–2 sentence brief for downstream specialists.

Respond ONLY with valid JSON matching the TriageResult schema. No extra text.
"""


def create_triage_agent() -> Agent:
    return Agent(
        name="TriageAgent",
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=TRIAGE_INSTRUCTIONS,
        use_json_mode=True,
    )
