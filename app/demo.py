"""Fixed, offline fault injection; never enabled through the normal review request."""

from dataclasses import replace

from app.agents.reasoner import ExtractiveReasonerAgent, ReasonerRun
from app.knowledge import KnowledgeBase
from app.models import Claim, RetrievalHit, ReviewRequest, ReviewResponse
from app.orchestrator import ReviewOrchestrator


class FaultInjectionReasoner(ExtractiveReasonerAgent):
    mode = "fault_injection_demo"

    def run(self, request: ReviewRequest, hits: list[RetrievalHit]) -> ReasonerRun:
        baseline = super().run(request, hits)
        target = next(
            hit.document for hit in hits if hit.document.id == "cdc-bronchitis-antibiotics-001"
        )
        return replace(
            baseline,
            claims=[
                *baseline.claims,
                Claim(
                    claim_id="injected-contradiction",
                    text=target.contradicted_statements[0],
                    category="injected_error",
                    citation_ids=[target.id],
                    confidence=0.95,
                ),
                Claim(
                    claim_id="injected-missing-source",
                    text="This case has already been independently reviewed.",
                    category="injected_error",
                    citation_ids=["nonexistent-source"],
                    confidence=0.9,
                ),
            ],
            uncertainties=[
                (
                    "DEMO ONLY: two deliberate errors were injected after extractive reasoning. "
                    "This demonstrates detection plumbing, not an observed model failure rate."
                )
            ],
        )


def run_conflict_demo(knowledge_base: KnowledgeBase) -> ReviewResponse:
    request = ReviewRequest(
        case_id="demo-conflict-injection",
        patient_summary=(
            "Synthetic adult case with uncomplicated acute bronchitis and a seven-day cough."
        ),
        question="Should routine antibiotics be recommended because of cough duration?",
        top_k=1,
    )
    response = ReviewOrchestrator(knowledge_base, FaultInjectionReasoner()).run(request)
    return response.model_copy(update={"is_demo": True})
