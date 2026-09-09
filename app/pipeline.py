from app.adaptive import AdaptiveReviewOrchestrator
from app.agents.reasoner import OpenAIReasonerAgent, ReasonerAgent, ReasonerConfigurationError
from app.knowledge import KnowledgeBase
from app.orchestrator import ReviewOrchestrator


def build_pipeline(
    mode: str,
    knowledge_base: KnowledgeBase,
    reasoner: ReasonerAgent,
) -> ReviewOrchestrator | AdaptiveReviewOrchestrator:
    if mode == "baseline":
        return ReviewOrchestrator(knowledge_base, reasoner)
    if mode == "adaptive" and isinstance(reasoner, OpenAIReasonerAgent):
        return AdaptiveReviewOrchestrator(knowledge_base, reasoner)
    raise ReasonerConfigurationError(
        "PIPELINE_MODE must be baseline or adaptive. Adaptive requires REASONER_MODE=openai "
        "and configured OPENAI_MODEL / OPENAI_API_KEY. No silent offline fallback is used."
    )
