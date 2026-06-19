# AI Extractor MVP

AI Extractor 是一个最小可运行的全栈 MVP：用户在聊天式页面上传文字、图片、语音或文件，后端返回结构化 JSON，用户可编辑并下载为 JSON、Excel、Markdown 或 ZIP。

## 技术栈

- Frontend：React + Vite，响应式支持 PC Web、手机 H5、微信内置浏览器
- Backend：FastAPI，统一 JSON 响应格式
- Deploy：Render Web Service 单服务部署，不使用 docker-compose
- Storage：暂不使用数据库，上传文件和导出文件临时保存在容器 `/tmp/ai_extractor`，访问 API 时自动清理超过 24 小时的临时文件

## 目录结构

```text
frontend/          # 前端聊天式上传和 JSON 编辑导出页面
backend/           # FastAPI API 服务，也负责托管 frontend/dist
README_RENDER.md   # Render Web Service 部署说明
docs/              # API 和设计文档
```

## Render 部署

请查看 [`README_RENDER.md`](./README_RENDER.md)。Render 上填写：

- Build Command：`pip install -r backend/requirements.txt && cd frontend && npm ci && VITE_API_BASE=/api npm run build`
- Start Command：`cd backend && uvicorn app.main:app --host 0.0.0.0 --port $PORT`
- 环境变量：`VITE_API_BASE=/api`（可选，Build Command 已内联）；`PORT` 由 Render 自动注入

## 本地开发

后端：

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

前端：

```bash
cd frontend
npm ci
VITE_API_BASE=http://127.0.0.1:8000/api npm run dev
```

## 本地模拟 Render 单服务

```bash
pip install -r backend/requirements.txt
cd frontend
npm ci
VITE_API_BASE=/api npm run build
cd ../backend
PORT=8000 sh -c 'uvicorn app.main:app --host 0.0.0.0 --port $PORT'
```

启动后访问：

- 前端：http://127.0.0.1:8000
- 后端健康检查：http://127.0.0.1:8000/api/health

## 测试策略

### Codex 环境轻量测试

当前 Codex 容器环境不能可靠执行 Docker build 或 docker-compose，因此在 Codex 中只运行非 Docker 测试：

```bash
cd backend
pip install -r requirements.txt
pytest
```

```bash
cd frontend
npm ci
npm run build
```

### Render / CI 验证

GitHub Actions 会运行 backend pytest 与 frontend production build。Render 完整联调在部署后通过 `/api/health` 和前端页面验证。

## 验证方式

1. 打开前端页面，在聊天输入框输入一段文本。
2. 可选：选择图片、音频或文档文件。
3. 点击「发送」，右侧/下方会出现结构化 JSON。
4. 编辑 JSON 后，点击 JSON、EXCEL、MARKDOWN 或 ZIP 按钮下载。
5. 打开 `/api/health`，应返回：

```json
{"code":0,"message":"ok","data":{"status":"healthy","service":"ai-extractor-backend"}}
```
