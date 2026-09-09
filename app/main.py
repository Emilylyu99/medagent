from __future__ import annotations

from fastapi import FastAPI, HTTPException

from app import __version__
from app.agents.reasoner import ProviderReasonerError, ReasonerError, build_reasoner
from app.challenges import OfflineChallengeReport, OfflineChallengeRunner
from app.demo import run_conflict_demo
from app.evaluation import EvaluationRunner
from app.knowledge import KnowledgeBase
from app.models import EvaluationReport, ReviewRequest, ReviewResponse
from app.pipeline import build_pipeline
from app.settings import settings

knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)
reasoner = build_reasoner(
    settings.reasoner_mode,
    openai_model=settings.openai_model,
    openai_api_key=settings.openai_api_key,
)
orchestrator = build_pipeline(settings.pipeline_mode, knowledge_base, reasoner)
evaluation_runner = EvaluationRunner(orchestrator, settings.evaluation_cases_path)

app = FastAPI(
    title="Evidence-Grounded Healthcare Agent",
    description=(
        "Synthetic-data demonstration of retrieval, citation-bound reasoning, "
        "claim verification, and conflict detection."
    ),
    version=__version__,
)


@app.get("/health")
def health() -> dict[str, str | int | None]:
    return {
        "status": "ok",
        "version": __version__,
        "environment": settings.app_env,
        "knowledge_documents": len(knowledge_base.documents),
        "reasoner_mode": reasoner.mode,
        "model_name": getattr(reasoner, "model", None),
        "pipeline_mode": settings.pipeline_mode,
    }


@app.post("/v1/reviews", response_model=ReviewResponse)
def create_review(request: ReviewRequest) -> ReviewResponse:
    try:
        return orchestrator.run(request)
    except ProviderReasonerError as exc:
        raise HTTPException(status_code=502, detail=exc.failure.model_dump(mode="json")) from None
    except ReasonerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/evaluations/run", response_model=EvaluationReport)
def run_evaluation() -> EvaluationReport:
    try:
        return evaluation_runner.run()
    except ProviderReasonerError as exc:
        raise HTTPException(status_code=502, detail=exc.failure.model_dump(mode="json")) from None
    except ReasonerError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@app.post("/v1/demos/conflict", response_model=ReviewResponse)
def conflict_demo() -> ReviewResponse:
    """Runs only the fixed synthetic fixture using the offline reasoner."""
    if not any(doc.id == "cdc-bronchitis-antibiotics-001" for doc in knowledge_base.documents):
        raise HTTPException(status_code=409, detail="The demo requires the bundled corpus.")
    return run_conflict_demo(knowledge_base)


@app.post("/v1/evaluations/offline", response_model=OfflineChallengeReport)
def run_offline_challenges() -> OfflineChallengeReport:
    """Always runs the bundled offline pipeline, not the backend's active model."""
    try:
        return OfflineChallengeRunner().run()
    except (ValueError, OSError):
        raise HTTPException(status_code=503, detail="The bundled offline challenge data is unavailable or invalid.") from None
