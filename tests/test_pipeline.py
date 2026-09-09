from app.evaluation import EvaluationRunner
from app.knowledge import KnowledgeBase
from app.models import ReviewRequest, VerificationLabel
from app.orchestrator import ReviewOrchestrator
from app.settings import settings


def build_orchestrator() -> ReviewOrchestrator:
    return ReviewOrchestrator(KnowledgeBase.from_json(settings.knowledge_base_path))


def test_review_pipeline_returns_citation_bound_claims() -> None:
    response = build_orchestrator().run(
        ReviewRequest(
            case_id="test-case",
            patient_summary=(
                "Synthetic adult case reports difficulty breathing and chest pain today."
            ),
            question="Which issue should be handled first?",
            top_k=1,
        )
    )

    assert response.status == "grounded"
    assert response.citations[0].citation_id == "cdc-respiratory-emergency-adults-001"
    assert response.claims[0].citation_ids == [
        "cdc-respiratory-emergency-adults-001"
    ]
    assert all(
        result.label == VerificationLabel.supported for result in response.verification
    )
    assert response.conflicts == []


def test_pipeline_refuses_to_generate_without_relevant_evidence() -> None:
    response = build_orchestrator().run(
        ReviewRequest(
            case_id="unrelated-case",
            patient_summary="Synthetic question about orbital mechanics and telescope mirrors.",
            question="Which launch trajectory is most efficient?",
            top_k=3,
        )
    )

    assert response.status == "no_evidence"
    assert response.claims == []
    assert response.citations == []


def test_bundled_evaluation_has_full_recall_and_grounding() -> None:
    report = EvaluationRunner(build_orchestrator(), settings.evaluation_cases_path).run()

    assert report.case_count == 6
    assert report.mean_retrieval_recall == 1.0
    assert report.mean_supported_claim_rate == 1.0
    assert report.hallucination_rate == 0.0
