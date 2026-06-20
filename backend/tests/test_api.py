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
    monkeypatch.delenv(main.LLM_BASE_URL_ENV, raising=False)

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
    assert main.LLM_BASE_URL_ENV in result["warnings"][0]


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


def test_vision_api_reads_llm_environment_variables(monkeypatch: Any) -> None:
    captured: dict[str, Any] = {}

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return {
                "document_info": {"title": "测试表", "id": "T-1", "confidence": 0.9},
                "sections": [
                    {
                        "section_name": "结果",
                        "fields": [
                            {
                                "field_name": "状态",
                                "field_value": "通过",
                                "status": "filled",
                                "source_hint": "图片右上角",
                            }
                        ],
                    }
                ],
                "raw_text": "状态 通过",
                "warnings": [],
            }

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            captured["timeout"] = timeout

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
            captured["url"] = url
            captured["headers"] = headers
            captured["json"] = json
            return FakeResponse()

    monkeypatch.setenv(main.LLM_BASE_URL_ENV, "https://llm.example.com/extract")
    monkeypatch.setenv(main.LLM_API_KEY_ENV, "test-key")
    monkeypatch.setenv(main.LLM_MODEL_ENV, "vision-model-test")
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post(
        "/api/parse",
        data={"text": "读取图片"},
        files={"files": ("form.png", b"image-bytes", "image/png")},
    )

    assert response.status_code == 200
    assert captured["url"] == "https://llm.example.com/extract"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert captured["json"]["model"] == "vision-model-test"
    assert captured["json"]["text"] == "读取图片"
    assert captured["json"]["images"][0]["base64"] == "aW1hZ2UtYnl0ZXM="
    assert response.json()["data"]["result"]["document_info"]["title"] == "测试表"


def test_vision_api_non_json_response_returns_warning(monkeypatch: Any) -> None:
    class FakeResponse:
        status_code = 200
        text = "not json"

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            raise json.JSONDecodeError("Expecting value", self.text, 0)

    class FakeAsyncClient:
        def __init__(self, timeout: float) -> None:
            return None

        async def __aenter__(self) -> "FakeAsyncClient":
            return self

        async def __aexit__(self, exc_type: Any, exc: Any, traceback: Any) -> None:
            return None

        async def post(self, url: str, headers: dict[str, str], json: dict[str, Any]) -> FakeResponse:
            return FakeResponse()

    monkeypatch.setenv(main.LLM_BASE_URL_ENV, "https://llm.example.com/extract")
    monkeypatch.setenv(main.LLM_MODEL_ENV, "vision-model-test")
    monkeypatch.setattr(main.httpx, "AsyncClient", FakeAsyncClient)

    response = client.post(
        "/api/parse",
        data={"text": "读取图片"},
        files={"files": ("form.png", b"image-bytes", "image/png")},
    )

    assert response.status_code == 200
    result = response.json()["data"]["result"]
    assert result["sections"][0]["fields"][0]["status"] == "uncertain"
    assert "not valid JSON" in result["warnings"][0]
    assert "not json" in result["warnings"][0]


def test_export_json_downloads_file() -> None:
    payload = {"data": {"summary": "demo", "fields": [{"key": "title", "value": "demo"}]}}
    response = client.post("/api/export/json", json=payload)

    assert response.status_code == 200
    assert response.headers["content-disposition"].startswith('attachment; filename="result.json"')
    assert json.loads(response.content) == payload["data"]
