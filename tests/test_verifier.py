from app.agents.conflict_detector import ConflictDetector
from app.agents.verifier import VerifierAgent
from app.knowledge import KnowledgeBase
from app.models import Claim, VerificationLabel
from app.settings import settings


def test_verifier_marks_exact_guidance_as_supported() -> None:
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)
    document = knowledge_base.documents[0]
    claim = Claim(
        claim_id="claim-supported",
        text=document.recommendation,
        category=document.category,
        citation_ids=[document.id],
        confidence=0.9,
    )

    result = VerifierAgent().run([claim], {document.id: document})[0]

    assert result.label == VerificationLabel.supported
    assert result.score == 1.0


def test_unsupported_high_confidence_claim_creates_conflict() -> None:
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)
    document = knowledge_base.documents[0]
    claim = Claim(
        claim_id="claim-unsupported",
        text="Schedule an unrelated imaging procedure next month.",
        category="test",
        citation_ids=[document.id],
        confidence=0.91,
    )

    verification = VerifierAgent().run([claim], {document.id: document})
    conflicts = ConflictDetector().run([claim], verification)

    assert verification[0].label == VerificationLabel.unsupported
    assert conflicts[0].severity.value == "high"


def test_explicitly_rejected_claim_is_contradicted() -> None:
    knowledge_base = KnowledgeBase.from_json(settings.knowledge_base_path)
    document = next(
        item
        for item in knowledge_base.documents
        if item.id == "cdc-bronchitis-antibiotics-001"
    )
    claim = Claim(
        claim_id="claim-contradicted",
        text="Recommend routine antibiotics for uncomplicated acute bronchitis.",
        category="antibiotic_stewardship",
        citation_ids=[document.id],
        confidence=0.88,
    )

    verification = VerifierAgent().run([claim], {document.id: document})
    conflicts = ConflictDetector().run([claim], verification)

    assert verification[0].label == VerificationLabel.contradicted
    assert conflicts[0].severity.value == "critical"
