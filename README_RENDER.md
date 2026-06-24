# Render Web Service 部署说明

本项目已调整为 Render Web Service 的最小单服务部署方式：Render 构建 React 前端静态文件，然后由 FastAPI 后端在同一个 Web Service 中托管 `/api/*` 和前端页面。

## Render 服务类型

请在 Render 创建 **Web Service**，并使用以下配置：

| 配置项 | 值 |
| --- | --- |
| Runtime | Docker |
| Root Directory | 留空（使用仓库根目录） |
| Dockerfile Path | `Dockerfile` |
| Build Command | 留空，Render 会自动执行 Dockerfile 构建 |
| Start Command | 留空，使用 Dockerfile 中的 `CMD` |

不要在 Render 上使用 docker-compose；Render 会直接基于仓库根目录的 `Dockerfile` 构建单容器服务。

## Dockerfile 行为

仓库根目录的 `Dockerfile` 会执行以下步骤：

1. 使用 Node 构建前端，并在构建时设置 `VITE_API_BASE=/api`。
2. 使用 Python 镜像安装后端依赖。
3. 将 `frontend/dist` 复制到最终镜像中。
4. 启动 FastAPI，并监听 Render 注入的 `PORT`。

因此 Render 上的 Build Command 和 Start Command 都留空：Build Command 由 Dockerfile 构建流程接管，Start Command 使用 Dockerfile 内置的 `CMD`。

## 环境变量

| Key | Value | 必填 | 说明 |
| --- | --- | --- | --- |
| `PORT` | Render 自动注入 | 是 | 不需要手动设置，Dockerfile 中的 `CMD` 会读取 `${PORT:-8000}` |
| `VITE_API_BASE` | 不需要手动设置 | 否 | Dockerfile 构建前端时已内联使用 `/api` |
| `LLM_BASE_URL` | 你的视觉模型或模型网关 HTTP JSON API 地址 | 是 | 上传图片时后端会调用该地址进行结构化抽取 |
| `LLM_API_KEY` | 你的 API Key | 否 | 如设置，会以 `Authorization: Bearer ...` 发送 |
| `LLM_MODEL` | 你的模型名称 | 是 | 会放入请求体的 `model` 字段 |
| `DATABASE_URL` | PostgreSQL 连接串 | 是 | Render PostgreSQL 会提供该连接串，后端用它建表并保存识别结果 |

## 部署后验证

假设 Render 域名是 `https://your-service.onrender.com`：

```bash
curl https://your-service.onrender.com/api/health
```

期望返回：

```json
{"code":0,"message":"ok","data":{"status":"healthy","service":"ai-extractor-backend"}}
```

浏览器打开 `https://your-service.onrender.com`，应看到 AI Extractor 前端页面和后台管理区域。输入文本或上传文件后，前端会请求同源 `/api/parse`，配置 `DATABASE_URL` 后可在后台管理区域看到保存的识别结果。
