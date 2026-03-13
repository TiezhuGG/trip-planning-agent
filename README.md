# 智能旅游规划助手

一个面向中文场景的 AI 旅游规划项目，后端基于 FastAPI，前端基于 Vue 3 + TypeScript + Vite + Tailwind CSS，支持通过 MCP 协议接入高德地图服务，完成景点检索、路线规划、天气查询，并由 AI 生成多日行程。

## 1. 项目目标

本项目聚焦以下核心能力：

1. AI 自动生成详细的多日旅行计划。
2. 通过高德地图 MCP 服务获取实时 POI、路线和天气数据。
3. Agent 按流程自动调用工具，形成“数据获取 -> 行程生成 -> 结果展示”的闭环。
4. 提供适配桌面端和移动端的高质量前端体验。
5. 补充住宿、交通、餐饮、预算、打包清单等完整旅行建议。

## 2. 架构概览

```text
frontend (Vue3 + Vite)
    |
    | HTTP /api/v1/plans/generate
    v
backend (FastAPI)
    |
    | TravelPlannerService
    |-- AmapMCPAdapter -> MCPStdioClient -> 高德地图 MCP Server
    |-- TravelAIClient -> OpenAI API
    |
    v
生成结构化旅行计划 JSON
```

## 3. 本地开发

### 后端

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

Windows + MCP 联调说明：

- 真实高德 MCP `stdio` 模式下，不要使用 `uvicorn --reload`，否则在 Windows 上会切到不支持 MCP 子进程的事件循环策略。
- 推荐直接运行 `python -m uvicorn app.main:app`。
- 如果用 PowerShell 调试 `/api/v1/plans/generate`，请使用 [backend/scripts/test_generate_utf8.ps1](C:/Users/FFF/Desktop/trip-planning-agent/backend/scripts/test_generate_utf8.ps1) 或先切换控制台为 UTF-8，否则中文请求和响应会显示为乱码。

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 4. Docker 部署

```bash
docker compose up --build
```
