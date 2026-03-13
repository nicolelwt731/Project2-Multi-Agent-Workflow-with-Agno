# Take-Home Exercise: AI-Native Multi-Agent Workflow with Agno

## Objective
Build a practical multi-agent system using **Agno Workflows or Teams** to automate a realistic business or operational workflow.

This exercise is intentionally designed for **AI-native / vibe-coding development**. You are encouraged to use AI-assisted tools as much as possible—such as Codex, Claude Code, Cursor, Antigravity, Copilot, or similar tools—so long as you can explain your design choices, debug issues, and defend the final system.

**Your goal is not to avoid AI. Your goal is to use AI effectively to ship a solid working system.**

---

## Choose One Track
Pick **one** of the following:

### Option A — Browser Automation Multi-Agent
Build a team that completes a browser-based task on a public website and returns structured results.
* **Possible examples:**
  * Search and extract top results from a public directory
  * Navigate a multi-step public workflow
  * Collect structured information across several pages
* **Suggested team:** Planner Agent, Browser Agent, Extraction Agent, Verifier Agent

### Option B — Marketing Team
Build a team that turns a simple product brief into a set of usable marketing assets.
* **Possible examples:**
  * Landing page copy
  * Launch email sequence
  * Ad concepts
  * Social content calendar
* **Suggested team:** Strategist Agent, Research Agent, Copywriter Agent, Editor/QA Agent

### Option C — Investment Team
Build a team that researches and evaluates a small set of companies, sectors, or opportunities and produces a recommendation memo.
* **Possible examples:**
  * Compare 3 AI startups in a niche
  * Compare 3 public companies in a sector
  * Create a short investment memo with risks and open questions
* **Suggested team:** Research Agent, Analyst Agent, Critic/Risk Agent, Decision Agent

### Option D — Operators Team (Recommended: Revenue Operations)
Build a team that helps an operator prioritize work and recommend actions.
* **Possible examples:**
  * Prioritize leads or accounts
  * Flag at-risk pipeline opportunities
  * Recommend follow-up actions
  * Summarize account notes into an operator dashboard
* **Suggested team:** Intake Agent, Classification/Enrichment Agent, Action Agent, Review/Manager Agent

---

## Core Requirements

### 1. Multi-Agent Orchestration
Your system must use a real multi-agent pattern, not just one agent with a long prompt. You should have at least:
* 1 coordinating agent
* 2 specialist agents
* 1 output/review step

*Examples of acceptable patterns:*
* Planner → Specialists → Reviewer
* Hierarchical Coordinator + Workers
* Generator → Critic → Revision
* Router → Specialist Agents → Aggregator

### 2. Runnable End-to-End Workflow
The system should be runnable locally and produce a real output for your chosen track (e.g., structured JSON, markdown report, CSV of ranked results, generated campaign package, investment memo, prioritized ops action list).

### 3. Typed State and Clean Interfaces
Use strongly typed objects for agent inputs/outputs and workflow state. Avoid “stringly typed” handoffs wherever possible.
* Pydantic models
* Typed dataclasses
* Explicit schemas for handoffs

### 4. Observability and Instrumentation
Track at least:
* Total workflow latency
* Per-agent latency
* Token usage, if available
* Success/failure status
*(A simple logging table or structured JSON log is sufficient).*

### 5. Resilience
Include at least **two** failure-handling scenarios.
*Examples: Malformed user input, missing or partial source data, transient LLM/tool failure with retry, browser/navigation failure, invalid structured output that triggers repair/retry.*

### 6. Demo UX
Provide a basic way to run and inspect the workflow.
* **Preferred:** Agno Agent OS UI (show the team execution clearly)
* **Acceptable fallback:** CLI + readable logs, minimal web UI, or a notebook with reproducible run steps

---

## Strong Hint on Implementation
**Do not overbuild this.** Simple, working, and well-explained beats ambitious but broken. A good submission can be:
* A small but clean Agno workflow
* 4 agents
* 2–4 tools
* Typed state
* Basic retries
* One good demo scenario
* One or two focused tests

---

## Suggested Project Structure
```text
repo/
├── README.md
├── app/
│   ├── agents/
│   ├── workflows/
│   ├── models/
│   └── tools/
├── tests/
├── data/ (or examples/)
└── demo/
