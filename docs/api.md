# API 约定

所有业务 API 默认返回统一 JSON：

```json
{"code":0,"message":"ok","data":{}}
```

## GET /api/health

健康检查。

## POST /api/parse

`multipart/form-data`，字段：

- `text`: 可选文本，可作为图片抽取补充说明
- `files`: 可选多文件，支持图片、语音、文档等 MVP 临时上传

当上传文件包含 `image/*` 时，后端会进入图片结构化信息抽取流程。抽取流程使用供应商无关的 JSON HTTP API 适配方式，不绑定 OpenAI、Claude、Qwen、DeepSeek 或任何特定模型名称。

### 图片抽取标准输出

图片抽取结果必须是 JSON 对象，并统一规范为以下结构：

```json
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
```

字段 `status` 只允许：

- `filled`：明确识别到的值
- `empty`：该位置确实存在但未填写
- `uncertain`：无法识别或不清晰

### 图片模型 API 配置

后端只要求“输入图片 + 输出 JSON”，通过环境变量适配不同供应商或中间网关：

| 环境变量 | 必填 | 说明 |
| --- | --- | --- |
| `LLM_BASE_URL` | 是 | 视觉模型或模型网关的 HTTP JSON API 地址 |
| `LLM_API_KEY` | 否 | 可选密钥；设置后默认以 `Authorization: Bearer ...` 发送 |
| `LLM_MODEL` | 是 | 要调用的模型名称；会放入默认请求体的 `model` 字段 |

默认请求体为：

```json
{
  "model": "...LLM_MODEL...",
  "prompt": "...标准抽取提示词...",
  "images": [
    {
      "filename": "form.png",
      "content_type": "image/png",
      "base64": "..."
    }
  ],
  "text": "用户补充说明"
}
```

如果 `LLM_BASE_URL` 以 `/v1/messages` 结尾，后端会自动使用 Messages API 请求体：`model`、`max_tokens`、`messages`，并将图片放入 `content[].source.data`。如果 `LLM_BASE_URL` 以 `/v1/chat/completions` 结尾，后端会自动使用 OpenAI-compatible Chat Completions 请求体：`model`、`messages`、`response_format`，并将图片放入 `content[].image_url.url` 的 data URL 中。每次调用前会在服务日志中打印脱敏后的 payload，图片 base64 / data URL 会被截断，便于排查 400 请求格式问题。

如果未配置 `LLM_BASE_URL`，或模型接口返回非 JSON / 请求失败，接口仍返回标准 JSON 结构，但会将图片字段标记为 `uncertain`，并在 `warnings` 中提示具体原因；HTTP 4xx/5xx 错误会包含状态码和响应正文片段。

## GET /api/admin/results

返回 PostgreSQL 中保存的识别结果列表，用于后台管理界面。响应中的 `database_enabled` 表示当前是否配置了 `DATABASE_URL`。

## GET /api/admin/results/{record_id}

返回单条已保存的识别结果详情。

## POST /api/export/{format}

导出 JSON / Excel / Markdown / ZIP。
