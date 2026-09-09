from types import SimpleNamespace

import pytest

from app.agents.reasoner import (
    ModelClaim,
    ModelReasoningOutput,
    OpenAIReasonerAgent,
    ReasonerOutputError,
)
from app.knowledge import KnowledgeBase
from app.models import ReviewRequest
from app.orchestrator import ReviewOrchestrator
from app.settings import settings


class FakeResponses:
    def __init__(self, parsed: ModelReasoningOutput) -> None:
        self.parsed = parsed
        self.calls: list[dict[str, object]] = []

    def parse(self, **kwargs: object) -> SimpleNamespace:
        self.calls.append(kwargs)
        return SimpleNamespace(
            id="resp_test_123",
            output_parsed=self.parsed,
            usage=SimpleNamespace(input_tokens=240, output_tokens=72),
        )


class FakeClient:
    def __init__(self, parsed: ModelReasoningOutput) -> None:
        self.responses = FakeResponses(parsed)


def review_request() -> ReviewRequest:
    return ReviewRequest(
        case_id="llm-test",
        patient_summary="Synthetic adult case reports difficulty breathing and chest pain today.",
        question="Which issue should be handled first?",
        top_k=1,
    )


def triage_hit():
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)
    return knowledge_base.search(
        "difficulty breathing chest pain urgent",
        top_k=1,
    )[0]


def test_openai_reasoner_uses_structured_output_and_provider_usage() -> None:
    hit = triage_hit()
    parsed = ModelReasoningOutput(
        summary="Synthetic case with urgent warning signs.",
        claims=[
            ModelClaim(
                text=hit.document.recommendation,
                category="triage",
                citation_ids=[hit.document.id],
                confidence=0.94,
            )
        ],
        uncertainties=["A qualified human must assess the case."],
    )
    client = FakeClient(parsed)
    reasoner = OpenAIReasonerAgent(model="test-model", client=client)

    result = reasoner.run(review_request(), [hit])

    assert result.mode == "openai"
    assert result.model_name == "test-model"
    assert result.provider_response_id == "resp_test_123"
    assert result.input_tokens == 240
    assert result.output_tokens == 72
    assert result.claims[0].citation_ids == [
        "cdc-respiratory-emergency-adults-001"
    ]
    call = client.responses.calls[0]
    assert call["text_format"] is ModelReasoningOutput
    assert call["store"] is False


def test_openai_reasoner_rejects_citation_outside_retrieved_evidence() -> None:
    hit = triage_hit()
    parsed = ModelReasoningOutput(
        summary="Synthetic case summary.",
        claims=[
            ModelClaim(
                text="A claim with an invented citation.",
                category="triage",
                citation_ids=["invented-document-id"],
                confidence=0.9,
            )
        ],
        uncertainties=[],
    )
    reasoner = OpenAIReasonerAgent(
        model="test-model",
        client=FakeClient(parsed),
    )

    with pytest.raises(ReasonerOutputError, match="invented-document-id"):
        reasoner.run(review_request(), [hit])


def test_openai_reasoner_skips_model_call_when_retrieval_is_empty() -> None:
    client = FakeClient(
        ModelReasoningOutput(summary="unused", claims=[], uncertainties=[])
    )
    reasoner = OpenAIReasonerAgent(model="test-model", client=client)

    result = reasoner.run(review_request(), [])

    assert result.claims == []
    assert client.responses.calls == []


def test_orchestrator_exposes_provider_token_usage() -> None:
    hit = triage_hit()
    parsed = ModelReasoningOutput(
        summary="Synthetic case with urgent warning signs.",
        claims=[
            ModelClaim(
                text=hit.document.recommendation,
                category="triage",
                citation_ids=[hit.document.id],
                confidence=0.94,
            )
        ],
        uncertainties=[],
    )
    reasoner = OpenAIReasonerAgent(
        model="test-model",
        client=FakeClient(parsed),
    )
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)
    orchestrator = ReviewOrchestrator(knowledge_base, reasoner=reasoner)

    result = orchestrator.run(review_request())

    assert result.metrics.reasoner_mode == "openai"
    assert result.metrics.model_name == "test-model"
    assert result.metrics.input_tokens == 240
    assert result.metrics.output_tokens == 72
    assert result.metrics.token_count_source == "provider"
