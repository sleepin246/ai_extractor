from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import time
import uuid
from pathlib import Path
from string import Template
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

import httpx
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
STATIC_DIR = REPO_ROOT / "frontend" / "dist"
TMP_ROOT = Path("/tmp/ai_extractor")
UPLOAD_DIR = TMP_ROOT / "uploads"
EXPORT_DIR = TMP_ROOT / "exports"
MAX_AGE_SECONDS = 60 * 60 * 24
LLM_BASE_URL_ENV = "LLM_BASE_URL"
LLM_API_KEY_ENV = "LLM_API_KEY"
LLM_MODEL_ENV = "LLM_MODEL"
LLM_TIMEOUT_SECONDS_ENV = "LLM_TIMEOUT_SECONDS"
DATABASE_URL_ENV = "DATABASE_URL"
DEFAULT_VISION_API_TIMEOUT_SECONDS = 120.0
DEFAULT_VISION_API_RETRIES = 2
LLM_RETRIES_ENV = "LLM_RETRIES"
FIELD_STATUSES = {"filled", "empty", "uncertain"}
IMAGE_CONTENT_TYPE_PREFIX = "image/"

FAVICON_SVG = """<svg xmlns=\"http://www.w3.org/2000/svg\" viewBox=\"0 0 64 64\"><rect width=\"64\" height=\"64\" rx=\"14\" fill=\"#111827\"/><path d=\"M18 42V22h8v20h-8Zm10 0 8-20h8l8 20h-8l-1.2-4h-7.6L34 42h-6Zm9.1-10h3.8L39 26l-1.9 6Z\" fill=\"#fff\"/></svg>"""

STANDARD_IMAGE_EXTRACTION_PROMPT = """
你是一个通用图片信息抽取器。请从用户提供的图片中识别并抽取所有可见信息，包括但不限于：
- 表格数据
- 手写内容
- 打印文字
- 勾选框/状态
- 数值与单位
- 备注说明

必须遵守：
1. 只输出 JSON，禁止任何解释文本。
2. 不要求与原始表格结构完全一致，但必须保证信息完整。
3. 每个字段必须标注 status：filled、empty 或 uncertain。
4. 不要使用供应商专属字段；仅根据输入图片生成 JSON。

标准输出格式：
{
  "document_info": {
    "title": "",
    "id": "",
    "confidence": 0
  },
  "sections": [
    {
      "section_name": "",
      "fields": [
        {
          "field_name": "",
          "field_value": "",
          "status": "filled",
          "source_hint": "来自图片的原始位置或描述"
        }
      ]
    }
  ],
  "raw_text": "",
  "warnings": []
}
""".strip()

for directory in (UPLOAD_DIR, EXPORT_DIR):
    directory.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="AI Extractor API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class NoCacheStaticFiles(StaticFiles):
    def is_not_modified(self, response_headers: Any, request_headers: Any) -> bool:
        return False

    def file_response(
        self,
        full_path: Any,
        stat_result: Any,
        scope: Any,
        status_code: int = 200,
    ) -> Response:
        response = super().file_response(full_path, stat_result, scope, status_code)
        response.headers["Cache-Control"] = "no-store"
        return response


@app.on_event("startup")
def startup() -> None:
    init_database()



def get_database_url() -> str:
    return os.getenv(DATABASE_URL_ENV, "").strip()


def init_database() -> bool:
    database_url = get_database_url()
    if not database_url:
        return False
    try:
        with psycopg.connect(database_url) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS extraction_results (
                    id UUID PRIMARY KEY,
                    request_id TEXT NOT NULL,
                    input_text TEXT NOT NULL DEFAULT '',
                    result_json JSONB NOT NULL,
                    saved_files JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_extraction_results_created_at "
                "ON extraction_results (created_at DESC)"
            )
            conn.commit()
        return True
    except psycopg.Error as exc:
        print(f"PostgreSQL initialization failed: {exc}", flush=True)
        return False


def save_extraction_result(
    request_id: str,
    input_text: str,
    result: dict[str, Any],
    saved_files: list[str],
) -> str | None:
    database_url = get_database_url()
    if not database_url:
        return None
    record_id = str(uuid.uuid4())
    try:
        with psycopg.connect(database_url) as conn:
            conn.execute(
                """
                INSERT INTO extraction_results (id, request_id, input_text, result_json, saved_files)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (record_id, request_id, input_text, Jsonb(result), Jsonb(saved_files)),
            )
            conn.commit()
        return record_id
    except psycopg.Error as exc:
        print(f"PostgreSQL save failed: {exc}", flush=True)
        return None


def list_extraction_results(limit: int = 100) -> list[dict[str, Any]]:
    database_url = get_database_url()
    if not database_url:
        return []
    safe_limit = max(1, min(limit, 500))
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            rows = conn.execute(
                """
                SELECT id::text, request_id, input_text, result_json, saved_files,
                       created_at::text AS created_at
                FROM extraction_results
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (safe_limit,),
            ).fetchall()
        return list(rows)
    except psycopg.Error as exc:
        print(f"PostgreSQL list failed: {exc}", flush=True)
        return []


def get_extraction_result(record_id: str) -> dict[str, Any] | None:
    database_url = get_database_url()
    if not database_url:
        return None
    try:
        with psycopg.connect(database_url, row_factory=dict_row) as conn:
            row = conn.execute(
                """
                SELECT id::text, request_id, input_text, result_json, saved_files,
                       created_at::text AS created_at
                FROM extraction_results
                WHERE id = %s
                """,
                (record_id,),
            ).fetchone()
        return dict(row) if row else None
    except psycopg.Error as exc:
        print(f"PostgreSQL get failed: {exc}", flush=True)
        return None


def api_response(data: Any = None, message: str = "ok", code: int = 0) -> dict[str, Any]:
    return {"code": code, "message": message, "data": data}


def cleanup_temp_files() -> None:
    now = time.time()
    for directory in (UPLOAD_DIR, EXPORT_DIR):
        for path in directory.iterdir():
            if now - path.stat().st_mtime > MAX_AGE_SECONDS:
                if path.is_dir():
                    shutil.rmtree(path, ignore_errors=True)
                else:
                    path.unlink(missing_ok=True)



def empty_image_extraction_result(warnings: list[str], image_files: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "document_info": {"title": "", "id": "", "confidence": 0},
        "sections": [
            {
                "section_name": "Uploaded images",
                "fields": [
                    {
                        "field_name": image_file["filename"],
                        "field_value": "",
                        "status": "uncertain",
                        "source_hint": f"uploaded image: {image_file['filename']}",
                    }
                    for image_file in image_files
                ],
            }
        ] if image_files else [],
        "raw_text": "",
        "warnings": warnings,
    }


def normalize_extraction_result(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return empty_image_extraction_result(["Vision model response was not a JSON object."], [])

    document_info = value.get("document_info") if isinstance(value.get("document_info"), dict) else {}
    normalized: dict[str, Any] = {
        "document_info": {
            "title": str(document_info.get("title", "")),
            "id": str(document_info.get("id", "")),
            "confidence": normalize_confidence(document_info.get("confidence", 0)),
        },
        "sections": [],
        "raw_text": str(value.get("raw_text", "")),
        "warnings": normalize_warnings(value.get("warnings", [])),
    }

    sections = value.get("sections", [])
    if isinstance(sections, list):
        for section in sections:
            if not isinstance(section, dict):
                continue
            fields = []
            section_fields = section.get("fields", [])
            if isinstance(section_fields, list):
                for field in section_fields:
                    if not isinstance(field, dict):
                        continue
                    fields.append(
                        {
                            "field_name": str(field.get("field_name", "")),
                            "field_value": stringify_field_value(field.get("field_value", "")),
                            "status": normalize_field_status(field.get("status", "uncertain")),
                            "source_hint": str(field.get("source_hint", "")),
                        }
                    )
            normalized["sections"].append(
                {"section_name": str(section.get("section_name", "")), "fields": fields}
            )

    return normalized


def normalize_confidence(value: Any) -> float:
    if isinstance(value, (int, float)):
        return max(0.0, min(1.0, float(value)))
    return 0.0


def normalize_warnings(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if value:
        return [str(value)]
    return []


def normalize_field_status(value: Any) -> str:
    status = str(value).strip().lower()
    if status in FIELD_STATUSES:
        return status
    return "uncertain"


def stringify_field_value(value: Any) -> str:
    if isinstance(value, str):
        return value
    if value is None:
        return ""
    return json.dumps(value, ensure_ascii=False)


def parse_json_from_model_response(value: Any) -> Any:
    if isinstance(value, (dict, list)):
        return value
    if not isinstance(value, str):
        return value

    content = value.strip()
    if content.startswith("```"):
        lines = content.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        content = "\n".join(lines).strip()

    return json.loads(content)


def is_messages_api_url(api_url: str) -> bool:
    return api_url.rstrip("/").endswith("/v1/messages")


def is_chat_completions_api_url(api_url: str) -> bool:
    return api_url.rstrip("/").endswith("/v1/chat/completions")


def build_user_prompt(prompt: str, text: str) -> str:
    if text:
        return f"{prompt}\n\n用户补充说明：\n{text}"
    return prompt


def redact_vision_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted = {}
        for key, item in value.items():
            if key in {"base64", "data"} and isinstance(item, str):
                redacted[key] = f"{item[:80]}...<truncated {len(item)} chars>"
            elif key == "url" and isinstance(item, str) and item.startswith("data:"):
                redacted[key] = f"{item[:80]}...<truncated {len(item)} chars>"
            else:
                redacted[key] = redact_vision_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_vision_payload(item) for item in value]
    return value


def print_vision_payload(payload: dict[str, Any]) -> None:
    print(
        "Vision model API payload: "
        f"{json.dumps(redact_vision_payload(payload), ensure_ascii=False)}",
        flush=True,
    )


def extract_model_output(response_payload: Any) -> Any:
    if not isinstance(response_payload, dict):
        return response_payload
    if any(key in response_payload for key in ("document_info", "sections", "raw_text", "warnings")):
        return response_payload

    content = response_payload.get("content")
    if isinstance(content, list):
        text_blocks = []
        for block in content:
            if isinstance(block, dict) and isinstance(block.get("text"), str):
                text_blocks.append(block["text"])
            elif isinstance(block, str):
                text_blocks.append(block)
        if text_blocks:
            return "\n".join(text_blocks)

    choices = response_payload.get("choices")
    if isinstance(choices, list) and choices:
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            message = first_choice.get("message")
            if isinstance(message, dict) and "content" in message:
                return message["content"]
            if "text" in first_choice:
                return first_choice["text"]

    return response_payload


def build_vision_payload(prompt: str, image_files: list[dict[str, Any]], text: str, api_url: str = "") -> dict[str, Any]:
    images = [
        {
            "filename": image_file["filename"],
            "content_type": image_file["content_type"],
            "base64": base64.b64encode(image_file["content"]).decode("ascii"),
        }
        for image_file in image_files
    ]
    model = os.getenv(LLM_MODEL_ENV, "")
    if is_messages_api_url(api_url):
        content: list[dict[str, Any]] = [{"type": "text", "text": build_user_prompt(prompt, text)}]
        content.extend(
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image["content_type"],
                    "data": image["base64"],
                },
            }
            for image in images
        )
        return {
            "model": model,
            "max_tokens": 4096,
            "messages": [{"role": "user", "content": content}],
        }

    if is_chat_completions_api_url(api_url):
        content = [{"type": "text", "text": build_user_prompt(prompt, text)}]
        content.extend(
            {
                "type": "image_url",
                "image_url": {
                    "url": f"data:{image['content_type']};base64,{image['base64']}",
                },
            }
            for image in images
        )
        return {
            "model": model,
            "messages": [{"role": "user", "content": content}],
            "response_format": {"type": "json_object"},
        }

    return {
        "model": model,
        "prompt": prompt,
        "images": images,
        "text": text,
    }


def get_vision_api_timeout_seconds() -> float:
    raw_timeout = os.getenv(LLM_TIMEOUT_SECONDS_ENV, str(DEFAULT_VISION_API_TIMEOUT_SECONDS)).strip()
    try:
        timeout = float(raw_timeout)
    except ValueError:
        return DEFAULT_VISION_API_TIMEOUT_SECONDS
    return max(5.0, min(timeout, 600.0))


def get_vision_api_retries() -> int:
    raw_retries = os.getenv(LLM_RETRIES_ENV, str(DEFAULT_VISION_API_RETRIES)).strip()
    try:
        retries = int(raw_retries)
    except ValueError:
        return DEFAULT_VISION_API_RETRIES
    return max(0, min(retries, 5))


def build_vision_headers(api_url: str = "") -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if is_messages_api_url(api_url):
        headers["anthropic-version"] = "2023-06-01"
    api_key = os.getenv(LLM_API_KEY_ENV)
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


async def call_vision_model_api(text: str, image_files: list[dict[str, Any]]) -> dict[str, Any]:
    api_url = os.getenv(LLM_BASE_URL_ENV)
    if not api_url:
        return empty_image_extraction_result(
            [f"{LLM_BASE_URL_ENV} is not configured; image extraction requires a vision-capable JSON API."],
            image_files,
        )

    payload = build_vision_payload(STANDARD_IMAGE_EXTRACTION_PROMPT, image_files, text, api_url)
    print_vision_payload(payload)
    headers = build_vision_headers(api_url)
    timeout_seconds = get_vision_api_timeout_seconds()
    retries = get_vision_api_retries()
    try:
        async with httpx.AsyncClient(timeout=timeout_seconds) as client:
            for attempt in range(retries + 1):
                try:
                    response = await client.post(api_url, headers=headers, json=payload)
                    response.raise_for_status()
                    response_payload = response.json()
                    return normalize_extraction_result(
                        parse_json_from_model_response(extract_model_output(response_payload))
                    )
                except httpx.TimeoutException:
                    if attempt >= retries:
                        raise
                    wait_seconds = min(2 ** attempt, 5)
                    print(
                        "Vision model API timed out; "
                        f"retrying attempt={attempt + 1}/{retries} after {wait_seconds}s",
                        flush=True,
                    )
                    await asyncio.sleep(wait_seconds)
    except json.JSONDecodeError:
        body_preview = response.text[:200] if "response" in locals() else ""
        return empty_image_extraction_result(
            [
                "Vision model API response was not valid JSON; "
                f"status={getattr(response, 'status_code', 'unknown')}; body={body_preview}"
            ],
            image_files,
        )
    except httpx.TimeoutException as exc:
        return empty_image_extraction_result(
            [
                "Vision model API request timed out: "
                f"timeout={timeout_seconds}s; retries={retries}; error={exc}"
            ],
            image_files,
        )
    except httpx.HTTPStatusError as exc:
        body_preview = exc.response.text[:200]
        return empty_image_extraction_result(
            [
                "Vision model API request failed: "
                f"status={exc.response.status_code}; body={body_preview}; error={exc}"
            ],
            image_files,
        )
    except httpx.HTTPError as exc:
        return empty_image_extraction_result([f"Vision model API request failed: {exc}"], image_files)
    except ValueError as exc:
        return empty_image_extraction_result([f"Vision model API returned invalid JSON content: {exc}"], image_files)


async def infer_structured_payload(text: str, files: list[dict[str, Any]]) -> dict[str, Any]:
    image_files = [file for file in files if file["content_type"].startswith(IMAGE_CONTENT_TYPE_PREFIX)]
    if image_files:
        return await call_vision_model_api(text, image_files)

    return {
        "summary": text[:120] if text else "MVP mock result: replace with AI provider later.",
        "source": {
            "text_length": len(text),
            "file_count": len(files),
            "files": [
                {"filename": file["filename"], "content_type": file["content_type"]}
                for file in files
            ],
        },
        "fields": [
            {"key": "title", "value": text.splitlines()[0] if text else "Untitled"},
            {"key": "language", "value": "zh-CN"},
        ],
    }


@app.get("/api/health")
def health() -> dict[str, Any]:
    cleanup_temp_files()
    return api_response({"status": "healthy", "service": "ai-extractor-backend"})


@app.post("/api/parse")
async def parse_content(
    text: str = Form(default=""),
    files: list[UploadFile] = File(default=[]),
) -> dict[str, Any]:
    cleanup_temp_files()
    request_id = str(uuid.uuid4())
    request_dir = UPLOAD_DIR / request_id
    request_dir.mkdir(parents=True, exist_ok=True)

    saved_files = []
    uploaded_files: list[dict[str, Any]] = []
    for file in files:
        filename = file.filename or f"upload-{uuid.uuid4().hex}"
        content = await file.read()
        target = request_dir / filename
        target.write_bytes(content)
        saved_files.append(str(target))
        uploaded_files.append(
            {
                "filename": filename,
                "content_type": file.content_type or "application/octet-stream",
                "content": content,
            }
        )

    result = await infer_structured_payload(text, uploaded_files)
    record_id = save_extraction_result(request_id, text, result, saved_files)
    return api_response({"id": request_id, "record_id": record_id, "result": result, "saved_files": saved_files})


@app.get("/api/admin/results")
def admin_results(limit: int = 100) -> dict[str, Any]:
    return api_response({"database_enabled": bool(get_database_url()), "items": list_extraction_results(limit)})


@app.get("/api/admin/results/{record_id}")
def admin_result_detail(record_id: str) -> dict[str, Any]:
    record = get_extraction_result(record_id)
    if not record:
        return api_response(None, message="not found", code=404)
    return api_response(record)


@app.post("/api/export/{format_name}")
async def export_result(format_name: str, payload: dict[str, Any]) -> FileResponse:
    cleanup_temp_files()
    export_id = uuid.uuid4().hex
    base = EXPORT_DIR / export_id
    base.mkdir(parents=True, exist_ok=True)
    data = payload.get("data", payload)

    if format_name == "json":
        target = base / "result.json"
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    elif format_name == "markdown":
        target = base / "result.md"
        target.write_text(f"# AI Extractor Result\n\n```json\n{json.dumps(data, ensure_ascii=False, indent=2)}\n```\n", encoding="utf-8")
    elif format_name == "excel":
        target = base / "result.xlsx"
        workbook = Workbook()
        sheet = workbook.active
        sheet.title = "Result"
        sheet.append(["key", "value"])
        if isinstance(data, dict):
            for key, value in data.items():
                sheet.append([key, json.dumps(value, ensure_ascii=False) if isinstance(value, (dict, list)) else value])
        workbook.save(target)
    elif format_name == "zip":
        target = base / "result.zip"
        json_file = base / "result.json"
        json_file.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        with ZipFile(target, "w", ZIP_DEFLATED) as zip_file:
            zip_file.write(json_file, arcname="result.json")
    else:
        target = base / "result.json"
        target.write_text(json.dumps({"error": "unsupported format"}, ensure_ascii=False), encoding="utf-8")

    return FileResponse(target, filename=target.name)


@app.get("/favicon.ico", include_in_schema=False)
def favicon() -> Response:
    return Response(
        content=FAVICON_SVG,
        media_type="image/svg+xml",
        headers={"Cache-Control": "no-store"},
    )


if STATIC_DIR.exists():
    app.mount("/", NoCacheStaticFiles(directory=STATIC_DIR, html=True), name="frontend")
