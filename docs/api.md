# API 约定

所有业务 API 默认返回统一 JSON：

```json
{"code":0,"message":"ok","data":{}}
```

## GET /api/health

健康检查。

## POST /api/parse

`multipart/form-data`，字段：

- `text`: 可选文本
- `files`: 可选多文件，支持图片、语音、文档等 MVP 临时上传

## POST /api/export/{format}

导出 JSON / Excel / Markdown / ZIP。
