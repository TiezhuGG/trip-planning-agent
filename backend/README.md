# Backend

后端基于 FastAPI，负责请求校验、Agent 编排、LLM 调用、AMap MCP / Web Service 数据获取、结果规范化与完整性校验。

### 主要职责

- 暴露健康检查和旅行规划接口
- 使用 `PlanningCoordinatorAgent` 串联各类子 Agent
- 调用 OpenAI 兼容模型生成初步草案和最终 itinerary
- 通过 AMap MCP 获取景点、路线、天气等上下文
- 对行程天数、`day_number`、预算、餐饮覆盖做严格校验
- 返回工具轨迹和 Agent 轨迹以便调试

### 核心模块

| 文件 / 模块 | 作用 |
| --- | --- |
| `app/main.py` | FastAPI 应用入口与 CORS 配置 |
| `app/api/routes/health.py` | 健康检查接口 |
| `app/api/routes/planning.py` | 规划相关接口 |
| `app/config.py` | 配置读取与运行时设置 |
| `app/services/planner.py` | 服务层入口 |
| `app/agents/planning_agent.py` | 总控协调器 |
| `app/services/ai_client.py` | LLM 调用、重试、计划规范化 |
| `app/services/amap_mcp_adapter.py` | AMap MCP / Web Service 适配 |
| `app/schemas/planning.py` | 请求与响应 schema |

### 子 Agent

- `PlannerSeedAgent`
- `SightseeingAgent`
- `HotelRecommendationAgent`
- `WeatherAgent`
- `MealRecommendationAgent`
- `RoutePlanningAgent`
- `ItineraryComposerAgent`

### 本地开发

```bash
cd backend
python -m venv .venv
```

激活环境：

```bash
# macOS / Linux
source .venv/bin/activate

# Windows PowerShell
.venv\Scripts\Activate.ps1
```

安装依赖并创建环境变量：

```bash
pip install -r requirements.txt
cp .env.example .env
```

启动服务：

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

### 环境变量

参考文件：

- [`./.env.example`](./.env.example)
- [`./.env.production.example`](./.env.production.example)

关键配置：

| 变量 | 说明 |
| --- | --- |
| `CORS_ORIGINS` | 允许访问的前端来源 |
| `OPENAI_API_KEY` | LLM 服务密钥 |
| `OPENAI_BASE_URL` | LLM 服务地址 |
| `OPENAI_MODEL` | 使用的模型名 |
| `AMAP_API_KEY` | 前端地图 JS SDK Key，会透出给前端地图配置 |
| `AMAP_SECURITY_JS_CODE` | 高德地图安全校验码 |
| `AMAP_MCP_COMMAND` | AMap MCP 启动命令 |
| `AMAP_MCP_ARGS` | AMap MCP 启动参数 |
| `AMAP_MCP_ENV` | 内含高德 Web Service Key |
| `ENABLE_MOCK_MCP` | 有限开发态 Mock 开关 |

### API

#### `GET /api/v1/health`

用于健康检查。

#### `GET /api/v1/plans/integrations/status`

检查以下状态：

- MCP 是否已连接
- LLM 是否已配置
- 工具映射是否完整
- 地图渲染配置是否可用
- 是否存在 warnings

#### `POST /api/v1/plans/generate`

接收 `TripPlanningRequest`，返回 `PlanningResponse`。

关键输入约束：

- `destination` 必须是中文城市名
- `days` 范围为 1 到 14
- `travelers.adults` 至少为 1

关键输出特性：

- `plan.days` 数量必须与请求一致
- `day_number` 必须连续覆盖
- 每日默认补齐早餐、午餐、晚餐
- 预算按每日明细重新聚合

### 测试

运行测试：

```bash
cd backend
pytest -q tests
```

测试重点包括：

- 请求校验
- 最终计划完整性
- 预算聚合
- 天气失败时的继续生成
- 路线与重试逻辑

### 注意事项

- 主生成流程默认要求可用的 LLM 和 AMap MCP。
- 部分 AMap 功能在 MCP 不可用时会尝试 Web Service 兜底。
- `ENABLE_MOCK_MCP` 主要用于开发调试，不适合作为正式结果来源。

