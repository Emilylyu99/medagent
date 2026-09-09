"""Dry-run by default. Explicit opt-in required for billable adaptive evaluation."""

from __future__ import annotations

import argparse
import json
import os
from datetime import UTC, datetime
from pathlib import Path

from app.adaptive import AdaptiveReviewOrchestrator
from app.agents.reasoner import OpenAIReasonerAgent, ReasonerConfigurationError
from app.agents.structured import AgentLimits
from app.knowledge import KnowledgeBase
from app.models import ReviewRequest
from app.orchestrator import ReviewOrchestrator
from scripts.export_report import ROOT, digest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--allow-model-calls", action="store_true")
    parser.add_argument("--case-limit", type=int, default=1)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    knowledge_path = ROOT / "data/guidelines.json"
    cases_path = ROOT / "data/evaluation_cases.json"
    dataset = json.loads(cases_path.read_text())
    if not 1 <= args.case_limit <= len(dataset["cases"]):
        parser.error(f"--case-limit must be between 1 and {len(dataset['cases'])}")
    cases = dataset["cases"][: args.case_limit]
    limits = AgentLimits()
    print(
        json.dumps(
            {
                "execution": "LIVE MODEL CALLS"
                if args.allow_model_calls
                else "DRY RUN; no model calls",
                "cases": len(cases),
                "max_model_calls": len(cases) * limits.max_model_calls,
                "model_configured": bool(os.getenv("OPENAI_MODEL")),
                "api_key_configured": bool(os.getenv("OPENAI_API_KEY")),
                "model_quality_measured": False,
            },
            indent=2,
        )
    )
    if not args.allow_model_calls:
        return
    if args.output is None or args.output.exists():
        parser.error("Live runs require --output pointing to a NEW report directory.")
    try:
        reasoner = OpenAIReasonerAgent(
            model=os.getenv("OPENAI_MODEL", ""),
            api_key=os.getenv("OPENAI_API_KEY"),
        )
    except ReasonerConfigurationError as exc:
        parser.error(str(exc))
    kb = KnowledgeBase.from_json(knowledge_path)
    pipelines = {
        "offline_baseline": ReviewOrchestrator(kb),
        "adaptive": AdaptiveReviewOrchestrator(kb, reasoner, limits),
    }
    args.output.mkdir(parents=True, exist_ok=False)
    bundle = {
        "generated_at": datetime.now(UTC).isoformat(),
        "dataset_name": dataset["dataset_name"],
        "model": reasoner.model,
        "note": (
            "Development smoke comparison, not an independent benchmark. Checker scores are "
            "not clinical accuracy. Baseline uses rules; adaptive uses a fallible model judge. "
            "Do not compare these support scores as if they share an independent ground truth. "
            "Review raw answers, initial failures, abstentions and errors; obtain human labels. "
            "No dollar estimate without a model price configuration."
        ),
        "limits_per_adaptive_case": vars(limits),
        "provenance": {
            "knowledge_sha256": digest(knowledge_path),
            "cases_sha256": digest(cases_path),
            "code_sha256": {
                str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / "app").rglob("*.py"))
            },
        },
        "results": [],
    }
    for item in cases:
        request = ReviewRequest.model_validate(item["request"])
        row = {"request": item["request"], "expected_citation_ids": item["expected_citation_ids"]}
        for name, pipeline in pipelines.items():
            row[name] = pipeline.run(request).model_dump(mode="json")
        bundle["results"].append(row)
        # Checkpoint every case. No credentials are included in exported records.
        (args.output / "comparison.json").write_text(json.dumps(bundle, indent=2) + "\n")
        adaptive = row["adaptive"]
        print(
            f"{request.case_id}: {adaptive['status']} ({adaptive['metrics']['model_calls']} model calls)"
        )
        if adaptive["status"] in {"model_error", "budget_exhausted"}:
            if adaptive.get("failure"):
                failure = adaptive["failure"]
                print(f"{failure['category']}: {failure['message']}")
                print(failure["suggested_action"])
            raise SystemExit(
                "Stopped after a model/budget error; inspect comparison.json before retrying."
            )
    print(args.output.resolve())


if __name__ == "__main__":
    main()
