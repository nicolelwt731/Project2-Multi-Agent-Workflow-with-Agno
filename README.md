# RevOps Multi-Agent Workflow

A production-style **Revenue Operations automation system** built with [Agno](https://agno.com) Workflows. 4 specialized AI agents form a sequential pipeline that classifies, enriches, plans and reviews sales leads — with a **human-in-the-loop approval breakpoint** for high-stakes deals.

---

## What It Does

Given a raw sales lead (name, company, deal value, stage, notes), the system automatically:

1. **Triages** the lead — urgency, category, workflow lane, priority score
2. **Enriches** it — company profile from mock CRM, risk flags
3. **Plans actions** — 3–5 specific follow-up actions with owners and deadlines
4. **Reviews and approves** — quality gate with escalation decision
5. **🌟Human Approval** — blocking breakpoint when `escalate_to_manager=True` or review rejected; auto-skips otherwise

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
└────────┬────────┘
         │
         ▼
┌─────────────────┐   escalate_to_manager=True  ┌─────────────────────────────┐
│  HumanApproval  │ ─────────────────────────►  │  Blocking stdin prompt      │
│  (HITL Gate)    │   OR review.approved=False   │  y/n + optional comment     │
│                 │ ◄────────────────────────── │  decision stored in result  │
│                 │   auto-skips when not needed └─────────────────────────────┘
└────────┬────────┘
         │
         ▼
Structured JSON + Observability Report
```

**Pattern:** Coordinator → Specialists → Reviewer → Human Gate

**Trigger logic for human approval:**

| Condition | Triggered by | Action |
| --- | --- | --- |
| `escalate_to_manager=True` | High-value deal at critical/high urgency, or at-risk with low health | Blocking prompt |
| `review.approved=False` | Quality score below 0.7 | Blocking prompt |
| Neither | Normal flow | Auto-record `skipped`, continue |
| Non-interactive (UI/tests) | Any escalation | Auto-approve with note |

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
│   │   └── revops_workflow.py    # Agno Workflow: step orchestration, retry, HITL, state
│   ├── models/
│   │   └── schemas.py            # All Pydantic models (Lead → HumanApprovalResult)
│   └── tools/
│       ├── crm_tools.py          # Mock CRM lookup tools
│       └── observability.py      # Latency, token, and error tracking
├── data/
│   └── mock_leads.json           # 4 demo leads covering all pipeline stages
├── demo/
│   ├── run_demo.py               # CLI runner + Agno AgentOS UI server
├── tests/
│   └── test_workflow.py          # 25-test pytest suite
└── requirements.txt
```

---

## Requirements Met

| Requirement | Implementation |
| --- | --- |
| **Multi-Agent Orchestration** | 5-agent sequential pipeline: 1 coordinator (Triage) + 2 specialists (Enrichment, Action) + 1 reviewer (Review) + 1 HITL gate (HumanApproval) |
| **Runnable End-to-End** | `python demo/run_demo.py` — processes leads and returns structured JSON |
| **Typed State** | 11 Pydantic models in `schemas.py`; `WorkflowState` tracks all inter-agent handoffs |
| **Observability** | `ObservabilityTracker`: total latency, per-agent latency, token usage, success/partial/failed status |
| **Resilience — Scenario 1** | Malformed lead input caught before any agent runs; returns `{"error": ...}` cleanly |
| **Resilience — Scenario 2** | LLM/parse failure: `_run_with_retry` retries up to 3× with exponential backoff |
| **Demo UX** | CLI with `rich` formatting + Agno AgentOS UI (`--ui` flag → `app.agno.com`) |

---

## Stretch Goals

| Stretch Goal | Status | Details |
| --- | --- | --- |
| **Human-in-the-Loop** | ✅ Full | Blocking `stdin` prompt in CLI; auto-approve in UI/tests; records `decision`, `comment`, `triggered_by`, `timestamp` in `HumanApprovalResult` |
| **Trace Visualization** | ✅ Full | `ObservabilityTracker` emits per-agent latency (ms), token counts, errors, and workflow status — printed and returned in every run's JSON |
| **Self-Correction Loop** | ⚡ Partial | `_run_with_retry` — 3× retry with 0.3s × attempt backoff on any LLM/parse failure |
| **Evaluation Harness** | ⚡ Partial | `ReviewAgent` scores output on 5 explicit rubric criteria (0–1 scale); `quality_score >= 0.7` required for approval |
| **Parallel Specialists** | — | Not implemented; strict data dependencies make sequential the correct model |

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

All 5 agents use `gpt-4o-mini`.

---

## Running the Demo

### CLI Mode (recommended)

```bash
# Run a single lead (index 0–3)
python demo/run_demo.py --lead 0    # Sarah Chen — $120k negotiation (triggers human approval)
python demo/run_demo.py --lead 1    # Marcus Webb — at_risk, 47 days silent
python demo/run_demo.py --lead 2    # Priya Nair  — renewal + expansion
python demo/run_demo.py --lead 3    # James Okafor — new inbound

# Run all 4 leads back-to-back
python demo/run_demo.py
```

**Example output (Lead 0 — Sarah Chen):**

```text
──────────────── Sarah Chen @ Acme Corp ────────────────

🚀 RevOps [a1b2c3d4] — Sarah Chen @ Acme Corp | $120,000 | negotiation
  ✅ Triage → CRITICAL | new_business | lane=accelerate | score=9/10
  ✅ Enrichment → enterprise | health=72% | flags=['large_deal_stalled']
  ✅ Actions → 4 actions | close_prob=65%
     Next: Schedule executive alignment call with VP of Ops this week
  ✅ APPROVED | quality=85% 🚨 ESCALATE

  ========================================================
  ⚠️  HUMAN APPROVAL REQUIRED
  ========================================================
  Lead     : Sarah Chen @ Acme Corp
  Reason   : escalate_to_manager=True
  Quality  : 85%  |  Feedback: Plan is specific and appropriately urgent.
  ========================================================

  Approve? [y/n] (optional comment after space): y ship it — AE to call VP Monday

  ✅ Human Approval → APPROVED — ship it — AE to call VP Monday

============================================================
  OBSERVABILITY REPORT  [a1b2c3d4]
  Status        : SUCCESS
  Total latency : 5,312.4 ms
  TriageAgent          1,203 ms     312 tokens
  EnrichmentAgent      1,544 ms     498 tokens
  ActionAgent          1,103 ms     421 tokens
  ReviewAgent            971 ms     287 tokens
============================================================
```

**Example output (Lead 1 — Marcus Webb, no escalation):**

```text
  ✅ Human Approval → skipped (no escalation required)
```

### Agno AgentOS UI Mode

```bash
python demo/run_demo.py --ui
```

Then open [app.agno.com](https://app.agno.com) → Playground → Workflows → connect endpoint `localhost:7777`.

In UI mode the `HumanApproval` step auto-approves (non-interactive) and logs the decision.

---

## Demo Scenarios
**Quick reference:**

| Lead | Deal | Stage | Expected outcome |
| --- | --- | --- | --- |
| `--lead 0` Sarah Chen | $120k | negotiation | CRITICAL · accelerate · human approval triggered |
| `--lead 1` Marcus Webb | $45k | at_risk | HIGH · retain · approval skipped |
| `--lead 2` Priya Nair | $78k | renewal | HIGH · renew · depends on health score |
| `--lead 3` James Okafor | $22k | prospecting | LOW/MEDIUM · qualify · approval skipped |

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

**25 tests** across 6 classes:

| Class | Tests | Coverage |
| --- | --- | --- |
| `TestSchemas` | 4 | Pydantic validation and field bounds |
| `TestCRMTools` | 4 | CRM lookup happy path and fallback |
| `TestObservability` | 3 | Latency tracking, error status |
| `TestFailureScenarios` | 2 | Invalid input, retry exhaustion |
| `TestHumanApprovalStep` | 5 | skipped, auto-approved, review_rejected, interactive approve/reject |
| `TestWorkflowExecution` | 2 | End-to-end with mocked agents |
| `TestPlaygroundCompatRoutes` | 5 | FastAPI routes, streaming, fallback input |

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

## Key Design Decisions

**Why a blocking `input()` instead of an async approval queue?**
For a CLI demo, synchronous `stdin` is the simplest, most legible human-in-the-loop pattern. The `interactive` flag (auto-detected via `sys.stdin.isatty()`, overridable) means the same step works in tests, UI, and live CLI without branching the workflow logic.

**Why sequential steps vs. a team?**
The RevOps pipeline has strict data dependencies — each agent builds on the previous agent's output. A sequential `Workflow` with `Steps` models this more clearly than a parallel team, and makes the data flow explicit and debuggable.

**Why a shared `WorkflowState`?**
A single typed `WorkflowState` object (not a stringly-typed dict) makes inter-agent handoffs type-safe and easy to inspect. It also allows the UI mode to safely reset state between runs without reconstructing the workflow object.

---

## How I Worked With AI

- **Primary tool: Claude Code with the Octopus plugin** — Octopus lets Claude, Gemini, and GPT simultaneously debate a design question or problem, essentially turning multiple LLMs into a panel of opinionated agents. I used it heavily during architecture and design phases.
- **Framework scaffolding was where AI sped me up the most** — standing up the Agno Workflow skeleton, wiring Pydantic models across five agents, and writing the `ObservabilityTracker` boilerplate all came together in a fraction of the time it would have taken manually.
- **Debugging was the other major time-save** — tracing why steps silently returned `None`, fixing retry-backoff math, and resolving FastAPI route conflicts were all substantially faster with AI assistance surfacing root causes quickly.
- **I spent more time *thinking with* the AI than prompting it to write code** — the most valuable sessions were structured debates between Claude, Gemini, and GPT on questions like "sequential steps vs. parallel team" and "blocking stdin vs. async approval queue." The multi-LLM disagreements helped me stress-test assumptions before writing a line of code.
- **Human-in-the-loop approval was the hardest feature for AI to get right** — early AI-generated implementations either blocked unconditionally (breaking UI/test mode) or skipped the prompt entirely. Getting the `sys.stdin.isatty()` auto-detection plus the `interactive` override flag to behave correctly across CLI, tests, and Agno AgentOS required several correction rounds.
- **The `interactive` flag logic needed manual redesign** — AI suggestions conflated non-interactive detection with the escalation trigger, causing the approval step to silently no-op in cases where it should have prompted. I rewrote the conditional logic and added the `triggered_by` field to the result model myself after the AI-generated versions kept regressing.
- **Agno AgentOS UI integration was a personal stretch goal I did not fully land** — I attempted to surface the workflow as a proper interactive UI model on the Agno Playground, but the session-state and streaming contract between the FastAPI layer and `app.agno.com` needs more investigation. The `--ui` flag and the `TestPlaygroundCompatRoutes` suite represent the current state; the fully interactive UI remains a work in progress.
- **Test coverage was partly AI-generated, partly hand-corrected** — AI produced the test class stubs quickly, but mock patching paths (`app.workflows.revops_workflow.input`) and the `TestPlaygroundCompatRoutes` async streaming tests needed manual fixes to match the actual module structure.
- **One area where AI was confidently wrong: Agno API surface** — several generated code snippets referenced Agno methods that don't exist in 2.5.x (e.g., a `Workflow.run_step()` shorthand). I caught these by reading the Agno source and corrected them before they became runtime errors.

---

