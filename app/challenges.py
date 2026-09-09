"""Offline challenge suite: never constructs or selects a model-backed pipeline."""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Literal

from pydantic import Field

from app.agents.verifier import VerifierAgent
from app.knowledge import KnowledgeBase
from app.models import Claim, ReviewRequest, StrictModel
from app.orchestrator import ReviewOrchestrator

ROOT = Path(__file__).resolve().parents[1]


class ChallengeSpec(StrictModel):
    id: str
    kind: Literal["retrieval", "verification", "abstention", "input_boundary"]
    category: str
    expected: str
    note: str
    known_limitation: bool = False
    query: str = ""
    top_k: int = Field(default=3, ge=1, le=8)
    expected_ids: list[str] = Field(default_factory=list)
    claim: Claim | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    request: ReviewRequest | None = None
    forbidden_output: str = ""


class ChallengeDataset(StrictModel):
    dataset_name: str
    notice: str
    cases: list[ChallengeSpec] = Field(min_length=1)


class ChallengeResult(StrictModel):
    case_id: str
    kind: str
    category: str
    expected: str
    observed: str
    outcome: Literal["passed", "known_limitation", "failed"]
    latency_ms: float
    note: str
    details: dict[str, Any]


class OfflineChallengeReport(StrictModel):
    dataset_name: str
    generated_at: str
    execution: str = "offline; explicit extractive pipeline; zero model API calls"
    model_api_calls: int = 0
    case_count: int
    passed_cases: int
    known_limitations: int
    failed_cases: int
    expectation_match_rate: float
    metric_note: str
    provenance: dict[str, Any]
    category_counts: dict[str, dict[str, int]]
    results: list[ChallengeResult]


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class OfflineChallengeRunner:
    def __init__(self, cases_path: Path | None = None, knowledge_path: Path | None = None):
        self.cases_path = cases_path or ROOT / "data/offline_challenges.json"
        self.knowledge_path = knowledge_path or ROOT / "data/guidelines.json"

    def run(self) -> OfflineChallengeReport:
        dataset = ChallengeDataset.model_validate_json(self.cases_path.read_text())
        kb = KnowledgeBase.from_json(self.knowledge_path)
        documents = {doc.id: doc for doc in kb.documents}
        pipeline = ReviewOrchestrator(
            kb
        )  # Explicit offline path, even if shell/backend uses a model.
        if len({case.id for case in dataset.cases}) != len(dataset.cases):
            raise ValueError("Challenge IDs must be unique.")
        results = []
        for case in dataset.cases:
            started = perf_counter()
            if case.kind == "retrieval":
                if not set(case.expected_ids) <= documents.keys():
                    raise ValueError("Challenge expected sources are absent from the corpus.")
                hits = kb.search(case.query, top_k=case.top_k)
                ids = {hit.document.id for hit in hits}
                observed = (
                    "all_expected_found" if set(case.expected_ids) <= ids else "missing_expected"
                )
                if not case.expected_ids:
                    observed = "unexpected_hits" if hits else "no_hits"
                details = {
                    "query": case.query,
                    "top_k": case.top_k,
                    "expected_ids": case.expected_ids,
                    "retrieved_ids": sorted(ids),
                }
            elif case.kind == "verification":
                if case.claim is None or not set(case.evidence_ids) <= documents.keys():
                    raise ValueError(
                        "Verification challenge requires a claim and available evidence."
                    )
                check = VerifierAgent().run(
                    [case.claim], {key: documents[key] for key in case.evidence_ids}
                )[0]
                observed = check.label.value
                details = {
                    "claim": case.claim.model_dump(mode="json"),
                    "evidence_ids": case.evidence_ids,
                    "check": check.model_dump(mode="json"),
                }
            else:
                if case.request is None:
                    raise ValueError("Pipeline challenge requires an input request.")
                response = pipeline.run(case.request)
                if case.kind == "input_boundary":
                    if not case.forbidden_output:
                        raise ValueError("Input boundary challenge requires an output marker.")
                    observed = (
                        "instruction_followed"
                        if any(case.forbidden_output in claim.text for claim in response.claims)
                        else "instruction_not_followed"
                    )
                else:
                    observed = "answer_emitted" if response.claims else "abstained"
                details = {
                    "request": case.request.model_dump(mode="json"),
                    "response": response.model_dump(mode="json"),
                }
            outcome = (
                "passed"
                if observed == case.expected
                else ("known_limitation" if case.known_limitation else "failed")
            )
            results.append(
                ChallengeResult(
                    case_id=case.id,
                    kind=case.kind,
                    category=case.category,
                    expected=case.expected,
                    observed=observed,
                    outcome=outcome,
                    latency_ms=round((perf_counter() - started) * 1000, 3),
                    note=case.note,
                    details=details,
                )
            )
        counts: dict[str, dict[str, int]] = {}
        for result in results:
            counts.setdefault(result.kind, {"passed": 0, "known_limitation": 0, "failed": 0})
            counts[result.kind][result.outcome] += 1
        passed = sum(r.outcome == "passed" for r in results)
        return OfflineChallengeReport(
            dataset_name=dataset.dataset_name,
            generated_at=datetime.now(UTC).isoformat(),
            case_count=len(results),
            passed_cases=passed,
            known_limitations=sum(r.outcome == "known_limitation" for r in results),
            failed_cases=sum(r.outcome == "failed" for r in results),
            expectation_match_rate=round(passed / len(results), 3),
            metric_note=dataset.notice
            + " Expectation match rate includes all cases in its denominator. "
            "Known limitations are NOT passes. No clinical accuracy or live-model quality is measured.",
            provenance={
                "knowledge_sha256": _digest(self.knowledge_path),
                "cases_sha256": _digest(self.cases_path),
                "code_sha256": {
                    str(path.relative_to(ROOT)): _digest(path)
                    for path in sorted((ROOT / "app").rglob("*.py"))
                },
            },
            category_counts=counts,
            results=results,
        )
