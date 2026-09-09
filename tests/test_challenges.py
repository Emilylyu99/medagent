import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app import main
from app.agents.reasoner import OpenAIReasonerAgent
from app.challenges import OfflineChallengeRunner
from scripts.offline_eval import render_markdown


def test_offline_results_expose_limitations_not_perfect_scores():
    report = OfflineChallengeRunner().run()
    assert report.case_count == 20
    assert report.passed_cases == 15
    assert report.known_limitations == 5
    assert report.failed_cases == 0
    assert report.expectation_match_rate == 0.75
    assert report.model_api_calls == 0
    assert len(report.provenance["cases_sha256"]) == 64
    assert {r.case_id for r in report.results if r.outcome == "known_limitation"} == {
        "verify-valid-paraphrase",
        "verify-novel-negation",
        "abstain-keyword-trap",
        "abstain-baking",
        "abstain-insufficient-details",
    }
    for result in report.results:
        if result.outcome == "known_limitation":
            assert result.expected != result.observed
    text = render_markdown(report)
    assert "75%" in text and "15 passed" in text and "5 known limitations" in text


def test_offline_endpoint_never_uses_active_model(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("The offline suite must not initialize or call a model")

    monkeypatch.setenv("REASONER_MODE", "openai")
    monkeypatch.setenv("PIPELINE_MODE", "adaptive")
    monkeypatch.setattr(OpenAIReasonerAgent, "__init__", forbidden)
    monkeypatch.setattr(main.orchestrator, "run", forbidden)
    response = TestClient(main.app).post("/v1/evaluations/offline")
    assert response.status_code == 200
    assert response.json()["model_api_calls"] == 0
    assert response.json()["case_count"] == 20


def test_unexpected_failure_is_not_automatically_a_known_gap(tmp_path):
    dataset = {
        "dataset_name": "regression-test",
        "notice": "Synthetic test fixture",
        "cases": [
            {
                "id": "wrong-expectation",
                "kind": "retrieval",
                "category": "test",
                "expected": "no_hits",
                "note": "Intentionally inconsistent expectation.",
                "query": "privacy identifiers",
                "expected_ids": [],
            }
        ],
    }
    path = tmp_path / "challenge.json"
    path.write_text(json.dumps(dataset))
    report = OfflineChallengeRunner(cases_path=path).run()
    assert report.failed_cases == 1 and report.known_limitations == 0
    assert report.expectation_match_rate == 0


def test_duplicate_ids_are_rejected(tmp_path):
    path = tmp_path / "challenge.json"
    dataset = json.loads(
        (Path(__file__).resolve().parents[1] / "data/offline_challenges.json").read_text()
    )
    dataset["cases"].append(dataset["cases"][0])
    path.write_text(json.dumps(dataset))
    with pytest.raises(ValueError, match="unique"):
        OfflineChallengeRunner(cases_path=path).run()


def test_report_export_and_no_overwrite(monkeypatch, tmp_path):
    from scripts import offline_eval

    output = tmp_path / "report"
    monkeypatch.setattr("sys.argv", ["offline_eval", "--output", str(output)])
    offline_eval.main()
    report = json.loads((output / "report.json").read_text())
    assert report["expectation_match_rate"] == 0.75
    before = (output / "report.json").read_bytes()
    with pytest.raises(SystemExit):
        offline_eval.main()
    assert before == (output / "report.json").read_bytes()


def test_ui_offline_checks_and_rerun_do_not_use_model(monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    client = TestClient(main.app)
    calls = []
    monkeypatch.setattr(httpx, "get", lambda url, **kwargs: client.get("/health"))

    def send(url, **kwargs):
        calls.append(url)
        assert url.endswith("/v1/evaluations/offline")
        return client.post("/v1/evaluations/offline")

    monkeypatch.setattr(httpx, "post", send)
    ui = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/app.py")).run()
    assert not calls
    next(b for b in ui.button if b.label == "Run Offline Checks").click().run()
    assert not ui.exception
    assert ui.session_state["offline_evaluation"]["known_limitations"] == 5
    values = {m.label: m.value for m in ui.metric}
    assert values["Checks passed"] == "15 / 20"
    assert values["Known limitations"] == "5"
    assert values["Model API calls"] == "0"
    ui.run()
    assert len(calls) == 1
