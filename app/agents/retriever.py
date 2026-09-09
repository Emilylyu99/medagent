from app.knowledge import KnowledgeBase
from app.models import RetrievalHit, ReviewRequest


class RetrieverAgent:
    def __init__(self, knowledge_base: KnowledgeBase) -> None:
        self.knowledge_base = knowledge_base

    def run(self, request: ReviewRequest) -> list[RetrievalHit]:
        query = f"{request.patient_summary}\n{request.question}"
        return self.knowledge_base.search(query, top_k=request.top_k)

