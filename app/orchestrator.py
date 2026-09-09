from __future__ import annotations

from time import perf_counter

from app.agents.conflict_detector import ConflictDetector
from app.agents.reasoner import ExtractiveReasonerAgent, ReasonerAgent
from app.agents.retriever import RetrieverAgent
from app.agents.verifier import VerifierAgent
from app.knowledge import KnowledgeBase
from app.models import (
    Citation,
    PipelineMetrics,
    ReviewRequest,
    ReviewResponse,
    TraceStep,
    VerificationLabel,
)

DISCLAIMER = (
    "Educational synthetic-case demonstration using curated public-source paraphrases. "
    "This output is not medical advice, does not provide a diagnosis, and must not be "
    "used for patient care. Verify all details on the linked official source pages."
)


def _milliseconds(start: float, end: float) -> float:
    return round((end - start) * 1_000, 3)


def _estimated_tokens(text: str) -> int:
    return max(1, round(len(text) / 4))


class ReviewOrchestrator:
    pipeline_mode = "baseline"

    def __init__(
        self,
        knowledge_base: KnowledgeBase,
        reasoner: ReasonerAgent | None = None,
    ) -> None:
        self.knowledge_base = knowledge_base
        self.retriever = RetrieverAgent(knowledge_base)
        self.reasoner = reasoner or ExtractiveReasonerAgent()
        self.verifier = VerifierAgent()
        self.conflict_detector = ConflictDetector()

    def run(self, request: ReviewRequest) -> ReviewResponse:
        started_at = perf_counter()

        retrieval_started = perf_counter()
        hits = self.retriever.run(request)
        retrieval_finished = perf_counter()

        reasoning_started = perf_counter()
        reasoner_run = self.reasoner.run(request, hits)
        summary = reasoner_run.summary
        claims = reasoner_run.claims
        uncertainties = reasoner_run.uncertainties
        reasoning_finished = perf_counter()

        verification_started = perf_counter()
        documents_by_id = {hit.document.id: hit.document for hit in hits}
        verification = self.verifier.run(claims, documents_by_id)
        verification_finished = perf_counter()
        conflict_started = perf_counter()
        conflicts = self.conflict_detector.run(claims, verification)
        conflict_finished = perf_counter()

        cited_ids = {citation_id for claim in claims for citation_id in claim.citation_ids}
        retrieved_citations = [
            Citation(
                citation_id=hit.document.id,
                title=hit.document.title,
                source=hit.document.source,
                publisher=hit.document.publisher,
                source_url=hit.document.source_url,
                source_updated_at=hit.document.source_updated_at,
                source_accessed_at=hit.document.source_accessed_at,
                content_kind=hit.document.content_kind,
                is_paraphrase=hit.document.is_paraphrase,
                jurisdiction=hit.document.jurisdiction,
                version=hit.document.version,
                excerpt=hit.document.text,
                review_point=hit.document.recommendation,
                retrieval_score=hit.score,
                matched_terms=hit.matched_terms,
            )
            for hit in hits
        ]
        citations = [c for c in retrieved_citations if c.citation_id in cited_ids]

        supported_count = sum(
            result.label == VerificationLabel.supported for result in verification
        )
        supported_rate = supported_count / len(verification) if verification else 0.0
        finished_at = perf_counter()
        output_text = " ".join(claim.text for claim in claims)

        if conflicts:
            status = "needs_human_review"
        elif not claims:
            status = "abstained" if hits else "no_evidence"
        else:
            status = "grounded"

        trace = [
            TraceStep(
                component="retriever",
                status="completed",
                duration_ms=_milliseconds(retrieval_started, retrieval_finished),
                details={
                    "candidate_documents": len(self.knowledge_base.documents),
                    "retrieved_documents": len(hits),
                    "retrieved_ids": [hit.document.id for hit in hits],
                },
            ),
            TraceStep(
                component="reasoner",
                status="completed",
                duration_ms=_milliseconds(reasoning_started, reasoning_finished),
                details={
                    "mode": reasoner_run.mode,
                    "model": reasoner_run.model_name,
                    "provider_response_id": reasoner_run.provider_response_id,
                    "claim_count": len(claims),
                },
            ),
            TraceStep(
                component="verifier",
                status="completed",
                duration_ms=_milliseconds(verification_started, verification_finished),
                details={
                    "supported": supported_count,
                    "flagged": len(conflicts),
                    "method": "exact_text_and_known_counterexamples_v2",
                },
            ),
            TraceStep(
                component="conflict_detector",
                status="flagged" if conflicts else "completed",
                duration_ms=_milliseconds(conflict_started, conflict_finished),
                details={"conflicts": len(conflicts), "requires_review": bool(conflicts)},
            ),
        ]

        estimated_input_tokens = _estimated_tokens(f"{request.patient_summary} {request.question}")
        estimated_output_tokens = _estimated_tokens(output_text)
        provider_has_usage = (
            reasoner_run.input_tokens is not None and reasoner_run.output_tokens is not None
        )

        return ReviewResponse(
            case_id=request.case_id,
            retrieved_citations=retrieved_citations,
            status=status,
            summary=summary,
            claims=claims,
            uncertainties=uncertainties,
            citations=citations,
            verification=verification,
            conflicts=conflicts,
            metrics=PipelineMetrics(
                retrieval_ms=trace[0].duration_ms,
                reasoning_ms=trace[1].duration_ms,
                verification_ms=trace[2].duration_ms,
                conflict_detection_ms=trace[3].duration_ms,
                total_ms=_milliseconds(started_at, finished_at),
                retrieved_chunks=len(hits),
                generated_claims=len(claims),
                supported_claim_rate=round(supported_rate, 3),
                reasoner_mode=reasoner_run.mode,
                model_name=reasoner_run.model_name,
                input_tokens=(
                    reasoner_run.input_tokens
                    if reasoner_run.input_tokens is not None
                    else estimated_input_tokens
                ),
                output_tokens=(
                    reasoner_run.output_tokens
                    if reasoner_run.output_tokens is not None
                    else estimated_output_tokens
                ),
                token_count_source="provider" if provider_has_usage else "estimated",
                model_calls=int(reasoner_run.provider_response_id is not None),
            ),
            trace=trace,
            disclaimer=DISCLAIMER,
        )
