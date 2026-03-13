"""Mock CRM database tools used by EnrichmentAgent."""

from __future__ import annotations

_MOCK_COMPANY_DB: dict = {
    "acme corp": {
        "company_size": "enterprise",
        "employee_count": 5000,
        "annual_revenue_usd": 500_000_000,
        "industry": "Manufacturing",
        "health_score": 0.72,
        "recent_activity": [
            "Attended product webinar 2 weeks ago",
            "Opened 3 of last 5 marketing emails",
            "Support ticket closed 10 days ago",
        ],
    },
    "globex": {
        "company_size": "mid_market",
        "employee_count": 800,
        "annual_revenue_usd": 80_000_000,
        "industry": "Technology",
        "health_score": 0.55,
        "recent_activity": [
            "No login in 45 days",
            "Downgraded plan last quarter",
            "NPS score: 5",
        ],
    },
    "initech": {
        "company_size": "smb",
        "employee_count": 120,
        "annual_revenue_usd": 8_000_000,
        "industry": "Finance",
        "health_score": 0.88,
        "recent_activity": [
            "Upsell conversation last week",
            "Champions just promoted",
            "High DAU growth (+30% MoM)",
        ],
    },
    "umbrella ltd": {
        "company_size": "startup",
        "employee_count": 35,
        "annual_revenue_usd": 1_200_000,
        "industry": "Healthcare",
        "health_score": 0.40,
        "recent_activity": [
            "CEO left company",
            "Missed last two QBRs",
            "Contract renewal in 30 days",
        ],
    },
}


def lookup_company(company_name: str) -> dict:
    """Return enrichment data for a company from the mock CRM."""
    key = company_name.lower().strip()
    for db_key, data in _MOCK_COMPANY_DB.items():
        if db_key in key or key in db_key:
            return data
    # Default for unknown companies
    return {
        "company_size": "smb",
        "employee_count": 50,
        "annual_revenue_usd": 2_000_000,
        "industry": "Unknown",
        "health_score": 0.60,
        "recent_activity": ["No historical data available"],
    }


def get_lead_history(lead_id: str) -> list[str]:
    """Return past interaction notes for a lead."""
    history_db = {
        "lead-001": ["Demo call completed", "Proposal sent 2 weeks ago", "Waiting on legal review"],
        "lead-002": ["Trial started 60 days ago", "No usage logged", "3 unanswered follow-ups"],
        "lead-003": ["Long-time customer", "Expansion opportunity discussed", "Strong champion"],
        "lead-004": ["New inbound lead", "High-intent demo request", "Budget confirmed"],
    }
    return history_db.get(lead_id, ["No prior history found"])
