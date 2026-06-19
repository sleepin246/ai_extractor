# Render Web Service 部署说明

本项目已调整为 Render Web Service 的最小单服务部署方式：Render 构建 React 前端静态文件，然后由 FastAPI 后端在同一个 Web Service 中托管 `/api/*` 和前端页面。

## Render 服务类型

- 类型：Web Service
- Runtime：Python 3
- Root Directory：留空（使用仓库根目录）
- 不使用 docker-compose

## Build Command

```bash
pip install -r backend/requirements.txt && cd frontend && npm ci && VITE_API_BASE=/api npm run build
```

说明：

- `pip install -r backend/requirements.txt` 安装 FastAPI 后端依赖。
- `npm ci` 安装前端依赖。
- `VITE_API_BASE=/api npm run build` 将前端 API 地址编译为同源 `/api`，避免写死 `localhost`。

## Start Command

```bash
cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

说明：

- Render 会自动注入 `PORT` 环境变量。
- 后端必须监听 `0.0.0.0`，否则 Render 无法从外部访问服务。

## 环境变量

| Key | Value | 必填 | 说明 |
| --- | --- | --- | --- |
| `PORT` | Render 自动注入 | 是 | 不需要手动设置，Start Command 读取 `$PORT` |
| `VITE_API_BASE` | `/api` | 建议 | Build Command 中已内联设置；如果在 Render 环境变量里配置，也应填 `/api` |

## 部署后验证

假设 Render 域名是 `https://your-service.onrender.com`：

```bash
curl https://your-service.onrender.com/api/health
```

期望返回：

```json
{"code":0,"message":"ok","data":{"status":"healthy","service":"ai-extractor-backend"}}
```

浏览器打开 `https://your-service.onrender.com`，应看到 AI Extractor 前端页面。输入文本或上传文件后，前端会请求同源 `/api/parse`。
