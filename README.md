# Trip Planning Agent

一个面向真实出行场景的 AI 智能旅游助手。  
项目基于 `Vue 3 + TypeScript + FastAPI`，结合 `OpenAI-compatible LLM` 与高德地图能力，输出结构化多日行程，并支持 Trip Workspace、固定预约、局部重规划、分享访问和地图可视化。

## 当前能力

- 生成多日结构化行程，包含景点、餐饮、酒店、路线、天气和预算摘要
- 保存 `Trip Workspace`，支持草稿、结果快照、锁定日期和继续编辑
- 录入固定预约，支持时间合法性校验、冲突校验和结果覆盖审计
- 支持整体重规划和按天重规划
- 集成高德 MCP，路线能力保留 Web Service fallback
- 输出 diagnostics、warnings、集成状态和 telemetry

## 技术栈

### 前端

- Vue 3
- TypeScript
- Vite

### 后端

- FastAPI
- Pydantic v2
- pytest

### 外部能力

- OpenAI-compatible API
- 高德地图 JS SDK
- 高德 MCP
- 高德 Web Service

## 系统结构

```text
frontend
  ├─ App.vue
  ├─ components/
  ├─ composables/
  └─ api/

backend
  ├─ app/api/routes/planning.py
  ├─ app/services/planner.py
  ├─ app/agents/
  ├─ app/services/
  └─ tests/

docs
  ├─ 智能旅游助手-简历项目描述.md
  ├─ 智能旅游助手-代码链路详解与复盘指南.md
  ├─ 智能旅游助手-面试介绍与高频问答.md
  └─ 智能旅游助手-竞品对比与功能路线图.md
```

## 核心链路

### 行程生成

1. 前端提交 `POST /api/v1/plans/generate`
2. 后端校验请求并检查集成状态
3. 多阶段 Agent 生成 seed itinerary
4. 调用地图与天气能力补全 POI、酒店、路线和天气
5. 汇总为结构化 `TravelPlan`
6. 做预算、路线、地图点位、warnings 和 diagnostics 收口

### 工作区链路

1. 前端创建或更新 `Trip Workspace`
2. 后端保存请求快照、备注、锁定日期和预约
3. 需要重生成时，把工作区上下文注入规划请求
4. 支持按分享 token 读取工作区
5. 支持整体或按天重规划，并保留未重规划日期

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

## 测试与验证

### 后端

在仓库根目录执行：

```powershell
& '.\backend\.venv\Scripts\python.exe' -m pytest -q backend\tests
```

如果已经进入 `backend` 目录，则执行：

```powershell
& '.\.venv\Scripts\python.exe' -m pytest -q tests
```

### 前端

```powershell
cd frontend
npm run build
```

截至 `2026-04-15`，当前本地基线为：

- 后端：`131 passed, 8 warnings`
- 前端：`vue-tsc --noEmit` 与 `npm run build` 通过

## 主要接口

- `GET /api/v1/plans/integrations/status`
- `GET /api/v1/plans/telemetry`
- `POST /api/v1/plans/generate`
- `POST /api/v1/trips`
- `GET /api/v1/trips/{trip_id}`
- `GET /api/v1/trips/share/{share_token}`
- `PATCH /api/v1/trips/{trip_id}`
- `POST /api/v1/trips/{trip_id}/replan`

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
- `VITE_SHOW_DEV_PANELS`

说明：

- `AMAP_API_KEY` 用于前端地图 JS SDK
- `AMAP_MCP_ENV` 中的 `AMAP_MAPS_API_KEY` 用于后端地图服务
- 两类 key 不应混用

## 文档

- [docs/智能旅游助手-简历项目描述.md](docs/智能旅游助手-简历项目描述.md)
- [docs/智能旅游助手-代码链路详解与复盘指南.md](docs/智能旅游助手-代码链路详解与复盘指南.md)
- [docs/智能旅游助手-面试介绍与高频问答.md](docs/智能旅游助手-面试介绍与高频问答.md)
- [docs/智能旅游助手-竞品对比与功能路线图.md](docs/智能旅游助手-竞品对比与功能路线图.md)
- [docs/solution-design.md](docs/solution-design.md)
- [docs/上线部署指南.md](docs/上线部署指南.md)

## 当前仍值得继续优化的方向

### 结构层

- 后端继续收缩 `route_agent_orchestration.py` 与 `ai_client_runtime_adapter.py` 这类仍偏厚的编排热点
- 给 planning 阶段上下文补更明确的输入/输出对象，减少长参数列表和隐式耦合
- 地图层进一步明确公共出口、内部 support 与 Web Service 专用实现的边界
- 前端继续保持 `App.vue` 作为页面壳层，避免新功能回流成“大总管组件”

### 产品层

- 把固定预约从“强约束提示 + 审计”升级为更明确的硬约束排程
- 增加缺口驱动的一键补齐，而不是只做发现缺口
- 增加 Google Maps 收藏点导入、`.ics` 导出、出发前二次校验和多方案 diff
