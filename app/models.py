from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewRequest(StrictModel):
    case_id: str = Field(min_length=1, max_length=80)
    patient_summary: str = Field(min_length=10, max_length=4_000)
    question: str = Field(min_length=5, max_length=1_000)
    top_k: int = Field(default=3, ge=1, le=8)


class GuidelineDocument(StrictModel):
    id: str
    title: str
    category: str
    source: str
    publisher: str
    source_url: str
    source_updated_at: date
    source_accessed_at: date
    content_kind: Literal["official_source_paraphrase", "synthetic_protocol"]
    is_paraphrase: bool
    jurisdiction: str
    version: str
    text: str
    recommendation: str
    keywords: list[str] = Field(default_factory=list)
    contradicted_statements: list[str] = Field(default_factory=list)


class RetrievalHit(StrictModel):
    document: GuidelineDocument
    score: float
    matched_terms: list[str]


class Citation(StrictModel):
    citation_id: str
    title: str
    source: str
    publisher: str
    source_url: str
    source_updated_at: date
    source_accessed_at: date
    content_kind: Literal["official_source_paraphrase", "synthetic_protocol"]
    is_paraphrase: bool
    jurisdiction: str
    version: str
    excerpt: str
    review_point: str = ""
    retrieval_score: float
    matched_terms: list[str]


class Claim(StrictModel):
    claim_id: str
    text: str
    category: str
    citation_ids: list[str]
    confidence: float = Field(ge=0.0, le=1.0)


class VerificationLabel(str, Enum):
    supported = "supported"
    unsupported = "unsupported"
    contradicted = "contradicted"


class EvidenceQuote(StrictModel):
    citation_id: str = Field(min_length=1, max_length=120)
    quote: str = Field(min_length=15, max_length=1000)


class ClaimVerification(StrictModel):
    claim_id: str
    label: VerificationLabel
    score: float = Field(ge=0.0, le=1.0)
    evidence_ids_checked: list[str]
    rationale: str
    evidence_quotes: list[EvidenceQuote] = Field(default_factory=list)


class ConflictSeverity(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"
    critical = "critical"


class Conflict(StrictModel):
    claim_id: str
    severity: ConflictSeverity
    reason: str
    requires_human_review: bool = True


class TraceStep(StrictModel):
    component: str
    status: str
    duration_ms: float
    details: dict[str, Any] = Field(default_factory=dict)


class PipelineMetrics(StrictModel):
    retrieval_ms: float
    reasoning_ms: float
    verification_ms: float
    conflict_detection_ms: float = 0.0
    total_ms: float
    retrieved_chunks: int
    generated_claims: int
    supported_claim_rate: float
    reasoner_mode: str
    model_name: str | None = None
    input_tokens: int
    output_tokens: int
    token_count_source: str
    pipeline_mode: str = "baseline"
    verification_method: str = "exact_text_and_known_counterexamples_v2"
    planning_ms: float = 0.0
    model_calls: int = 0
    search_calls: int = 1
    repair_attempts: int = 0
    initial_supported_claim_rate: float | None = None
    withheld_claims: int = 0


class ReviewAttempt(StrictModel):
    attempt: int
    claims: list[Claim]
    verification: list[ClaimVerification] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    verification_completed: bool = False


class ProviderFailure(StrictModel):
    category: Literal[
        "credits_exhausted", "quota_exceeded", "spend_limit", "usage_limit",
        "rate_limited", "rate_limit_or_quota", "timeout", "connection",
        "authentication", "permission", "model_unavailable", "invalid_request",
        "service_unavailable", "unknown",
    ]
    code: str | None = None
    http_status: int | None = None
    request_id: str | None = None
    retry_after_seconds: float | None = None
    retryable: bool = False
    message: str
    suggested_action: str


class ReviewResponse(StrictModel):
    case_id: str
    is_demo: bool = False
    retrieved_citations: list[Citation] = Field(default_factory=list)
    status: str
    summary: str
    claims: list[Claim]
    uncertainties: list[str]
    citations: list[Citation]
    verification: list[ClaimVerification]
    conflicts: list[Conflict]
    metrics: PipelineMetrics
    trace: list[TraceStep]
    disclaimer: str
    attempts: list[ReviewAttempt] = Field(default_factory=list)
    clarification_questions: list[str] = Field(default_factory=list)
    stop_reason: str | None = None
    failure: ProviderFailure | None = None


class EvaluationCaseResult(StrictModel):
    case_id: str
    expected_citation_ids: list[str]
    retrieved_citation_ids: list[str]
    retrieval_recall: float
    citation_precision: float
    supported_claim_rate: float
    conflict_count: int
    latency_ms: float
    initial_supported_claim_rate: float | None = None
    status: str = "unknown"
    repair_attempts: int = 0
    released_claims: int = 0
    model_calls: int = 0
    search_calls: int = 1
    input_tokens: int = 0
    output_tokens: int = 0
    token_count_source: str = "unavailable"


class EvaluationReport(StrictModel):
    dataset_name: str
    case_count: int
    mean_retrieval_recall: float
    mean_citation_precision: float
    mean_supported_claim_rate: float
    hallucination_rate: float
    mean_latency_ms: float
    p95_latency_ms: float = 0.0
    conflict_case_rate: float = 0.0
    reasoner_mode: str = "extractive"
    pipeline_mode: str = "baseline"
    initial_flagged_claim_rate: float | None = None
    abstention_case_rate: float = 0.0
    error_case_rate: float = 0.0
    metric_note: str = (
        "Small synthetic smoke set. Grounding and hallucination_rate are rule-based proxies, "
        "not clinical accuracy or an independently measured hallucination rate."
    )
    results: list[EvaluationCaseResult]
