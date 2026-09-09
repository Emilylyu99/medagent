from __future__ import annotations

import re

from app.models import (
    Claim,
    ClaimVerification,
    GuidelineDocument,
    VerificationLabel,
)


def _normalize(text: str) -> str:
    # Preserve word order, numbers and negation. Bag-of-words overlap is not entailment.
    return " ".join(text.casefold().split()).rstrip(".!?")


class VerifierAgent:
    """Conservative offline check; paraphrases require independent human/semantic review."""

    def run(
        self,
        claims: list[Claim],
        documents_by_id: dict[str, GuidelineDocument],
    ) -> list[ClaimVerification]:
        return [self._verify_claim(claim, documents_by_id) for claim in claims]

    def _verify_claim(
        self,
        claim: Claim,
        documents_by_id: dict[str, GuidelineDocument],
    ) -> ClaimVerification:
        evidence = [
            documents_by_id[citation_id]
            for citation_id in claim.citation_ids
            if citation_id in documents_by_id
        ]
        evidence_ids = [document.id for document in evidence]
        if not claim.citation_ids or len(evidence) != len(claim.citation_ids):
            return ClaimVerification(
                claim_id=claim.claim_id,
                label=VerificationLabel.unsupported,
                score=0,
                evidence_ids_checked=evidence_ids,
                rationale="One or more citations are missing from the retrieved evidence.",
            )
        normalized = _normalize(claim.text)
        contradiction = any(
            normalized == _normalize(statement)
            for document in evidence
            for statement in document.contradicted_statements
        )
        supported = bool(normalized) and any(
            normalized == _normalize(statement)
            for document in evidence
            for statement in [
                document.recommendation,
                document.text,
                *re.split(r"(?<=[.!?])\s+", document.text),
            ]
        )
        if contradiction:
            return ClaimVerification(
                claim_id=claim.claim_id,
                label=VerificationLabel.contradicted,
                score=1.0,
                evidence_ids_checked=evidence_ids,
                rationale="Exact match to a curator-authored counterexample; not a semantic model judgment.",
            )
        if supported:
            return ClaimVerification(
                claim_id=claim.claim_id,
                label=VerificationLabel.supported,
                score=1.0,
                evidence_ids_checked=evidence_ids,
                rationale="Exact text match to a curated evidence sentence or review point; applicability is not assessed.",
            )
        reason = (
            "The claim has no valid citation in the retrieved evidence."
            if not evidence
            else "No exact evidence match. This rule cannot establish semantic support; human review is required."
        )
        return ClaimVerification(
            claim_id=claim.claim_id,
            label=VerificationLabel.unsupported,
            score=0.0,
            evidence_ids_checked=evidence_ids,
            rationale=reason,
        )
