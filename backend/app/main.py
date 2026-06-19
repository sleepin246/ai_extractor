from __future__ import annotations

import json
import shutil
import time
import uuid
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, ZipFile

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import Workbook

BACKEND_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = BACKEND_ROOT.parent
STATIC_DIR = REPO_ROOT / "frontend" / "dist"
TMP_ROOT = Path("/tmp/ai_extractor")
UPLOAD_DIR = TMP_ROOT / "uploads"
EXPORT_DIR = TMP_ROOT / "exports"
MAX_AGE_SECONDS = 60 * 60 * 24

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


def infer_structured_payload(text: str, files: list[UploadFile]) -> dict[str, Any]:
    return {
        "summary": text[:120] if text else "MVP mock result: replace with AI provider later.",
        "source": {
            "text_length": len(text),
            "file_count": len(files),
            "files": [
                {"filename": file.filename, "content_type": file.content_type}
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
    for file in files:
        target = request_dir / (file.filename or f"upload-{uuid.uuid4().hex}")
        with target.open("wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        saved_files.append(str(target))

    result = infer_structured_payload(text, files)
    return api_response({"id": request_id, "result": result, "saved_files": saved_files})


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


if STATIC_DIR.exists():
    app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="frontend")
