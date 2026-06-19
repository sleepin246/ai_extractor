# Render Web Service 部署说明

本项目已调整为 Render Web Service 的最小单服务部署方式：Render 构建 React 前端静态文件，然后由 FastAPI 后端在同一个 Web Service 中托管 `/api/*` 和前端页面。

## Render 服务类型

请在 Render 创建 **Web Service**，并使用以下配置：

| 配置项 | 值 |
| --- | --- |
| Runtime | Docker |
| Root Directory | 留空（使用仓库根目录） |
| Dockerfile Path | `Dockerfile` |
| Start Command | 留空，使用 Dockerfile 中的 `CMD` |

不要在 Render 上使用 docker-compose；Render 会直接基于仓库根目录的 `Dockerfile` 构建单容器服务。

## Dockerfile 行为

仓库根目录的 `Dockerfile` 会执行以下步骤：

1. 使用 Node 构建前端，并在构建时设置 `VITE_API_BASE=/api`。
2. 使用 Python 镜像安装后端依赖。
3. 将 `frontend/dist` 复制到最终镜像中。
4. 启动 FastAPI，并监听 Render 注入的 `PORT`。

因此 Render 上不需要手动填写 Build Command 或 Start Command。

## 环境变量

| Key | Value | 必填 | 说明 |
| --- | --- | --- | --- |
| `PORT` | Render 自动注入 | 是 | 不需要手动设置，Dockerfile 中的 `CMD` 会读取 `${PORT:-8000}` |
| `VITE_API_BASE` | 不需要手动设置 | 否 | Dockerfile 构建前端时已内联使用 `/api` |

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
