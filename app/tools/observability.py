"""Lightweight observability tracker for workflow runs."""

from __future__ import annotations

import time
import uuid
from datetime import datetime, timezone
from typing import Dict, List

from app.models.schemas import WorkflowObservability


class ObservabilityTracker:
    def __init__(self, lead_id: str):
        self._reset(lead_id)

    def _reset(self, lead_id: str) -> None:
        self.workflow_id = str(uuid.uuid4())[:8]
        self.lead_id = lead_id
        self._start = time.perf_counter()
        self._agent_starts: Dict[str, float] = {}
        self.per_agent_latency_ms: Dict[str, float] = {}
        self.token_usage: Dict[str, int] = {}
        self.errors: List[str] = []
        self.status = "success"

    def reset(self, lead_id: str) -> None:
        self._reset(lead_id)

    def agent_start(self, agent_name: str) -> None:
        self._agent_starts[agent_name] = time.perf_counter()

    def agent_end(self, agent_name: str, tokens: int = 0) -> None:
        start = self._agent_starts.get(agent_name, time.perf_counter())
        self.per_agent_latency_ms[agent_name] = round(
            (time.perf_counter() - start) * 1000, 2
        )
        if tokens:
            self.token_usage[agent_name] = tokens

    def record_error(self, msg: str) -> None:
        self.errors.append(msg)
        self.status = "partial" if self.per_agent_latency_ms else "failed"

    def finalize(self) -> WorkflowObservability:
        total_ms = round((time.perf_counter() - self._start) * 1000, 2)
        if self.errors and not self.per_agent_latency_ms:
            self.status = "failed"
        return WorkflowObservability(
            workflow_id=self.workflow_id,
            lead_id=self.lead_id,
            total_latency_ms=total_ms,
            per_agent_latency_ms=self.per_agent_latency_ms,
            token_usage=self.token_usage,
            status=self.status,
            errors=self.errors,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def log(self, obs: WorkflowObservability) -> None:
        print("\n" + "=" * 60)
        print(f"  OBSERVABILITY REPORT  [{obs.workflow_id}]")
        print("=" * 60)
        print(f"  Status        : {obs.status.upper()}")
        print(f"  Lead ID       : {obs.lead_id}")
        print(f"  Total latency : {obs.total_latency_ms:.1f} ms")
        print("  Per-agent latency:")
        for agent, ms in obs.per_agent_latency_ms.items():
            tokens = obs.token_usage.get(agent, 0)
            print(f"    {agent:<20} {ms:>8.1f} ms   {tokens:>5} tokens")
        if obs.errors:
            print("  Errors:")
            for e in obs.errors:
                print(f"    ⚠ {e}")
        print("=" * 60 + "\n")
