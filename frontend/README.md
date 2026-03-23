# Frontend

前端基于 Vue 3 + TypeScript + Vite，负责旅行规划表单、规划结果展示、地图渲染、提示反馈以及图片 / PDF 导出。

### 主要职责

- 收集用户输入并构造 `TripPlanningRequest`
- 调用后端接口：
  - `GET /api/v1/plans/integrations/status`
  - `POST /api/v1/plans/generate`
- 展示行程摘要、每日 itinerary、路线信息、预算和地图
- 将后端 warnings / errors 转换为更友好的用户提示
- 导出规划结果为 PNG / PDF

### 技术栈

- Vue 3
- TypeScript
- Vite
- Tailwind CSS
- html2canvas
- jspdf

### 关键模块

| 文件 / 模块 | 作用 |
| --- | --- |
| `src/App.vue` | 页面主入口，负责表单状态、请求流程、通知和结果切换 |
| `src/api/planning.ts` | 封装后端 API 请求 |
| `src/components/LandingHero.vue` | 首屏展示区域 |
| `src/components/PlannerLaunchPanel.vue` | 规划发起面板 |
| `src/components/TravelTonePanel.vue` | 旅行风格摘要展示 |
| `src/components/DailyItinerarySection.vue` | 每日行程区域 |
| `src/components/AmapMap.vue` | 高德地图渲染与路线展示 |
| `src/components/AgentTrace.vue` | Agent 执行轨迹展示 |
| `src/components/NotificationModal.vue` | 警告和错误弹窗 |

### 本地开发

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

默认开发地址：

- `http://localhost:5173`

### 环境变量

参考文件：

- [`./.env.example`](./.env.example)
- [`./.env.production.example`](./.env.production.example)

| 变量 | 说明 |
| --- | --- |
| `VITE_API_BASE_URL` | 后端 API 地址，开发态通常是 `http://localhost:8000` |
| `VITE_SHOW_DEV_PANELS` | 是否显示集成诊断面板 |

### 构建

```bash
npm run build
```

预览构建结果：

```bash
npm run preview
```

### 与后端协作约定

- 后端返回的 `integration_status` 会驱动前端诊断展示。
- 地图渲染依赖后端返回的 `map_config`。
- 前端默认将后端内部错误转换为更可理解的用户提示，而不是直接展示原始异常文本。

### 部署说明

- 如果前后端同源部署，`VITE_API_BASE_URL` 可以留空。
- 如果前端单独托管，`VITE_API_BASE_URL` 需要指向公网后端地址。
- 如果启用了高德 JS Key 来源限制，必须把实际前端访问域名或 IP 加入高德控制台白名单。