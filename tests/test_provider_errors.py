"""Construct SDK errors locally; no provider requests or credentials are needed."""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.adaptive import AdaptiveReviewOrchestrator
from app.agents.reasoner import OpenAIReasonerAgent
from app.models import ReviewRequest
from app.orchestrator import ReviewOrchestrator
from app.provider_errors import classify_provider_error

openai = pytest.importorskip("openai")
SENSITIVE = "sk-DO-NOT-PRINT-THIS-TEST-SECRET"
REQUEST_ID = "req_0123456789abcdef0123456789abcdef"


def error(status=429, code=None, error_type=None, retry_after="12"):
    request = httpx.Request(
        "POST",
        "https://api.openai.com/v1/responses",
        headers={"Authorization": "Bearer " + SENSITIVE},
    )
    response = httpx.Response(
        status,
        request=request,
        headers={
            "retry-after": retry_after,
            "x-request-id": REQUEST_ID,
        },
    )
    cls = openai.RateLimitError if status == 429 else openai.APIStatusError
    return cls(
        SENSITIVE,
        response=response,
        body={"code": code, "type": error_type, "message": SENSITIVE, "case": SENSITIVE},
    )


@pytest.mark.parametrize(
    "code,category,retryable",
    [
        ("credit_balance_exhausted", "credits_exhausted", False),
        ("insufficient_quota", "quota_exceeded", False),
        ("organization_spend_limit_exceeded", "spend_limit", False),
        ("project_spend_limit_exceeded", "spend_limit", False),
        ("organization_usage_limit_exceeded", "usage_limit", False),
        ("rate_limit_exceeded", "rate_limited", True),
        ("slow_down", "rate_limited", True),
        (None, "rate_limit_or_quota", False),
    ],
)
def test_429_categories_are_distinct(code, category, retryable):
    failure = classify_provider_error(error(code=code))
    assert failure.category == category
    assert failure.retryable is retryable
    assert failure.code == code
    assert failure.request_id == REQUEST_ID
    assert failure.retry_after_seconds == 12
    assert SENSITIVE not in failure.model_dump_json()


def test_specific_credit_code_takes_precedence_over_broad_quota_type():
    failure = classify_provider_error(
        error(code="credit_balance_exhausted", error_type="insufficient_quota")
    )
    assert failure.category == "credits_exhausted"
    failure = classify_provider_error(error(error_type="insufficient_quota"))
    assert failure.category == "quota_exceeded"
    failure = classify_provider_error(error(error_type="rate_limit_error"))
    assert failure.category == "rate_limited"


@pytest.mark.parametrize(
    "status,category",
    [
        (400, "invalid_request"),
        (401, "authentication"),
        (403, "permission"),
        (404, "model_unavailable"),
        (422, "invalid_request"),
        (500, "service_unavailable"),
        (503, "service_unavailable"),
    ],
)
def test_other_provider_statuses(status, category):
    assert classify_provider_error(error(status=status)).category == category


def test_sdk_timeout_and_connection_are_distinct():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    assert classify_provider_error(openai.APITimeoutError(request)).category == "timeout"
    assert (
        classify_provider_error(openai.APIConnectionError(request=request)).category == "connection"
    )


@pytest.mark.parametrize("value", ["", "NaN", "Infinity", "-1", "100000000", SENSITIVE])
def test_unsafe_retry_header_is_not_exported(value):
    failure = classify_provider_error(error(retry_after=value))
    assert failure.retry_after_seconds is None
    assert SENSITIVE not in failure.model_dump_json()


def test_unknown_fields_and_ids_cannot_leak_secrets():
    problem = error(code=SENSITIVE)
    problem.request_id = SENSITIVE
    failure = classify_provider_error(problem)
    assert failure.category == "rate_limit_or_quota"
    assert failure.code is None
    assert failure.request_id is None
    assert SENSITIVE not in failure.model_dump_json()


class FailingClient:
    def __init__(self, problem):
        self.problem = problem
        self.responses = self
        self.calls = 0

    def parse(self, **kwargs):
        self.calls += 1
        raise self.problem


def request_case():
    return ReviewRequest(
        case_id="failure-test",
        patient_summary="Synthetic case includes identifiers in free text.",
        question="Which identifiers should be reviewed?",
        top_k=1,
    )


def test_adaptive_propagates_diagnostics_without_retry_or_secret(caplog):
    model = FailingClient(error(code="insufficient_quota"))
    pipeline = AdaptiveReviewOrchestrator(
        main.knowledge_base, OpenAIReasonerAgent(model="test", client=model)
    )
    result = pipeline.run(request_case())
    assert result.failure.category == "quota_exceeded"
    assert result.status == "model_error" and result.claims == []
    assert result.trace[1].details["failure"]["code"] == "insufficient_quota"
    assert result.metrics.token_count_source == "partial_or_unavailable"
    assert model.calls == 1
    assert "insufficient_quota" in caplog.text
    assert SENSITIVE not in result.model_dump_json() + caplog.text


def test_single_pass_api_returns_sanitized_structured_failure(monkeypatch):
    model = FailingClient(error(code="credit_balance_exhausted"))
    pipeline = ReviewOrchestrator(
        main.knowledge_base, OpenAIReasonerAgent(model="test", client=model)
    )
    monkeypatch.setattr(main, "orchestrator", pipeline)
    response = TestClient(main.app).post("/v1/reviews", json=request_case().model_dump())
    assert response.status_code == 502
    assert response.json()["detail"]["category"] == "credits_exhausted"
    assert model.calls == 1
    assert SENSITIVE not in response.text


@pytest.mark.parametrize("adaptive", [False, True])
def test_ui_displays_actionable_provider_failure(monkeypatch, adaptive):
    testing = pytest.importorskip("streamlit.testing.v1")
    model = FailingClient(error(code="credit_balance_exhausted"))
    reasoner = OpenAIReasonerAgent(model="test", client=model)
    cls = AdaptiveReviewOrchestrator if adaptive else ReviewOrchestrator
    monkeypatch.setattr(main, "orchestrator", cls(main.knowledge_base, reasoner))
    client = TestClient(main.app)
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: client.get("/health"))
    monkeypatch.setattr(
        httpx, "post", lambda url, **kwargs: client.post("/v1/reviews", json=kwargs["json"])
    )
    ui = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/app.py")).run()
    next(b for b in ui.button if b.label == "Run Agents").click().run()
    assert not ui.exception
    assert any("no prepaid credits" in item.value for item in ui.error)
    assert any("offline mode" in item.value for item in ui.caption)
    assert model.calls == 1
    assert SENSITIVE not in json.dumps([item.value for item in ui.error])


def test_unknown_exception_stays_generic():
    failure = classify_provider_error(ValueError(SENSITIVE))
    assert failure.category == "unknown"
    assert SENSITIVE not in failure.model_dump_json()


def test_cli_prints_specific_failure_instead_of_only_model_error(monkeypatch, tmp_path, capsys):
    from scripts import compare_modes

    model = FailingClient(error(code="credit_balance_exhausted"))
    reasoner = OpenAIReasonerAgent(model="test", client=model)
    monkeypatch.setattr(compare_modes, "OpenAIReasonerAgent", lambda **kwargs: reasoner)
    monkeypatch.setattr(
        "sys.argv", ["compare_modes", "--allow-model-calls", "--output", str(tmp_path / "result")]
    )
    with pytest.raises(SystemExit, match="Stopped after"):
        compare_modes.main()
    output = capsys.readouterr().out
    assert "credits_exhausted" in output
    assert SENSITIVE not in output
    assert model.calls == 1


def test_network_guard_is_active():
    import socket

    with pytest.raises(AssertionError, match="Network disabled"):
        socket.create_connection(("example.com", 443))
