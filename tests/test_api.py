from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_endpoint() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["knowledge_documents"] == 6
    assert response.json()["reasoner_mode"] == "extractive"


def test_review_endpoint_validates_input() -> None:
    response = client.post(
        "/v1/reviews",
        json={
            "case_id": "bad",
            "patient_summary": "short",
            "question": "why?",
            "top_k": 100,
        },
    )

    assert response.status_code == 422
