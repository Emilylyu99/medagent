"""Export a reproducible offline engineering report; never initializes a model provider."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from datetime import UTC, datetime
from pathlib import Path

from app.demo import run_conflict_demo
from app.evaluation import EvaluationRunner
from app.knowledge import KnowledgeBase
from app.models import ReviewRequest
from app.orchestrator import ReviewOrchestrator

ROOT = Path(__file__).resolve().parents[1]


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_report() -> dict:
    knowledge = ROOT / "data/guidelines.json"
    cases = ROOT / "data/evaluation_cases.json"
    kb = KnowledgeBase.from_json(knowledge)
    pipeline = ReviewOrchestrator(kb)  # Explicit offline baseline, independent of shell settings.
    report = EvaluationRunner(pipeline, cases).run().model_dump(mode="json")
    demo = run_conflict_demo(kb)
    out_of_scope = pipeline.run(
        ReviewRequest(
            case_id="release-out-of-scope",
            patient_summary="Orbital mechanics and telescope mirrors aboard a spacecraft.",
            question="Which launch trajectory is most efficient?",
            top_k=2,
        )
    )
    expected_flags = {"injected-contradiction", "injected-missing-source"}
    smoke_checks = {
        "injected_errors_detected": {c.claim_id for c in demo.conflicts} == expected_flags,
        "unrelated_input_abstains": out_of_scope.status == "no_evidence"
        and not out_of_scope.claims,
    }
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "execution": "offline; explicit extractive reasoner; no model API calls",
        "environment": {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
        },
        "provenance": {
            "knowledge_sha256": digest(knowledge),
            "cases_sha256": digest(cases),
            "code_sha256": {
                str(p.relative_to(ROOT)): digest(p) for p in sorted((ROOT / "app").rglob("*.py"))
            },
        },
        "evaluation": report,
        "smoke_checks": smoke_checks,
        "conflict_demo": demo.model_dump(mode="json"),
        "abstention_demo": out_of_scope.model_dump(mode="json"),
    }


def render_markdown(bundle: dict) -> str:
    report = bundle["evaluation"]
    lines = [
        "# MedAgent — offline baseline results",
        "",
        f"Generated: {bundle['generated_at']}",
        "",
        "**Scope:** Six curated synthetic smoke cases, not an independent clinical benchmark.",
        "The extractive reasoner copies curated review points; perfect text matching is expected.",
        "These results do not establish medical accuracy or a real-model hallucination rate.",
        "",
        "| Metric | Observed value |",
        "| --- | --- |",
        f"| Retrieval Recall@K (K=1) | {report['mean_retrieval_recall']:.0%} |",
        f"| Expected citation-ID precision | {report['mean_citation_precision']:.0%} |",
        f"| Rule text-match rate | {report['mean_supported_claim_rate']:.0%} |",
        f"| Cases with review flags | {report['conflict_case_rate']:.0%} |",
        f"| Mean pipeline latency | {report['mean_latency_ms']:.3f} ms |",
        f"| P95 pipeline latency | {report['p95_latency_ms']:.3f} ms |",
        "| Model API cost | $0.00 — no model calls |",
        "| Clinical accuracy / independent hallucination rate | Not measured |",
        "",
        "Latency is a single in-process run over a six-chunk in-memory corpus. It excludes",
        "startup, network, browser rendering, and model latency. P95 uses the nearest-rank method",
        "(the slowest case at this sample size). Values vary by machine and run.",
        "",
        "## Per-case results",
        "",
        "| Case | Recall@1 | Citation precision | Text match | Flags | Latency (ms) |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    for row in report["results"]:
        lines.append(
            f"| {row['case_id']} | {row['retrieval_recall']:.0%} | "
            f"{row['citation_precision']:.0%} | {row['supported_claim_rate']:.0%} | "
            f"{row['conflict_count']} | {row['latency_ms']:.3f} |"
        )
    lines += ["", "## Separate behavior checks", ""]
    for name, passed in bundle["smoke_checks"].items():
        lines.append(f"- {name}: {'PASS' if passed else 'FAIL'}")
    lines += [
        "",
        "The error fixture deliberately injects two errors. Detecting them is not a",
        "measurement of natural model failures. The unrelated-input check is not a clinical",
        "out-of-distribution benchmark.",
        "",
        "## Reproduce",
        "",
        "Run `make report` from the repository root. It always uses the",
        "offline reasoner, even if the shell is configured for a model provider.",
        "",
        "See [report.json](report.json) for inputs, outputs, source/code SHA-256 hashes,",
        "runtime metadata, and full per-case measurements.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    # Each report has its own directory; avoid overwriting a previous observation.
    args.output.mkdir(parents=True, exist_ok=False)
    bundle = collect_report()
    (args.output / "report.json").write_text(json.dumps(bundle, indent=2) + "\n")
    (args.output / "README.md").write_text(render_markdown(bundle))
    print(args.output.resolve())
    if not all(bundle["smoke_checks"].values()):
        raise SystemExit("One or more behavior checks failed; inspect report.json.")


if __name__ == "__main__":
    main()
