from __future__ import annotations

import json

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_unified_json() -> None:
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "code": 0,
        "message": "ok",
        "data": {"status": "healthy", "service": "ai-extractor-backend"},
    }


def test_parse_text_and_file_returns_structured_payload() -> None:
    response = client.post(
        "/api/parse",
        data={"text": "合同标题\n金额：100"},
        files={"files": ("contract.txt", b"hello", "text/plain")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 0
    assert body["message"] == "ok"
    assert body["data"]["result"]["summary"] == "合同标题\n金额：100"
    assert body["data"]["result"]["source"]["file_count"] == 1
    assert body["data"]["result"]["source"]["files"][0]["filename"] == "contract.txt"


def test_export_json_downloads_file() -> None:
    payload = {"data": {"summary": "demo", "fields": [{"key": "title", "value": "demo"}]}}
    response = client.post("/api/export/json", json=payload)

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith('attachment; filename="result.json"')
    assert json.loads(response.content) == payload["data"]
