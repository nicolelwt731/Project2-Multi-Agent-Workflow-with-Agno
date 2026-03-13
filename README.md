# RevOps Multi-Agent Workflow

A production-style **Revenue Operations automation system** built with [Agno](https://agno.com) Workflows. Four specialized AI agents form a sequential pipeline that classifies, enriches, plans, and reviews sales leads — end-to-end in seconds.

---

## What It Does

Given a raw sales lead (name, company, deal value, stage, notes), the system automatically:

1. **Triages** the lead — urgency, category, workflow lane, priority score
2. **Enriches** it — company profile from mock CRM, risk flags
3. **Plans actions** — 3–5 specific follow-up actions with owners and deadlines
4. **Reviews and approves** — quality gate with escalation decision

Every run produces structured JSON output and a full observability report (latency, tokens, status).

---

## Architecture

```text
Lead Input (JSON)
      │
      ▼
┌─────────────────┐
│  TriageAgent    │  Classifies urgency, category, workflow lane
│  (Coordinator)  │  Decides if manager watch is needed
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ EnrichmentAgent │  Pulls CRM data, detects risk flags
│  (Specialist)   │  (no_recent_contact, low_health_score, etc.)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ActionAgent    │  Generates 3–5 prioritized actions
│  (Specialist)   │  Assigns owners (ae/csm/manager/marketing)
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  ReviewAgent    │  QA gate: quality score, approve/reject,
│  (Output/QA)    │  escalate_to_manager flag
└─────────────────┘
         │
         ▼
Structured JSON + Observability Report
```

**Pattern:** Coordinator → Specialists → Reviewer (matching the assignment's recommended Operators Team pattern)

---

## Project Structure

```text
repo/
├── app/
│   ├── agents/
│   │   ├── triage_agent.py       # Lead intake coordinator
│   │   ├── enrichment_agent.py   # CRM data enrichment specialist
│   │   ├── action_agent.py       # Action planning specialist
│   │   └── review_agent.py       # QA review / final gate
│   ├── workflows/
│   │   └── revops_workflow.py    # Agno Workflow: step orchestration, retry, state
│   ├── models/
│   │   └── schemas.py            # All Pydantic models (Lead, TriageResult, etc.)
│   └── tools/
│       ├── crm_tools.py          # Mock CRM lookup tools
│       └── observability.py      # Latency, token, and error tracking
├── data/
│   └── mock_leads.json           # 4 demo leads covering all pipeline stages
├── demo/
│   └── run_demo.py               # CLI runner + Agno AgentOS UI server
├── tests/
│   └── test_workflow.py          # Pytest suite
└── requirements.txt
```

---

## Requirements Met

| Requirement | Implementation |
| --- | --- |
| **Multi-Agent Orchestration** | 4-agent sequential pipeline: 1 coordinator (Triage) + 2 specialists (Enrichment, Action) + 1 reviewer (Review) |
| **Runnable End-to-End** | `python demo/run_demo.py` — processes leads and returns structured JSON |
| **Typed State** | 10 Pydantic models in `schemas.py`; `WorkflowState` tracks all inter-agent handoffs |
| **Observability** | `ObservabilityTracker`: total latency, per-agent latency, token usage, success/partial/failed status |
| **Resilience — Scenario 1** | Malformed lead input caught before any agent runs; returns `{"error": ...}` cleanly |
| **Resilience — Scenario 2** | LLM/parse failure: `_run_with_retry` retries up to 3× with exponential backoff |
| **Demo UX** | CLI with `rich` formatting + Agno AgentOS UI (`--ui` flag → `app.agno.com`) |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone <repo-url>
cd Project2-Multi-Agent-Workflow-with-Agno
pip install -r requirements.txt
```

### 2. Set your OpenAI API key

```bash
export OPENAI_API_KEY=sk-...
```

All 4 agents use `gpt-4o-mini`.

---

## Running the Demo

### CLI Mode (recommended)

```bash
# Run a single lead (index 0–3)
python demo/run_demo.py --lead 0    # Sarah Chen — $120k negotiation (high-value)
python demo/run_demo.py --lead 1    # Marcus Webb — at_risk, 47 days silent
python demo/run_demo.py --lead 2    # Priya Nair  — renewal + expansion
python demo/run_demo.py --lead 3    # James Okafor — new inbound

# Run all 4 leads back-to-back
python demo/run_demo.py
```

**Example output:**

```text
──────────────── Sarah Chen @ Acme Corp ────────────────

🚀 RevOps [a1b2c3d4] — Sarah Chen @ Acme Corp | $120,000 | negotiation
  ✅ Triage → CRITICAL | new_business | lane=accelerate | score=9/10
  ✅ Enrichment → enterprise | health=72% | flags=['large_deal_stalled']
  ✅ Actions → 4 actions | close_prob=65%
     Next: Schedule executive alignment call with VP of Ops this week
  ✅ APPROVED | quality=85% 🚨 ESCALATE

============================================================
  OBSERVABILITY REPORT  [a1b2c3d4]
  Status        : SUCCESS
  Total latency : 4821.3 ms
  TriageAgent          1203.4 ms     312 tokens
  EnrichmentAgent      1544.1 ms     498 tokens
  ActionAgent          1102.8 ms     421 tokens
  ReviewAgent           970.6 ms     287 tokens
============================================================
```

### Agno AgentOS UI Mode

```bash
python demo/run_demo.py --ui
```

Then open [app.agno.com](https://app.agno.com) → Playground → Workflows → connect endpoint `localhost:7777`.

Paste a lead JSON in the input field to run the pipeline interactively.

---

## Demo Scenarios

Two leads are designed for a compelling side-by-side demo:

**Lead 1 — High-value, late-stage** (`--lead 0`)

```json
{"id":"lead-001","name":"Sarah Chen","company":"Acme Corp",
 "deal_value":120000,"stage":"negotiation","last_contact_days":18,
 "notes":"Legal is reviewing MSA. Champion is VP of Ops.",
 "email":"s.chen@acmecorp.com","industry":"Manufacturing"}
```

Expected: CRITICAL urgency, `accelerate` lane, manager escalation, 4+ actions

**Lead 2 — At-risk, silent** (`--lead 1`)

```json
{"id":"lead-002","name":"Marcus Webb","company":"Globex",
 "deal_value":45000,"stage":"at_risk","last_contact_days":47,
 "notes":"Usage dropped 60% last month. No response to 3 follow-ups.",
 "email":"m.webb@globex.io","industry":"Technology"}
```

Expected: `retain` lane, multiple risk flags, retention-focused actions

---

## Resilience Demo

**Failure Scenario 1 — Invalid input** (caught before any agent runs):

```bash
python -c "
from app.workflows.revops_workflow import run_revops
print(run_revops({'id': 'bad', 'name': 'Test'}))  # missing required fields
"
# → {"error": "Invalid lead data: ...", "lead_id": "bad"}
```

**Failure Scenario 2 — LLM retry** is automatic. If an agent returns malformed JSON or a transient error occurs, `_run_with_retry` retries up to 3 times with 0.3s × attempt backoff. Each attempt is logged to the observability report.

---

## Running Tests

```bash
pytest tests/ -v
```

Tests cover: schema validation, triage logic, enrichment, action planning, review, observability, and end-to-end workflow.

---

## Key Design Decisions

**Why sequential steps vs. a team?**
The RevOps pipeline has strict data dependencies — each agent builds on the previous agent's output. A sequential `Workflow` with `Steps` models this more clearly than a parallel team, and makes the data flow explicit and debuggable.

**Why `gpt-4o-mini` for all agents?**
The task is JSON extraction from structured prompts — `gpt-4o-mini` is fast, cheap, and reliable for this pattern. All agents use `use_json_mode=True` to enforce structured output.

**Why a shared `WorkflowState`?**
A single typed `WorkflowState` object (not a stringly-typed dict) makes inter-agent handoffs type-safe and easy to inspect. It also allows the UI mode to safely reset state between runs without reconstructing the workflow object.

---

## Tech Stack

| Component | Library |
| --- | --- |
| Agent framework | [Agno](https://agno.com) 2.5.x |
| LLM | OpenAI `gpt-4o-mini` |
| Typed schemas | Pydantic v2 |
| UI server | FastAPI + Uvicorn |
| CLI output | Rich |
| Tests | Pytest |
