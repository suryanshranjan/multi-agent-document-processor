from __future__ import annotations

import time
from collections.abc import Callable
from typing import TypeVar

from backend.app.schemas import AgentTrace

T = TypeVar("T")


class MonitoringAgent:
    def __init__(self) -> None:
        self.trace: list[AgentTrace] = []
        self.warnings: list[str] = []
        self.errors: list[str] = []

    def run_step(self, agent: str, message: str, action: Callable[[], T]) -> T:
        started = time.perf_counter()
        try:
            result = action()
        except Exception as exc:
            duration_ms = (time.perf_counter() - started) * 1000
            self.errors.append(str(exc))
            self.trace.append(
                AgentTrace(
                    agent=agent,
                    status="failed",
                    message=str(exc),
                    duration_ms=round(duration_ms, 2),
                )
            )
            raise

        duration_ms = (time.perf_counter() - started) * 1000
        self.trace.append(
            AgentTrace(
                agent=agent,
                status="completed",
                message=message,
                duration_ms=round(duration_ms, 2),
            )
        )
        return result

    def record(self, agent: str, status: str, message: str, details: dict | None = None) -> None:
        self.trace.append(
            AgentTrace(
                agent=agent,
                status=status,
                message=message,
                duration_ms=0,
                details=details or {},
            )
        )

    def warn(self, message: str) -> None:
        self.warnings.append(message)
        self.record("MonitoringAgent", "warning", message)

