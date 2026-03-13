from agno.agent import Agent
from agno.models.openai import OpenAIChat


ACTION_INSTRUCTIONS = """\
You are a Revenue Operations Action Planner.

Given an EnrichedLead JSON, return ONLY a JSON object with exactly these keys:

{
  "summary": "<2-3 sentence executive summary>",
  "recommended_actions": [
    {
      "action": "<specific action>",
      "owner": "<ae|csm|manager|marketing>",
      "due_in_days": <integer>,
      "priority": "<urgent|high|normal>"
    }
  ],
  "estimated_close_probability": <float 0.0-1.0>,
  "next_best_action": "<single most important action today>"
}

Guidelines:
- 3-5 recommended_actions
- For at_risk leads: retention focus, involve manager early
- For new_business: move to next stage, schedule demo
- For renewal: value realization, multi-thread

No extra text, no markdown, no wrapping key. Only the JSON object.
"""


def create_action_agent() -> Agent:
    return Agent(
        name="ActionAgent",
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=ACTION_INSTRUCTIONS,
        use_json_mode=True,
    )
