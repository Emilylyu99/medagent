"""Request-local, bounded structured model calls. Never logs prompts or provider bodies."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from app.models import ProviderFailure, TraceStep
from app.provider_errors import classify_provider_error

logger = logging.getLogger(__name__)
Output = TypeVar("Output", bound=BaseModel)


@dataclass(frozen=True)
class AgentLimits:
    max_model_calls: int = 7
    max_searches: int = 3  # Includes the initial search.
    max_repairs: int = 1
    max_documents: int = 8
    max_output_tokens: int = 2048
    max_input_chars: int = 32000
    request_timeout_seconds: float = 20.0
    run_seconds: float = 90.0

    def __post_init__(self) -> None:
        for name, value in vars(self).items():
            if value < 0 or (value == 0 and name != "max_repairs"):
                raise ValueError(f"{name} must be positive (max_repairs may be zero).")
        if self.max_repairs > 1:
            raise ValueError("This prototype permits at most one repair.")


class AgentStopped(RuntimeError):
    def __init__(self, reason: str, failure: ProviderFailure | None = None) -> None:
        self.reason = reason
        self.failure = failure
        super().__init__(reason)


@dataclass
class StructuredSession:
    """One instance per review: budgets/usage cannot leak between concurrent requests."""

    client: Any
    model: str
    limits: AgentLimits
    trace: list[TraceStep] = field(default_factory=list)
    started_at: float = field(default_factory=perf_counter)
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    usage_complete: bool = True

    def check_budget(self) -> float:
        remaining = self.limits.run_seconds - (perf_counter() - self.started_at)
        if remaining <= 0:
            raise AgentStopped("time_budget_exhausted")
        if self.calls >= self.limits.max_model_calls:
            raise AgentStopped("model_call_budget_exhausted")
        return remaining

    def call(
        self, component: str, instructions: str, payload: dict, schema: type[Output]
    ) -> Output:
        remaining = self.check_budget()
        serialized = json.dumps(payload, ensure_ascii=False)
        if len(serialized) + len(instructions) > self.limits.max_input_chars:
            raise AgentStopped("input_budget_exhausted")
        self.calls += 1
        started = perf_counter()
        step = TraceStep(
            component=component,
            status="started",
            duration_ms=0,
            details={"call": self.calls, "model": self.model, "prompt_version": "adaptive-v1"},
        )
        self.trace.append(step)
        try:
            response = self.client.responses.parse(
                model=self.model,
                instructions=instructions,
                input=serialized,
                text_format=schema,
                store=False,
                max_output_tokens=self.limits.max_output_tokens,
                timeout=min(self.limits.request_timeout_seconds, remaining),
            )
        except Exception as exc:  # noqa: BLE001 - isolate SDK/transport failures at this boundary
            self.usage_complete = False
            step.status = "failed"
            step.duration_ms = round((perf_counter() - started) * 1000, 3)
            failure = classify_provider_error(exc)
            step.details["failure"] = failure.model_dump(mode="json")
            logger.warning("%s request failed (category=%s, code=%s, status=%s)",
                           component, failure.category, failure.code, failure.http_status)
            raise AgentStopped("provider_error", failure=failure) from None

        step.duration_ms = round((perf_counter() - started) * 1000, 3)
        usage = getattr(response, "usage", None)
        for name in ("input_tokens", "output_tokens"):
            value = getattr(usage, name, None)
            if isinstance(value, int) and value >= 0:
                setattr(self, name, getattr(self, name) + value)
                step.details[name] = value
            else:
                self.usage_complete = False
        step.details["provider_response_id"] = getattr(response, "id", None)
        try:
            if getattr(response, "status", "completed") != "completed":
                raise AgentStopped("incomplete_model_output")
            parsed = getattr(response, "output_parsed", None)
            if parsed is None:
                raise AgentStopped("refused_or_empty_model_output")
            parsed = schema.model_validate(parsed)
            # A slow call must not authorize further actions after the deadline.
            if perf_counter() - self.started_at >= self.limits.run_seconds:
                raise AgentStopped("time_budget_exhausted")
        except ValidationError:
            step.status = "rejected"
            raise AgentStopped("invalid_model_output") from None
        except AgentStopped:
            step.status = "rejected"
            raise
        step.status = "completed"
        return parsed
