from __future__ import annotations

from typing import Dict, List, Literal, Optional
from pydantic import BaseModel, Field


# ─── Input ────────────────────────────────────────────────────────────────────

class Lead(BaseModel):
    id: str
    name: str
    company: str
    email: str
    deal_value: float = Field(ge=0, description="Deal value in USD")
    stage: Literal[
        "prospecting", "qualification", "proposal",
        "negotiation", "at_risk", "renewal", "closed_won", "closed_lost"
    ]
    last_contact_days: int = Field(ge=0, description="Days since last contact")
    notes: str = ""
    industry: Optional[str] = None


# ─── Triage ───────────────────────────────────────────────────────────────────

class TriageResult(BaseModel):
    lead_id: str
    urgency: Literal["critical", "high", "medium", "low"]
    category: Literal["new_business", "expansion", "at_risk", "renewal"]
    priority_score: int = Field(ge=1, le=10, description="1 = low, 10 = critical")
    reason: str
    workflow_lane: Literal["accelerate", "retain", "renew", "qualify"] = "qualify"
    manager_watch: bool = False
    specialist_sequence: List[Literal["TriageAgent", "EnrichmentAgent", "ActionAgent", "ReviewAgent"]] = Field(
        default_factory=lambda: ["TriageAgent", "EnrichmentAgent", "ActionAgent", "ReviewAgent"]
    )
    specialist_brief: str = ""


# ─── Enrichment ───────────────────────────────────────────────────────────────

class CompanyProfile(BaseModel):
    company_size: Literal["enterprise", "mid_market", "smb", "startup"]
    employee_count: int
    annual_revenue_usd: float
    industry: str
    health_score: float = Field(ge=0.0, le=1.0, description="0=churned, 1=healthy")
    recent_activity: List[str]


class EnrichedLead(BaseModel):
    lead: Lead
    triage: TriageResult
    company_profile: CompanyProfile
    risk_flags: List[str]


# ─── Action Plan ──────────────────────────────────────────────────────────────

class ActionItem(BaseModel):
    action: str
    owner: Literal["ae", "csm", "manager", "marketing"]
    due_in_days: int
    priority: Literal["urgent", "high", "normal"]


class ActionPlan(BaseModel):
    lead_id: str
    summary: str
    recommended_actions: List[ActionItem]
    estimated_close_probability: float = Field(ge=0.0, le=1.0)
    next_best_action: str


# ─── Review Output ────────────────────────────────────────────────────────────

class ReviewOutput(BaseModel):
    lead_id: str
    approved: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    feedback: str
    final_action_plan: ActionPlan
    escalate_to_manager: bool


# ─── LLM output sub-schemas (what each agent actually generates) ──────────────

class EnrichmentOutput(BaseModel):
    """What the EnrichmentAgent LLM returns — assembled into EnrichedLead in code."""
    company_profile: CompanyProfile
    risk_flags: List[str]


class ReviewDecision(BaseModel):
    """What the ReviewAgent LLM returns — assembled into ReviewOutput in code."""
    approved: bool
    quality_score: float = Field(ge=0.0, le=1.0)
    feedback: str
    escalate_to_manager: bool


# ─── Observability ────────────────────────────────────────────────────────────

class WorkflowObservability(BaseModel):
    workflow_id: str
    lead_id: str
    total_latency_ms: float
    per_agent_latency_ms: Dict[str, float]
    token_usage: Dict[str, int]
    status: Literal["success", "failed", "partial"]
    errors: List[str]
    timestamp: str


class WorkflowState(BaseModel):
    lead: Optional[Lead] = None
    triage: Optional[TriageResult] = None
    enriched: Optional[EnrichedLead] = None
    action_plan: Optional[ActionPlan] = None
    review: Optional[ReviewOutput] = None

    def start_run(self, lead: Lead) -> None:
        self.lead = lead
        self.triage = None
        self.enriched = None
        self.action_plan = None
        self.review = None
