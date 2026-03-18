# 智能旅游规划助手

一个面向中文场景的 AI 旅游规划项目，后端基于 FastAPI，前端基于 Vue 3 + TypeScript + Vite + Tailwind CSS，支持通过 MCP 协议接入高德地图服务，完成景点检索、路线规划、天气查询，并由 AI 生成多日行程。

## 1. 项目目标

本项目聚焦以下核心能力：

1. AI 自动生成详细的多日旅行计划。
2. 通过高德地图 MCP 服务获取实时 POI、路线和天气数据。
3. Agent 按流程自动调用工具，形成“数据获取 -> 行程生成 -> 结果展示”的闭环。
4. 提供适配桌面端和移动端的高质量前端体验。
5. 补充住宿、交通、餐饮、预算、打包清单等完整旅行建议。
6. 保证最终行程严格满足请求天数与 `day_number` 连续性（`1..N`）。
7. 预算按“每日明细汇总”计算，确保每日与总计一致。
8. 每日详细行程默认覆盖早/中/晚三餐，并计入当日餐饮费用。

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
    |-- TravelAIClient -> OpenAI API (严格校验 + 多轮重试)
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

## 5. 生成正确性与稳定性说明

1. 初步规划（seed）与最终行程汇总（compose）均采用多轮重试策略，应对上游模型偶发超时、解析失败或临时拒绝。
2. 最终行程在返回前会执行严格完整性校验：
   - `days` 数量必须等于请求天数；
   - `day_number` 必须唯一且覆盖 `1..request.days`；
   - 每天必须有活动、路线信息与餐饮信息；
   - 每日 `cost_breakdown.total_per_person_cny` 必须等于各分项之和。
3. 每日餐饮会在归一化阶段补齐早餐/午餐/晚餐，并将餐饮费用纳入每日与总预算。
4. 若重试后仍不满足严格约束，后端会直接报错，不会返回降级结果。

## 6. 回归测试

```bash
cd backend
.venv\Scripts\python.exe -m pytest -q tests
```
