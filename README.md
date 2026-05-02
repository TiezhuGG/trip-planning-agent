# Trip Planning Agent

一个面向真实出行场景的 AI 旅行规划工作台。

项目基于 `Vue 3 + TypeScript + FastAPI`，结合 `OpenAI-compatible API` 与高德地图能力，输出结构化多日行程，并支持 Trip Workspace、固定预约录入、局部重规划、出发前预检、`.ics` 日历导出和地图可视化。

## 项目定位

这个项目不是“让模型生成一段旅游文案”，而是把 AI 规划、地图事实数据、工作区持续编辑、预约约束和预检修复接成一套连续的产品化链路。

用户拿到的不是一次性结果，而是一个可以继续补充、锁定、修复和导出的旅行工作区。

## 核心能力

- 生成结构化多日行程，包含景点、餐饮、住宿、路线、天气和预算摘要
- 保存 `Trip Workspace`，支持草稿、结果快照、分享访问和继续编辑
- 录入固定预约，支持酒店、航班、火车、餐厅、门票等类型
- 对预约做生成前约束注入、生成后覆盖诊断和保底锚定回写
- 支持整程重规划、单日重规划和 `fill_gaps` 缺口修复
- 支持出发前预检刷新，检查天气、路线、营业时间和预约覆盖问题
- 支持导出 `.ics` 日历文件和前端 PNG / PDF 结果导出
- 输出 diagnostics、warnings、integration status 和 telemetry

## 技术栈

- 前端：`Vue 3`、`TypeScript`、`Vite`
- 后端：`FastAPI`、`Pydantic v2`、`pytest`
- 模型层：`OpenAI-compatible API`
- 地图层：高德地图 `JS SDK`、高德 `MCP`、高德 `Web Service fallback`
- 工程化：`Docker Compose`、前端构建校验、后端回归测试

## 系统结构

```text
frontend
  ├─ src/App.vue
  ├─ src/components/
  ├─ src/composables/
  └─ src/api/

backend
  ├─ app/api/routes/planning.py
  ├─ app/services/planner.py
  ├─ app/services/trip_workspace.py
  ├─ app/agents/
  └─ tests/

docs
  ├─ Trip-Planning-Agent-简历面试说明.md
  ├─ Trip-Planning-Agent-面试问答库.md
  ├─ 智能旅游助手-代码链路详解与复盘指南.md
  └─ solution-design.md
```

## 核心链路

### 行程生成

1. 前端提交 `POST /api/v1/plans/generate`
2. 后端校验请求并检查 LLM / 地图集成状态
3. 多阶段编排生成 seed itinerary
4. 调用 POI、酒店、天气、路线等能力补事实
5. 汇总为结构化 `TravelPlan`
6. 收口预算、路线、地图点位、diagnostics 和 warnings

### 工作区链路

1. 前端创建或更新 `Trip Workspace`
2. 后端保存请求快照、备注、锁定日期和预约
3. 当需要重生成时，把工作区上下文注入规划请求
4. 支持整程重规划、单日重规划和缺口修复
5. 支持手动刷新出发前预检
6. 支持分享访问和 `.ics` 导出

### 预约链路

1. 用户在工作区录入预约
2. 后端做时间合法性和冲突校验
3. 生成前把预约映射成时段级约束注入请求
4. 生成后输出 `reservation_coverage`
5. 必要时自动锚定预约回写到日程

## 主要接口

- `GET /api/v1/plans/integrations/status`
- `GET /api/v1/plans/telemetry`
- `POST /api/v1/plans/generate`
- `POST /api/v1/trips`
- `GET /api/v1/trips/{trip_id}`
- `GET /api/v1/trips/share/{share_token}`
- `PATCH /api/v1/trips/{trip_id}`
- `POST /api/v1/trips/{trip_id}/replan`
- `POST /api/v1/trips/{trip_id}/precheck`
- `GET /api/v1/trips/{trip_id}/export/ics`

## 本地启动

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 前端

```powershell
cd frontend
npm install
Copy-Item .env.example .env.local
npm run dev
```

默认地址：

- 前端：`http://localhost:5173`
- 后端健康检查：`http://localhost:8000/api/v1/health`

## 环境变量

后端参考：

- `backend/.env.example`
- `backend/.env.production.example`

前端参考：

- `frontend/.env.example`
- `frontend/.env.production.example`

常见关键配置：

- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_MODEL`
- `AMAP_API_KEY`
- `AMAP_SECURITY_JS_CODE`
- `AMAP_MCP_COMMAND`
- `AMAP_MCP_ARGS`
- `AMAP_MCP_ENV`
- `VITE_API_BASE_URL`

说明：

- `AMAP_API_KEY` 用于前端地图 JS SDK
- `AMAP_MCP_ENV` 中的 `AMAP_MAPS_API_KEY` 用于后端地图服务
- 两类 key 不应混用

## 验证

前端：

```powershell
cd frontend
npm run build
```

后端示例：

```powershell
& '.\backend\.venv\Scripts\python.exe' -m pytest -q backend\tests\test_planning_routes.py
```

`2026-04-26` 本地已确认：

- 前端 `npm run build` 通过
- 后端 `test_planning_routes.py` 通过
- `test_trip_workspace_service.py` 仍有 1 个既有断言失败，属于预约冲突提示文案预期差异，不是本次项目拆分引入的问题

## 适合如何写进简历

这个项目更适合投递：

- AI Agent / LLM 应用开发
- Python 后端
- 智能体工作流 / 工具调用 / MCP 集成
- 具备一定产品化意识的全栈岗位

建议优先突出三点：

- 多阶段 AI 编排，而不是单次文案生成
- Trip Workspace 持续编辑、预约约束和局部修复能力
- 地图工具、结构化校验、预检和导出的完整工程链路

## 文档

- [简历面试说明](docs/Trip-Planning-Agent-简历面试说明.md)
- [面试问答库](docs/Trip-Planning-Agent-面试问答库.md)
- [代码链路详解与复盘指南](docs/智能旅游助手-代码链路详解与复盘指南.md)
- [系统设计说明](docs/solution-design.md)
- [上线部署指南](docs/上线部署指南.md)

## 一句话总结

这个项目的核心价值，不是“调了一个模型生成攻略”，而是把 AI 生成、地图事实、工作区编辑、预约约束、预检修复和日历导出接成了一套连续的旅行产品化系统。
