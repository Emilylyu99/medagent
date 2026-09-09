from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.agents.verifier import VerifierAgent
from app.main import app, knowledge_base, orchestrator
from app.models import Claim, ReviewRequest, VerificationLabel

client = TestClient(app)


def test_demo_detects_both_errors_and_does_not_change_normal_reviews():
    demo = client.post("/v1/demos/conflict").json()
    assert demo["is_demo"] is True
    assert demo["status"] == "needs_human_review"
    assert {c["claim_id"] for c in demo["conflicts"]} == {
        "injected-contradiction",
        "injected-missing-source",
    }
    assert [step["component"] for step in demo["trace"]] == [
        "retriever",
        "reasoner",
        "verifier",
        "conflict_detector",
    ]
    normal = client.post(
        "/v1/reviews",
        json={
            "case_id": "normal-after-demo",
            "patient_summary": "Synthetic adult with uncomplicated acute bronchitis.",
            "question": "Should routine antibiotics be recommended?",
            "top_k": 1,
        },
    ).json()
    assert normal["is_demo"] is False
    assert normal["conflicts"] == []
    assert normal["metrics"]["reasoner_mode"] == "extractive"


def test_negation_and_missing_citation_do_not_pass_on_word_overlap():
    doc = knowledge_base.documents[0]
    for text, ids in [
        ("Do not " + doc.recommendation, [doc.id]),
        (doc.recommendation, [doc.id, "invented"]),
    ]:
        claim = Claim(
            claim_id="tampered", text=text, category="test", citation_ids=ids, confidence=0.9
        )
        result = VerifierAgent().run([claim], {doc.id: doc})[0]
        assert result.label == VerificationLabel.unsupported


def test_retrieval_is_preserved_independently_of_three_claim_limit():
    response = orchestrator.run(
        ReviewRequest(
            case_id="all-topics",
            patient_summary="Adult bronchitis pneumonia respiratory emergency privacy HIPAA identifiers diabetes.",
            question="Review all relevant evidence.",
            top_k=6,
        )
    )
    assert len(response.retrieved_citations) == 6
    assert len(response.citations) == 3


def test_ui_demo_history_evaluation_and_failed_request(monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")
    monkeypatch.setattr(httpx, "get", lambda url, **kw: client.get("/health"))
    monkeypatch.setattr(
        httpx,
        "post",
        lambda url, **kw: client.post(
            "/" + url.split("/", 3)[3],
            json=kw.get("json"),
        ),
    )
    app_test = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/app.py"))
    app_test.run()
    assert not app_test.exception
    assert {
        "Ask",
        "Evaluate",
        "Cases",
        "Playground",
        "About",
        "Final Answer",
        "Agent Outputs",
        "Conflict Analysis",
    } == {tab.label for tab in app_test.tabs}
    next(b for b in app_test.button if b.label == "Run Conflict Demo").click().run()
    assert not app_test.exception
    assert app_test.session_state["active_review"]["result"]["is_demo"]
    assert len(app_test.session_state["history"]) == 1
    app_test.radio(key="example").set_value("Out-of-scope question").run()
    assert "active_review" not in app_test.session_state
    assert "Orbital" in app_test.text_area(key="case_summary").value
    next(b for b in app_test.button if b.label == "Run Agents").click().run()
    assert not app_test.exception
    assert app_test.session_state["active_review"]["result"]["status"] == "no_evidence"
    assert len(app_test.session_state["history"]) == 2
    next(b for b in app_test.button if b.label == "Run Evaluation").click().run()
    assert not app_test.exception
    assert app_test.session_state["evaluation"]["case_count"] == 6
    # A rerun caused by an unrelated widget must retain the previous result.
    app_test.run()
    assert len(app_test.session_state["history"]) == 2

    def fail(*args, **kwargs):
        raise httpx.ConnectError("test service unavailable")

    monkeypatch.setattr(httpx, "post", fail)
    next(b for b in app_test.button if b.label == "Run Agents").click().run()
    assert not app_test.exception
    assert "active_review" not in app_test.session_state
    assert len(app_test.session_state["history"]) == 2


def test_english_ui_new_case_validation_and_restore(monkeypatch):
    import re

    testing = pytest.importorskip("streamlit.testing.v1")
    source_path = Path(__file__).resolve().parents[1] / "ui/app.py"
    assert not re.search(r"[\u4e00-\u9fff]", source_path.read_text())
    monkeypatch.setattr(httpx, "get", lambda url, **kw: client.get("/health"))
    calls = []

    def send(url, **kwargs):
        calls.append(url)
        return client.post("/" + url.split("/", 3)[3], json=kwargs.get("json"))

    monkeypatch.setattr(httpx, "post", send)
    ui = testing.AppTest.from_file(str(source_path)).run()
    assert not calls  # Opening tabs must not execute the model or evaluations.
    next(b for b in ui.button if b.label == "Run Agents").click().run()
    assert not ui.exception
    submitted = ui.session_state["active_review"]["input"]
    assert len(calls) == 1
    assert {m.label: m.value for m in ui.metric}["Model API cost"] == "$0.00"
    next(b for b in ui.button if b.label == "＋ New Case").click().run()
    assert not ui.exception
    assert ui.text_area(key="case_summary").value == ""
    assert "active_review" not in ui.session_state
    assert len(ui.session_state["history"]) == 1
    next(b for b in ui.button if b.label == "Run Agents").click().run()
    assert not ui.exception
    assert len(calls) == 1  # Invalid empty input is rejected without an API request.
    ui.button(key="restore-0").click().run()
    assert not ui.exception
    assert ui.text_area(key="case_summary").value == submitted["patient_summary"]
    assert ui.text_input(key="review_question").value == submitted["question"]
    assert ui.session_state["active_review"]["input"] == submitted
    next(b for b in ui.button if b.label == "Clear").click().run()
    assert not ui.exception
    assert ui.text_area(key="case_summary").value == ""
    assert len(ui.session_state["history"]) == 1


def test_ui_disconnected_backend_disables_execution(monkeypatch):
    testing = pytest.importorskip("streamlit.testing.v1")

    def disconnected(*args, **kwargs):
        raise httpx.ConnectError("offline")

    monkeypatch.setattr(httpx, "get", disconnected)
    ui = testing.AppTest.from_file(str(Path(__file__).resolve().parents[1] / "ui/app.py")).run()
    assert not ui.exception
    assert any("Backend unavailable" in error.value for error in ui.error)
    for label in ("Run Agents", "Run Evaluation", "Run Conflict Demo"):
        assert next(b for b in ui.button if b.label == label).disabled
