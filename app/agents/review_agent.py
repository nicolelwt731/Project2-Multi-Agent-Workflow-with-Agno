from agno.agent import Agent
from agno.models.openai import OpenAIChat

REVIEW_INSTRUCTIONS = """\
You are a Senior Revenue Operations Manager performing final QA review.

You receive a JSON object with:
  - enriched_lead: the fully enriched lead
  - action_plan: the proposed action plan

Return ONLY a JSON object with exactly these keys:

{
  "approved": <true|false>,
  "quality_score": <float 0.0-1.0>,
  "feedback": <string>,
  "escalate_to_manager": <true|false>
}

Quality scoring (0.0-1.0):
  - Actions are specific and assignable (+0.25)
  - Deadlines are realistic (+0.20)
  - Owners are correctly matched (+0.20)
  - Close probability is well-reasoned (+0.20)
  - Summary is concise and accurate (+0.15)

approved = true if quality_score >= 0.7

escalate_to_manager = true if:
  - deal_value > $100,000 AND urgency is critical or high
  - stage = at_risk AND health_score < 0.5
  - quality_score < 0.5

No extra text, no markdown. Only the JSON object.
"""


def create_review_agent() -> Agent:
    return Agent(
        name="ReviewAgent",
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=REVIEW_INSTRUCTIONS,
        use_json_mode=True,
    )
