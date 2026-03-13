import json

from agno.agent import Agent
from agno.models.openai import OpenAIChat

from app.tools.crm_tools import lookup_company, get_lead_history

ENRICHMENT_INSTRUCTIONS = """\
You are a Revenue Operations Data Enrichment Specialist.

You receive a JSON object with:
  - triage: urgency/category/coordination output from intake
  - specialist_brief: routing brief for downstream specialists
  - company_crm_data: CRM record for the company
  - lead_history: past interaction notes
  - lead_notes: notes from the lead record
  - last_contact_days: days since last contact
  - deal_value: deal size in USD
  - stage: current pipeline stage

Return ONLY a JSON object with exactly these two keys:

{
  "company_profile": {
    "company_size": <"enterprise"|"mid_market"|"smb"|"startup">,
    "employee_count": <integer>,
    "annual_revenue_usd": <float>,
    "industry": <string>,
    "health_score": <float 0.0-1.0>,
    "recent_activity": [<string>, ...]
  },
  "risk_flags": [<string>, ...]
}

For risk_flags include any that apply:
  - "no_recent_contact" if last_contact_days > 21
  - "low_health_score" if health_score < 0.5
  - "at_risk_stage" if stage = at_risk
  - "large_deal_stalled" if deal_value > 50000 and stage not advancing
  - "champion_risk" if lead_history mentions executive departure

No extra text, no markdown. Only the JSON object.
"""


def create_enrichment_agent() -> Agent:
    return Agent(
        name="EnrichmentAgent",
        model=OpenAIChat(id="gpt-4o-mini"),
        instructions=ENRICHMENT_INSTRUCTIONS,
        use_json_mode=True,
    )


def build_enrichment_prompt(lead_dict: dict, triage_dict: dict) -> str:
    company_data = lookup_company(lead_dict.get("company", ""))
    history = get_lead_history(lead_dict.get("id", ""))
    payload = {
        "triage": triage_dict,
        "specialist_brief": triage_dict.get("specialist_brief", ""),
        "company_crm_data": company_data,
        "lead_history": history,
        "lead_notes": lead_dict.get("notes", ""),
        "last_contact_days": lead_dict.get("last_contact_days", 0),
        "deal_value": lead_dict.get("deal_value", 0),
        "stage": lead_dict.get("stage", ""),
    }
    return json.dumps(payload, indent=2)
