from app.knowledge import KnowledgeBase
from app.settings import settings


def test_retriever_prioritizes_urgent_warning_signs() -> None:
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)

    hits = knowledge_base.search(
        "adult with difficulty breathing and chest pain needs urgent review",
        top_k=2,
    )

    assert hits
    assert hits[0].document.id == "cdc-respiratory-emergency-adults-001"
    assert "chest" in hits[0].matched_terms


def test_official_source_documents_include_provenance() -> None:
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)

    for document in knowledge_base.documents:
        assert document.content_kind == "official_source_paraphrase"
        assert document.is_paraphrase is True
        assert document.source_url.startswith("https://")
        assert document.source_accessed_at >= document.source_updated_at


def test_retriever_returns_no_hit_for_unrelated_query() -> None:
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)

    hits = knowledge_base.search("quantum telescope orbital mechanics", top_k=3)

    assert hits == []
