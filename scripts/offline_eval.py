"""Run and export the offline engineering challenge suite. No model configuration is used."""

from __future__ import annotations

import argparse
from pathlib import Path

from app.challenges import OfflineChallengeReport, OfflineChallengeRunner


def render_markdown(report: OfflineChallengeReport) -> str:
    lines = [
        "# MedAgent — offline engineering challenge report",
        "",
        f"Generated: {report.generated_at}",
        "",
        report.execution,
        "",
        (
            f"{report.case_count} cases: **{report.passed_cases} passed**, "
            f"**{report.known_limitations} known limitations**, **{report.failed_cases} unexpected failures**."
        ),
        f"Expectation match rate: {report.expectation_match_rate:.0%}. Known limitations are not passes.",
        "",
        report.metric_note,
        "",
        "| Case | Kind | Expected | Observed | Outcome |",
        "| --- | --- | --- | --- | --- |",
    ]
    for result in report.results:
        lines.append(
            f"| {result.case_id} | {result.kind} | {result.expected} | {result.observed} | {result.outcome} |"
        )
    lines += ["", "## Limitations and failures", ""]
    for result in report.results:
        if result.outcome != "passed":
            lines.append(f"- **{result.case_id}**: {result.note}")
    lines += [
        "",
        "## Reproduce and inspect",
        "",
        "Run `make offline-eval` from the project root. It ignores model-related environment settings.",
        "The command exits nonzero on unexpected failures, but reports known gaps without hiding them.",
        "[report.json](report.json) contains inputs, all observed outputs, checker explanations,",
        "per-case in-process latency, and source/dataset/code SHA-256 hashes.",
        "",
        "This development suite complements the six earlier retrieval smoke cases. It is not an",
        "independently reviewed medical benchmark, a live LLM evaluation, or evidence that an",
        "extractive pipeline resists LLM prompt injection. No patient data is used.",
        "",
    ]
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Choose a new output directory; existing reports are never overwritten.")
    report = OfflineChallengeRunner().run()
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / "report.json").write_text(report.model_dump_json(indent=2) + "\n")
    (args.output / "README.md").write_text(render_markdown(report))
    print(
        f"Offline: {report.passed_cases}/{report.case_count} matched; "
        f"{report.known_limitations} known limitations; {report.failed_cases} unexpected failures; 0 API calls."
    )
    print(args.output.resolve())
    if report.failed_cases:
        raise SystemExit("Unexpected challenge failures; inspect the report before continuing.")


if __name__ == "__main__":
    main()
