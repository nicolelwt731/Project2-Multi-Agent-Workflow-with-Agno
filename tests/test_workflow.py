"""Tests for the RevOps multi-agent workflow."""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from agno.workflow import StepInput
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).parents[1]))

from app.models.schemas import (
    ActionItem, ActionPlan, CompanyProfile, Lead, ReviewDecision,
    ReviewOutput, TriageResult,
)
from app.tools.crm_tools import get_lead_history, lookup_company
from app.tools.observability import ObservabilityTracker


# ─── Schema validation ────────────────────────────────────────────────────────

class TestSchemas:
    def test_lead_valid(self):
        lead = Lead(
            id="test-001", name="Alice", company="TestCo",
            email="alice@test.com", deal_value=50000,
            stage="proposal", last_contact_days=7,
        )
        assert lead.deal_value == 50000

    def test_lead_invalid_stage(self):
        with pytest.raises(Exception):
            Lead(
                id="bad", name="X", company="Y", email="x@y.com",
                deal_value=0, stage="invalid_stage", last_contact_days=0,
            )

    def test_triage_result_score_bounds(self):
        with pytest.raises(Exception):
            TriageResult(
                lead_id="x", urgency="high", category="new_business",
                priority_score=11,  # out of 1-10
                reason="test",
            )

    def test_review_output_quality_bounds(self):
        plan = ActionPlan(
            lead_id="x", summary="s", recommended_actions=[],
            estimated_close_probability=0.5, next_best_action="call",
        )
        with pytest.raises(Exception):
            ReviewOutput(
                lead_id="x", approved=True, quality_score=1.5,  # > 1.0
                feedback="ok", final_action_plan=plan, escalate_to_manager=False,
            )


# ─── CRM tools ────────────────────────────────────────────────────────────────

class TestCRMTools:
    def test_lookup_known_company(self):
        result = lookup_company("Acme Corp")
        assert result["company_size"] == "enterprise"
        assert result["health_score"] == 0.72

    def test_lookup_unknown_company_returns_default(self):
        result = lookup_company("Unknown Startup XYZ 999")
        assert "company_size" in result
        assert "health_score" in result

    def test_get_lead_history_known(self):
        history = get_lead_history("lead-001")
        assert len(history) > 0

    def test_get_lead_history_unknown(self):
        history = get_lead_history("lead-999")
        assert "No prior history found" in history[0]


# ─── Observability ────────────────────────────────────────────────────────────

class TestObservability:
    def test_tracker_records_latency(self):
        import time
        tracker = ObservabilityTracker(lead_id="test-001")
        tracker.agent_start("TriageAgent")
        time.sleep(0.01)
        tracker.agent_end("TriageAgent", tokens=150)
        obs = tracker.finalize()
        assert "TriageAgent" in obs.per_agent_latency_ms
        assert obs.per_agent_latency_ms["TriageAgent"] >= 10
        assert obs.token_usage["TriageAgent"] == 150

    def test_tracker_error_sets_failed_status(self):
        tracker = ObservabilityTracker(lead_id="test-002")
        tracker.record_error("Something went wrong")
        obs = tracker.finalize()
        assert obs.status == "failed"
        assert len(obs.errors) == 1

    def test_tracker_partial_status_when_some_agents_ran(self):
        import time
        tracker = ObservabilityTracker(lead_id="test-003")
        tracker.agent_start("TriageAgent")
        time.sleep(0.001)
        tracker.agent_end("TriageAgent")
        tracker.record_error("EnrichmentAgent failed")
        obs = tracker.finalize()
        assert obs.status == "partial"


# ─── Failure scenarios ────────────────────────────────────────────────────────

class TestFailureScenarios:
    def test_failure_scenario_1_invalid_lead_returns_error(self):
        """Malformed input is caught before any agent runs."""
        from app.workflows.revops_workflow import run_revops

        bad_lead = {"id": "x", "name": "Incomplete"}  # missing required fields
        result = run_revops(bad_lead)
        assert "error" in result
        assert "Invalid lead data" in result["error"]

    def test_failure_scenario_2_retry_exhaustion_raises(self):
        """_run_with_retry raises RuntimeError after MAX_RETRIES failures."""
        from app.workflows.revops_workflow import _run_with_retry

        tracker = ObservabilityTracker(lead_id="retry-test")
        mock_agent = MagicMock()
        mock_agent.run.side_effect = Exception("LLM timeout")

        with pytest.raises(RuntimeError, match="failed after"):
            _run_with_retry(mock_agent, "prompt", TriageResult, "TriageAgent", tracker)

        assert any("TriageAgent" in e for e in tracker.errors)
        assert mock_agent.run.call_count == 3  # MAX_RETRIES


# ─── Workflow execution ───────────────────────────────────────────────────────

class TestWorkflowExecution:
    def test_build_revops_workflow_uses_runtime_input(self, monkeypatch):
        from app.workflows.revops_workflow import build_revops_workflow

        lead = Lead(
            id="lead-ui",
            name="Runtime User",
            company="Runtime Corp",
            email="runtime@example.com",
            deal_value=75000,
            stage="proposal",
            last_contact_days=9,
            notes="Needs quick follow-up",
        )
        captured = {}

        monkeypatch.setattr("app.workflows.revops_workflow.create_triage_agent", lambda: object())

        def fake_run_with_retry(agent, prompt, schema, agent_name, tracker, inject=None):
            captured["prompt"] = prompt
            tracker.agent_start(agent_name)
            time.sleep(0.001)
            tracker.agent_end(agent_name, tokens=42)
            return TriageResult(
                lead_id=lead.id,
                urgency="high",
                category="new_business",
                priority_score=8,
                reason="High-value active opportunity",
                workflow_lane="accelerate",
                manager_watch=False,
                specialist_brief="Move quickly and confirm next meeting.",
            )

        monkeypatch.setattr("app.workflows.revops_workflow._run_with_retry", fake_run_with_retry)

        workflow = build_revops_workflow()
        output = workflow.steps[0].executor(StepInput(input=lead))
        triage = TriageResult.model_validate_json(output.content)

        assert "Runtime User" in captured["prompt"]
        assert "ui-placeholder" not in captured["prompt"]
        assert triage.lead_id == "lead-ui"
        assert triage.workflow_lane == "accelerate"

    def test_run_revops_returns_complete_result_with_mocked_agents(self, monkeypatch):
        from app.workflows.revops_workflow import run_revops

        lead_data = {
            "id": "lead-001",
            "name": "Sarah Chen",
            "company": "Acme Corp",
            "email": "s.chen@acmecorp.com",
            "deal_value": 120000,
            "stage": "negotiation",
            "last_contact_days": 18,
            "notes": "Legal is reviewing MSA. Champion is VP of Ops.",
            "industry": "Manufacturing",
        }

        monkeypatch.setattr("app.workflows.revops_workflow.create_triage_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_enrichment_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_action_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_review_agent", lambda: object())

        def fake_run_with_retry(agent, prompt, schema, agent_name, tracker, inject=None):
            tracker.agent_start(agent_name)
            time.sleep(0.001)
            tracker.agent_end(agent_name, tokens=50)

            if agent_name == "TriageAgent":
                return TriageResult(
                    lead_id="lead-001",
                    urgency="critical",
                    category="new_business",
                    priority_score=9,
                    reason="Large late-stage deal needs coordination.",
                    workflow_lane="accelerate",
                    manager_watch=True,
                    specialist_brief="Protect deal momentum and unblock legal.",
                )

            if agent_name == "EnrichmentAgent":
                return schema(
                    company_profile=CompanyProfile(
                        company_size="enterprise",
                        employee_count=5000,
                        annual_revenue_usd=500_000_000,
                        industry="Manufacturing",
                        health_score=0.72,
                        recent_activity=["Attended product webinar 2 weeks ago"],
                    ),
                    risk_flags=["large_deal_stalled"],
                )

            if agent_name == "ActionAgent":
                return ActionPlan(
                    lead_id="lead-001",
                    summary="Large strategic opportunity with active legal review.",
                    recommended_actions=[
                        ActionItem(
                            action="Schedule legal unblock call",
                            owner="ae",
                            due_in_days=1,
                            priority="urgent",
                        )
                    ],
                    estimated_close_probability=0.68,
                    next_best_action="Book a same-week legal review meeting.",
                )

            if agent_name == "ReviewAgent":
                return ReviewDecision(
                    approved=True,
                    quality_score=0.9,
                    feedback="Action plan is specific and appropriately urgent.",
                    escalate_to_manager=True,
                )

            raise AssertionError(f"Unexpected agent name: {agent_name}")

        monkeypatch.setattr("app.workflows.revops_workflow._run_with_retry", fake_run_with_retry)

        result = run_revops(lead_data, session_id="test")

        assert result["lead_id"] == "lead-001"
        assert result["triage"]["workflow_lane"] == "accelerate"
        assert result["enriched"]["company_profile"]["industry"] == "Manufacturing"
        assert result["action_plan"]["lead_id"] == "lead-001"
        assert result["review"]["approved"] is True
        assert result["observability"]["status"] == "success"
        assert set(result["observability"]["per_agent_latency_ms"]) == {
            "TriageAgent",
            "EnrichmentAgent",
            "ActionAgent",
            "ReviewAgent",
        }


class TestPlaygroundCompatRoutes:
    def test_playground_workflow_detail_route_returns_schema_and_steps(self):
        from demo.run_demo import create_ui_app

        client = TestClient(create_ui_app())

        list_response = client.get("/playground/workflows")
        assert list_response.status_code == 200
        workflows = list_response.json()
        assert workflows[0]["workflow_id"] == "revops-workflow"

        detail_response = client.get("/playground/workflows/revops-workflow")
        assert detail_response.status_code == 200

        payload = detail_response.json()
        assert payload["workflow_id"] == "revops-workflow"
        assert payload["input_schema"]["title"] == "Lead"
        assert [step["name"] for step in payload["steps"]] == [
            "TriageAgent",
            "EnrichmentAgent",
            "ActionAgent",
            "ReviewAgent",
        ]

    def test_ui_app_exposes_workflow_sessions_without_db_errors(self):
        from demo.run_demo import create_ui_app

        client = TestClient(create_ui_app())
        response = client.get("/sessions?workflow_id=revops-workflow")

        assert response.status_code == 200
        payload = response.json()
        assert payload["data"] == []

    def test_playground_run_route_accepts_json_body(self, monkeypatch):
        from demo.run_demo import create_ui_app

        lead_data = {
            "id": "lead-001",
            "name": "Sarah Chen",
            "company": "Acme Corp",
            "email": "s.chen@acmecorp.com",
            "deal_value": 120000,
            "stage": "negotiation",
            "last_contact_days": 18,
            "notes": "Legal is reviewing MSA. Champion is VP of Ops.",
            "industry": "Manufacturing",
        }

        monkeypatch.setattr("app.workflows.revops_workflow.create_triage_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_enrichment_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_action_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_review_agent", lambda: object())

        def fake_run_with_retry(agent, prompt, schema, agent_name, tracker, inject=None):
            tracker.agent_start(agent_name)
            time.sleep(0.001)
            tracker.agent_end(agent_name, tokens=25)

            if agent_name == "TriageAgent":
                return TriageResult(
                    lead_id="lead-001",
                    urgency="critical",
                    category="new_business",
                    priority_score=9,
                    reason="Large late-stage deal needs coordination.",
                    workflow_lane="accelerate",
                    manager_watch=True,
                    specialist_brief="Protect deal momentum and unblock legal.",
                )

            if agent_name == "EnrichmentAgent":
                return schema(
                    company_profile=CompanyProfile(
                        company_size="enterprise",
                        employee_count=5000,
                        annual_revenue_usd=500_000_000,
                        industry="Manufacturing",
                        health_score=0.72,
                        recent_activity=["Attended product webinar 2 weeks ago"],
                    ),
                    risk_flags=["large_deal_stalled"],
                )

            if agent_name == "ActionAgent":
                return ActionPlan(
                    lead_id="lead-001",
                    summary="Large strategic opportunity with active legal review.",
                    recommended_actions=[
                        ActionItem(
                            action="Schedule legal unblock call",
                            owner="ae",
                            due_in_days=1,
                            priority="urgent",
                        )
                    ],
                    estimated_close_probability=0.68,
                    next_best_action="Book a same-week legal review meeting.",
                )

            if agent_name == "ReviewAgent":
                return ReviewDecision(
                    approved=True,
                    quality_score=0.9,
                    feedback="Action plan is specific and appropriately urgent.",
                    escalate_to_manager=True,
                )

            raise AssertionError(f"Unexpected agent name: {agent_name}")

        monkeypatch.setattr("app.workflows.revops_workflow._run_with_retry", fake_run_with_retry)

        client = TestClient(create_ui_app())
        response = client.post(
            "/playground/workflows/revops-workflow/runs",
            json={"input": lead_data, "stream": False},
        )

        assert response.status_code == 200
        payload = response.json()
        assert payload["workflow_id"] == "revops-workflow"
        assert payload["status"] == "COMPLETED"

    def test_playground_run_route_falls_back_to_default_mock_lead(self, monkeypatch):
        from demo.run_demo import create_ui_app

        seen = {}

        monkeypatch.setattr("app.workflows.revops_workflow.create_triage_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_enrichment_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_action_agent", lambda: object())
        monkeypatch.setattr("app.workflows.revops_workflow.create_review_agent", lambda: object())

        def fake_run_with_retry(agent, prompt, schema, agent_name, tracker, inject=None):
            tracker.agent_start(agent_name)
            time.sleep(0.001)
            tracker.agent_end(agent_name, tokens=20)

            if agent_name == "TriageAgent":
                seen["prompt"] = prompt
                return TriageResult(
                    lead_id="lead-001",
                    urgency="critical",
                    category="new_business",
                    priority_score=9,
                    reason="Large late-stage deal needs coordination.",
                    workflow_lane="accelerate",
                    manager_watch=True,
                    specialist_brief="Protect deal momentum and unblock legal.",
                )

            if agent_name == "EnrichmentAgent":
                return schema(
                    company_profile=CompanyProfile(
                        company_size="enterprise",
                        employee_count=5000,
                        annual_revenue_usd=500_000_000,
                        industry="Manufacturing",
                        health_score=0.72,
                        recent_activity=["Attended product webinar 2 weeks ago"],
                    ),
                    risk_flags=["large_deal_stalled"],
                )

            if agent_name == "ActionAgent":
                return ActionPlan(
                    lead_id="lead-001",
                    summary="Large strategic opportunity with active legal review.",
                    recommended_actions=[
                        ActionItem(
                            action="Schedule legal unblock call",
                            owner="ae",
                            due_in_days=1,
                            priority="urgent",
                        )
                    ],
                    estimated_close_probability=0.68,
                    next_best_action="Book a same-week legal review meeting.",
                )

            if agent_name == "ReviewAgent":
                return ReviewDecision(
                    approved=True,
                    quality_score=0.9,
                    feedback="Action plan is specific and appropriately urgent.",
                    escalate_to_manager=True,
                )

            raise AssertionError(f"Unexpected agent name: {agent_name}")

        monkeypatch.setattr("app.workflows.revops_workflow._run_with_retry", fake_run_with_retry)

        client = TestClient(create_ui_app())
        response = client.post("/playground/workflows/revops-workflow/runs", json={"stream": False})

        assert response.status_code == 200
        assert "Sarah Chen" in seen["prompt"]
        payload = response.json()
        assert payload["status"] == "COMPLETED"
