# Trip Planning Agent - 智能旅行助手

一个面向旅行场景的 AI 智能行程规划项目。  
项目使用 Vue 3 + FastAPI 构建前后端，结合 OpenAI 兼容模型与高德地图 MCP / Web Service 能力，生成结构化的多日旅行计划，并在前端展示路线、餐饮、住宿、天气和预算结果。


### 项目描述

- 支持输入目的地、天数、节奏、预算、交通偏好、住宿风格、餐饮偏好、必打卡地点等信息。
- 通过 Agent 编排串联初步规划、景点检索、天气查询、路线规划、住宿推荐和最终汇总。
- 返回结构化行程数据 ，而不是只有一段自由文本。
- 支持前端地图渲染、每日行程展开、提示弹窗、导出 PNG / PDF。
- 暴露集成状态接口，便于检查 LLM、MCP 和地图配置是否正常。

### 功能概览

#### 用户侧功能

- 多日旅行计划生成
- 景点、餐饮、酒店候选展示
- 天气与路线摘要
- 地图点位与折线渲染
- 预算总览与每日费用明细
- 行程导出为图片和 PDF

#### 系统侧能力

- 基于 LLM 生成初步日程草案
- 通过高德 AMap MCP 获取 POI、天气、路线数据
- 对路线规划支持 Web Service 兜底，避免 MCP 服务不可用时的失败
- 对可重试的模型错误执行多轮重试
- 对部分上游失败场景保留降级继续生成能力

### 架构

```text
frontend (Vue 3 + TypeScript + Vite)
    |
    | HTTP /api/v1/...
    v
backend (FastAPI)
    |
    |-- PlanningCoordinatorAgent
    |   |-- PlannerSeedAgent
    |   |-- SightseeingAgent
    |   |-- HotelRecommendationAgent
    |   |-- WeatherAgent
    |   |-- MealRecommendationAgent
    |   |-- RoutePlanningAgent
    |   `-- ItineraryComposerAgent
    |
    |-- TravelAIClient -> OpenAI-compatible API
    `-- AmapMCPAdapter -> MCP stdio client -> AMap MCP server / AMap Web Service fallback
```

请求流程：

1. 前端提交 `POST /api/v1/plans/generate`
2. 后端校验输入并检查集成状态
3. LLM 生成初步日程草案
4. AMap 相关 Agent 获取景点、餐饮、酒店、天气、路线信息
5. LLM 汇总最终行程数据
6. 后端执行规范化与完整性校验后返回结构化结果

### 技术栈

#### 前端

- Vue 3
- TypeScript
- Vite
- Tailwind CSS
- html2canvas
- jspdf

更多说明见 [`frontend/README.md`](frontend/README.md)。

#### 后端

- FastAPI
- Pydantic v2
- OpenAI Python SDK
- HTTPX
- MCP Python SDK

更多说明见 [`backend/README.md`](backend/README.md)。

### 快速开始

#### 环境要求

- Python 3.10+
- Node.js 20+
- npm
- Docker / Docker Compose，可选
- OpenAI 兼容模型的 API Key、Base URL、模型名
- 高德相关配置：
  - 前端 JS SDK Key
  - 如启用安全校验，则需要 `securityJsCode`
  - 后端 Web Service Key
  - AMap MCP Server 启动命令

#### 启动后端

```bash
cd backend
python -m venv .venv
```

激活虚拟环境：

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

安装依赖并创建环境变量文件：

```bash
pip install -r requirements.txt
cp .env.example .env
```

启动服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

#### 启动前端

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

访问地址：

- 前端：`http://localhost:5173`
- 后端健康检查：`http://localhost:8000/api/v1/health`

### 配置说明

#### 后端环境变量

参考：

- [`backend/.env.example`](backend/.env.example)
- [`backend/.env.production.example`](backend/.env.production.example)

关键配置：

| 变量 | 说明 |
| --- | --- |
| `OPENAI_API_KEY` | OpenAI 兼容模型服务的密钥 |
| `OPENAI_BASE_URL` | 非默认供应商时的 Base URL |
| `OPENAI_MODEL` | 用于初步规划和最终汇总的模型名 |
| `CORS_ORIGINS` | 允许访问的前端来源 |
| `AMAP_API_KEY` | 前端地图 JS SDK Key |
| `AMAP_SECURITY_JS_CODE` | 地图安全校验码 |
| `AMAP_MCP_COMMAND` | 启动 AMap MCP Server 的命令 |
| `AMAP_MCP_ARGS` | MCP 启动参数 |
| `AMAP_MCP_ENV` | 包含 `AMAP_MAPS_API_KEY` 的环境变量 JSON |
| `ENABLE_MOCK_MCP` | 是否允许有限开发态 Mock |

#### 前端环境变量

参考：

- [`frontend/.env.example`](frontend/.env.example)
- [`frontend/.env.production.example`](frontend/.env.production.example)

关键配置：

| 变量 | 说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 显式指定后端地址，留空表示同源访问 |
| `VITE_SHOW_DEV_PANELS` | 是否显示集成状态调试面板 |

#### 高德凭据区分

本项目同时使用两类高德凭据：

- `AMAP_API_KEY`：前端地图 JS SDK Key
- `AMAP_MCP_ENV={"AMAP_MAPS_API_KEY":"..."}`：后端 Web Service Key

两者不能混用。

### API

#### `GET /api/v1/health`

基础健康检查接口。

#### `GET /api/v1/plans/integrations/status`

返回以下集成诊断信息：

- MCP 是否启用、是否连通
- 可用工具与工具映射
- LLM 是否启用、是否可达
- 地图渲染配置状态
- 警告信息

#### `POST /api/v1/plans/generate`

生成结构化旅行计划。

请求体核心字段：

- `destination`
- `start_date`
- `days`
- `interests`
- `must_visit`
- `pace`
- `budget_level`
- `transport_preferences`
- `hotel_style`
- `dining_preferences`
- `travelers`
- `notes`

返回体核心字段：

- `initial_plan`
- `planning_context`
- `agent_trace`
- `tool_trace`
- `meta`
- `map_config`
- `integration_status`
- `plan`

### 部署

#### Docker Compose

项目自带 Docker 部署方式：

```bash
cp backend/.env.production.example backend/.env
docker compose --env-file .env.docker up -d --build
```

当前默认端口映射：

- backend：`127.0.0.1:8000 -> 8000`
- frontend：`${FRONTEND_PUBLIC_PORT:-8080} -> 80`

默认公网访问通常为：

- `http://<server-ip>:8080/`

部署参考文件：

- [`docker-compose.yml`](docker-compose.yml)
- [`.env.docker.example`](.env.docker.example)
- [`deploy/tencent-cvm-nginx.example.conf`](deploy/tencent-cvm-nginx.example.conf)

#### 生产环境检查清单

- 正确填写 `backend/.env`
- `CORS_ORIGINS` 与实际前端来源一致
- 高德 JS Key 的来源限制包含实际访问地址
- 放通前端公网端口
- 后端 `8000` 端口尽量保持仅本机监听

### 测试

运行后端测试：

```bash
cd backend
pytest -q tests
```

当前测试重点覆盖：

- 非中文城市名输入校验
- `day_number` 和天数完整性校验
- 预算聚合结果
- 早餐 / 午餐 / 晚餐补全逻辑
- 天气异常时的继续生成能力
- 路线与重试逻辑

### 目录结构

```text
trip-planning-agent/
  backend/
    app/
      agents/
      api/routes/
      schemas/
      services/
      main.py
    tests/
    requirements.txt
    README.md
  frontend/
    src/
      api/
      components/
      types/
      App.vue
    package.json
    README.md
  deploy/
  docs/
  docker-compose.yml
  README.md
```

### 约束与注意事项

- `destination` 当前只接受中文城市名。
- 主生成流程要求：
  - 可用的 OpenAI 兼容模型
  - 可用的 AMap MCP 配置
- 前端地图渲染依赖高德 JS SDK 的来源限制配置。
- 导出图片和 PDF 的质量依赖浏览器渲染与 canvas 捕获效果。