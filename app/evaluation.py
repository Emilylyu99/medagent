from __future__ import annotations

import json
import math
from pathlib import Path

from app.adaptive import AdaptiveReviewOrchestrator
from app.models import (
    EvaluationCaseResult,
    EvaluationReport,
    ReviewRequest,
    VerificationLabel,
)
from app.orchestrator import ReviewOrchestrator


class EvaluationRunner:
    def __init__(self, orchestrator: ReviewOrchestrator | AdaptiveReviewOrchestrator, cases_path: Path) -> None:
        self.orchestrator = orchestrator
        self.cases_path = cases_path

    def run(self) -> EvaluationReport:
        with self.cases_path.open(encoding="utf-8") as handle:
            dataset = json.load(handle)

        results: list[EvaluationCaseResult] = []
        total_claims = 0
        unsupported_claims = 0
        initial_claims = 0
        initial_flagged = 0

        for item in dataset["cases"]:
            request = ReviewRequest.model_validate(item["request"])
            expected = set(item["expected_citation_ids"])
            response = self.orchestrator.run(request)
            retrieved = {citation.citation_id for citation in response.retrieved_citations}
            cited = {citation.citation_id for citation in response.citations}
            relevant = expected.intersection(retrieved)

            recall = len(relevant) / len(expected) if expected else 1.0
            precision = len(expected.intersection(cited)) / len(cited) if cited else 0.0
            supported = sum(
                verification.label == VerificationLabel.supported
                for verification in response.verification
            )
            claim_count = len(response.verification)
            supported_rate = supported / claim_count if claim_count else 0.0
            total_claims += claim_count
            unsupported_claims += claim_count - supported
            initial = response.attempts[0].verification if response.attempts else response.verification
            initial_claims += len(initial)
            initial_flagged += sum(v.label != VerificationLabel.supported for v in initial)

            results.append(
                EvaluationCaseResult(
                    case_id=request.case_id,
                    expected_citation_ids=sorted(expected),
                    retrieved_citation_ids=sorted(retrieved),
                    retrieval_recall=round(recall, 3),
                    citation_precision=round(precision, 3),
                    supported_claim_rate=round(supported_rate, 3),
                    conflict_count=len(response.conflicts),
                    latency_ms=response.metrics.total_ms,
                    initial_supported_claim_rate=response.metrics.initial_supported_claim_rate,
                    status=response.status,
                    repair_attempts=response.metrics.repair_attempts,
                    released_claims=len(response.claims),
                    model_calls=response.metrics.model_calls,
                    search_calls=response.metrics.search_calls,
                    input_tokens=response.metrics.input_tokens,
                    output_tokens=response.metrics.output_tokens,
                    token_count_source=response.metrics.token_count_source,
                )
            )

        case_count = len(results)

        def mean(attribute: str) -> float:
            if not results:
                return 0.0
            return round(
                sum(float(getattr(result, attribute)) for result in results) / case_count,
                3,
            )

        hallucination_rate = unsupported_claims / total_claims if total_claims else 0.0
        return EvaluationReport(
            dataset_name=dataset["dataset_name"],
            case_count=case_count,
            mean_retrieval_recall=mean("retrieval_recall"),
            mean_citation_precision=mean("citation_precision"),
            mean_supported_claim_rate=mean("supported_claim_rate"),
            hallucination_rate=round(hallucination_rate, 3),
            mean_latency_ms=mean("latency_ms"),
            p95_latency_ms=(
                sorted(result.latency_ms for result in results)[math.ceil(case_count * 0.95) - 1]
                if results
                else 0.0
            ),
            conflict_case_rate=(
                sum(result.conflict_count > 0 for result in results) / case_count
                if results
                else 0.0
            ),
            reasoner_mode=self.orchestrator.reasoner.mode,
            pipeline_mode=self.orchestrator.pipeline_mode,
            initial_flagged_claim_rate=round(initial_flagged / initial_claims, 3) if initial_claims else None,
            abstention_case_rate=sum(r.released_claims == 0 for r in results) / case_count if case_count else 0,
            error_case_rate=sum(r.status in {"model_error", "budget_exhausted"} for r in results) / case_count if case_count else 0,
            metric_note=(
                "Small synthetic smoke set, not clinical accuracy. Support scores are checker judgments "
                "(rules in baseline, model + quote checks in adaptive), not independent hallucination "
                "measurements. Legacy hallucination_rate counts final-candidate check failures; "
                "initial_flagged_claim_rate preserves pre-repair failures. Read abstention/error rates "
                "alongside scores; withholding everything is not a successful answer."
            ),
            results=results,
        )
