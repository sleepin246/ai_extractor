from __future__ import annotations

import json
from typing import Any

from fastapi.testclient import TestClient

from app import main
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


def test_parse_image_without_vision_api_returns_standard_json(monkeypatch: Any) -> None:
    monkeypatch.delenv(main.VISION_API_URL_ENV, raising=False)

    response = client.post(
        "/api/parse",
        data={"text": "请抽取图片"},
        files={"files": ("form.png", b"fake-image", "image/png")},
    )

    assert response.status_code == 200
    result = response.json()["data"]["result"]
    assert set(result) == {"document_info", "sections", "raw_text", "warnings"}
    assert result["document_info"]["confidence"] == 0
    assert result["sections"][0]["fields"][0] == {
        "field_name": "form.png",
        "field_value": "",
        "status": "uncertain",
        "source_hint": "uploaded image: form.png",
    }
    assert main.VISION_API_URL_ENV in result["warnings"][0]


def test_parse_image_uses_provider_neutral_json_result(monkeypatch: Any) -> None:
    async def fake_call_vision_model_api(text: str, image_files: list[dict[str, Any]]) -> dict[str, Any]:
        assert text == "识别表格"
        assert image_files[0]["filename"] == "table.jpg"
        assert image_files[0]["content"] == b"image-bytes"
        return main.normalize_extraction_result(
            {
                "document_info": {"title": "巡检表", "id": "A-1", "confidence": 0.87},
                "sections": [
                    {
                        "section_name": "基础信息",
                        "fields": [
                            {
                                "field_name": "温度",
                                "field_value": "23 °C",
                                "status": "filled",
                                "source_hint": "表格第一行",
                            },
                            {
                                "field_name": "备注",
                                "field_value": "",
                                "status": "empty",
                                "source_hint": "底部备注栏",
                            },
                        ],
                    }
                ],
                "raw_text": "温度 23 °C",
                "warnings": [],
            }
        )

    monkeypatch.setattr(main, "call_vision_model_api", fake_call_vision_model_api)

    response = client.post(
        "/api/parse",
        data={"text": "识别表格"},
        files={"files": ("table.jpg", b"image-bytes", "image/jpeg")},
    )

    assert response.status_code == 200
    result = response.json()["data"]["result"]
    assert result["document_info"] == {"title": "巡检表", "id": "A-1", "confidence": 0.87}
    assert result["sections"][0]["fields"][0]["status"] == "filled"
    assert result["sections"][0]["fields"][1]["status"] == "empty"
    assert result["raw_text"] == "温度 23 °C"


def test_export_json_downloads_file() -> None:
    payload = {"data": {"summary": "demo", "fields": [{"key": "title", "value": "demo"}]}}
    response = client.post("/api/export/json", json=payload)

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith('attachment; filename="result.json"')
    assert json.loads(response.content) == payload["data"]
