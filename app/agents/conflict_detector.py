from __future__ import annotations

from app.models import (
    Claim,
    ClaimVerification,
    Conflict,
    ConflictSeverity,
    VerificationLabel,
)


class ConflictDetector:
    def run(
        self,
        claims: list[Claim],
        verification: list[ClaimVerification],
    ) -> list[Conflict]:
        claims_by_id = {claim.claim_id: claim for claim in claims}
        conflicts: list[Conflict] = []

        for result in verification:
            claim = claims_by_id[result.claim_id]
            if result.label == VerificationLabel.contradicted:
                conflicts.append(
                    Conflict(
                        claim_id=claim.claim_id,
                        severity=ConflictSeverity.critical,
                        reason="The verifier found that the evidence contradicts this claim.",
                    )
                )
            elif result.label == VerificationLabel.unsupported:
                severity = (
                    ConflictSeverity.high
                    if claim.confidence >= 0.75
                    else ConflictSeverity.medium
                )
                conflicts.append(
                    Conflict(
                        claim_id=claim.claim_id,
                        severity=severity,
                        reason="The reasoner emitted a claim that is not adequately grounded.",
                    )
                )

        return conflicts

