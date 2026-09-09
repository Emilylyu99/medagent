import json

from scripts.export_report import collect_report, render_markdown


def test_report_is_offline_and_includes_provenance(monkeypatch):
    monkeypatch.setenv("REASONER_MODE", "openai")
    bundle = collect_report()
    assert bundle["evaluation"]["reasoner_mode"] == "extractive"
    assert bundle["evaluation"]["case_count"] == 6
    assert all(bundle["smoke_checks"].values())
    assert len(bundle["provenance"]["knowledge_sha256"]) == 64
    assert "app/orchestrator.py" in bundle["provenance"]["code_sha256"]
    text = render_markdown(bundle)
    assert "Not measured" in text
    assert "not an independent clinical benchmark" in text
    assert all(row["case_id"] in text for row in bundle["evaluation"]["results"])
    assert "openai_api_key" not in json.dumps(bundle).lower()
