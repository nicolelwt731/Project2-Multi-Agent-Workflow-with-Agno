"""
Demo runner for the RevOps multi-agent workflow.

Usage:
    # Run all 4 mock leads (CLI):
    python demo/run_demo.py

    # Run a specific lead by index (0-3):
    python demo/run_demo.py --lead 1

    # Launch Agno Playground UI:
    python demo/run_demo.py --ui
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).parents[1]))

from agno.db.sqlite.sqlite import SqliteDb
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from rich.console import Console
from rich.panel import Panel
from rich.rule import Rule

console = Console()
DATA_PATH = Path(__file__).parents[1] / "data" / "mock_leads.json"
AGENTOS_DB_PATH = Path(__file__).parents[1] / ".agno" / "playground.db"
CONTROL_FIELDS = {"stream", "session_id", "user_id"}
INPUT_FIELDS = ("message", "input", "content", "prompt", "text")


def run_cli(lead_index: int | None = None) -> None:
    from app.workflows.revops_workflow import run_revops

    leads = load_mock_leads()
    targets = [leads[lead_index]] if lead_index is not None else leads

    for lead_data in targets:
        console.print(Rule(f"[bold cyan]{lead_data['name']} @ {lead_data['company']}"))
        result = run_revops(lead_data, session_id="demo")
        console.print_json(json.dumps(result, default=str))
        console.print()


def load_mock_leads() -> list[dict[str, Any]]:
    return json.loads(DATA_PATH.read_text())


def get_default_playground_input() -> dict[str, Any]:
    leads = load_mock_leads()
    if not leads:
        raise RuntimeError("No mock leads available for Playground fallback input.")
    return leads[0]


def _coerce_bool(value: Any, default: bool = True) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)

    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on"}:
        return True
    if text in {"0", "false", "no", "off"}:
        return False
    return default


def _maybe_parse_json(value: Any) -> Any:
    if not isinstance(value, str):
        return value

    text = value.strip()
    if not text:
        return ""

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return value


async def _parse_playground_run_request(request: Request) -> tuple[Any, bool, str | None, str | None]:
    content_type = request.headers.get("content-type", "").lower()

    if "application/json" in content_type:
        payload: Any = await request.json()
    elif "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
        payload = dict(await request.form())
    else:
        raw = (await request.body()).decode().strip()
        payload = _maybe_parse_json(raw) if raw else {}

    stream = True
    session_id = None
    user_id = None

    if isinstance(payload, dict):
        stream = _coerce_bool(payload.get("stream"), True)
        session_id = payload.get("session_id")
        user_id = payload.get("user_id")

        for field in INPUT_FIELDS:
            if field in payload and payload[field] not in (None, ""):
                return _maybe_parse_json(payload[field]), stream, session_id, user_id

        structured_input = {k: v for k, v in payload.items() if k not in CONTROL_FIELDS}
        if structured_input:
            return structured_input, stream, session_id, user_id
        return None, stream, session_id, user_id

    if isinstance(payload, list):
        return payload, stream, session_id, user_id

    return _maybe_parse_json(payload), stream, session_id, user_id


def create_ui_app():
    from agno.os.app import AgentOS
    from agno.os.routers.workflows.router import workflow_response_streamer
    from agno.os.routers.workflows.schema import WorkflowResponse
    from agno.os.schema import WorkflowSummaryResponse
    from app.workflows.revops_workflow import build_revops_workflow

    agent_os = AgentOS(
        workflows=[build_revops_workflow()],
        db=SqliteDb(db_file=str(AGENTOS_DB_PATH)),
    )
    app = agent_os.get_app()

    def resolve_workflow(workflow_id: str, session_id: str | None = None):
        if workflow_id != "revops-workflow":
            return None
        return build_revops_workflow(session_id=session_id or "revops-ui")

    # Compatibility routes for app.agno.com PLAYGROUND section
    compat = APIRouter(prefix="/playground")

    @compat.get("/status")
    async def playground_status():
        return {"status": "available"}

    @compat.get("/agents")
    async def playground_agents():
        return []

    @compat.get("/workflows")
    async def playground_workflows():
        return [
            {
                **WorkflowSummaryResponse.from_workflow(w).model_dump(exclude_none=True),
                "workflow_id": w.id,
            }
            for w in (agent_os.workflows or [])
        ]

    @compat.get("/workflows/{workflow_id}")
    async def playground_workflow_detail(workflow_id: str):
        workflow = resolve_workflow(workflow_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        detail = await WorkflowResponse.from_workflow(workflow)
        payload = detail.model_dump(exclude_none=True)
        payload["workflow_id"] = workflow.id
        return payload

    @compat.post("/workflows/{workflow_id}/runs")
    async def playground_run_workflow(
        workflow_id: str,
        request: Request,
        background_tasks: BackgroundTasks,
    ):
        workflow_input, stream, session_id, user_id = await _parse_playground_run_request(request)
        workflow = resolve_workflow(workflow_id, session_id=session_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        if workflow_input in (None, ""):
            workflow_input = get_default_playground_input()
            console.print(
                "[yellow]Playground did not send workflow input; using the first mock lead as a demo default.[/yellow]"
            )

        session_id = session_id or str(uuid4())

        if stream:
            return StreamingResponse(
                workflow_response_streamer(
                    workflow,
                    input=workflow_input,
                    session_id=session_id,
                    user_id=user_id,
                    background_tasks=background_tasks,
                ),
                media_type="text/event-stream",
            )

        run_response = await workflow.arun(
            input=workflow_input,
            session_id=session_id,
            user_id=user_id,
            stream=False,
            background_tasks=background_tasks,
        )
        return run_response.to_dict()

    @compat.get("/workflows/{workflow_id}/runs/{run_id}")
    async def playground_get_workflow_run(
        workflow_id: str,
        run_id: str,
        session_id: str = Query(...),
    ):
        workflow = resolve_workflow(workflow_id, session_id=session_id)
        if workflow is None:
            raise HTTPException(status_code=404, detail="Workflow not found")

        run_output = await workflow.aget_run_output(run_id=run_id, session_id=session_id)
        if run_output is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return run_output.to_dict()

    app.include_router(compat)
    return app


def run_ui() -> None:
    app = create_ui_app()

    console.print(Panel(
        "[bold green]Agno Playground UI starting...[/]\n"
        "Open: [link=http://localhost:7777]http://localhost:7777[/link]\n\n"
        "Paste a lead JSON as input to run the pipeline.",
        title="🚀 RevOps Workflow Demo",
    ))

    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=7777)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="RevOps Workflow Demo")
    parser.add_argument("--lead", type=int, default=None, help="Lead index 0-3")
    parser.add_argument("--ui", action="store_true", help="Launch Agno Playground UI")
    args = parser.parse_args()

    if args.ui:
        run_ui()
    else:
        run_cli(lead_index=args.lead)
