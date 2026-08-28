# 文旅多 Agent 行程规划系统 — 交付文档

> 版本 v2.0 · 交付日期 2026-08-28

## 一、项目定位

基于 8 个 AI Agent 协作的文旅资源调研与个性化行程规划系统。用户输入一句自然语言需求，系统自动完成偏好解析、网页调研、舆情评估、日程编排、预算计算，全过程以真实数据（高德地图 + 天气 + 真实 LLM）驱动，支持断点续传、人工审核、图记忆与运行态强干预。

## 二、已接入的 API

| # | 服务商 | 能力 | 接口 | 状态 |
|---|---|---|---|---|
| 1 | 高德地图 | 地理编码（城市→坐标） | `geocode/geo` | ✅ |
| 2 | 高德地图 | POI 搜索（景点/酒店/餐饮） | `place/text` | ✅ |
| 3 | 高德地图 | 路径规划（距离+耗时） | `direction/driving` | ✅ |
| 4 | 高德地图 | 天气（实时+4天预报） | `weather/weatherInfo` | ✅ |
| 5 | 阿里云百炼 | LLM 大模型（8 Agent 推理） | `qwen3.7-plus` | ✅ |

> 密钥全部通过根目录 `.env` 注入（`.env` 已被 `.gitignore` 忽略，不入 git）。

## 三、技术架构

```
前端 (React 18 + TS + AntD)
  ↓ REST + WebSocket
API 网关 (FastAPI + JWT/RBAC)
  ↓
Agent 编排层 (LangGraph StateGraph + 8 节点)
  ├─ Intake    偏好解析（LLM）
  ├─ Planner   任务拆解（LLM）
  ├─ Web Research  高德 POI 搜索（真实数据）
  ├─ Sentiment 舆情评估
  ├─ Itinerary 高德路径规划（真实路线）
  ├─ Budget    预算计算
  ├─ Human Review 人工审核（HITL）
  └─ Report    报告生成（含天气）
  ↓
记忆与干预层 (memory/engine.py + mutator.py)
  ↓
数据层 (PostgreSQL + Redis + workspace 状态文件)
```

## 四、核心功能清单

- [x] 8 个 Agent 协作编排（LangGraph DAG + 条件边）
- [x] 真实高德数据：景点/路线/天气
- [x] 真实 LLM：qwen3.7-plus 驱动 Agent 推理
- [x] 断点续传（travel_plan.md + 原子写 + 5秒恢复）
- [x] HITL 人工审核（超预算/夜行/舆情 → 挂起 → 审批）
- [x] 安全（JWT/RBAC + 注入检测 + 内容过滤）
- [x] 图记忆（实体抽取 → 三元组 → 双路检索）
- [x] 运行态强干预（HMAC 验签 + nonce + 三写事务）
- [x] 提交防抖 + 审批超时 + Worker 心跳
- [x] Docker Compose 一键启动
- [x] 压测达标（QPS 1109 / P95 35ms / 错误率 0%）

## 五、启动方式

### 双击脚本（Windows）

- `start.bat` —— 一键启动 + 自动打开浏览器
- `stop.bat` —— 一键停止

### 命令行

```powershell
# 首次：复制 .env 模板并填 key
cp .env.example .env

# 启动
docker compose up -d --build
```

### 访问地址

| 服务 | 地址 |
|---|---|
| 前端看板 | http://localhost:8080 |
| API 文档 | http://localhost:8001/docs |
| Grafana | http://localhost:3002 (admin/admin) |
| Prometheus | http://localhost:9091 |

### 演示账号

| 用户名 | 角色 | 密码 |
|---|---|---|
| advisor_demo | 旅行顾问 | wenlv123 |
| supervisor_demo | 主管 | wenlv123 |

## 六、环境变量（.env）

```bash
# 高德（地图+天气）
WENLV_AMAP_KEY=xxx
WENLV_AMAP_ENABLED=true

# LLM（阿里云百炼）
WENLV_LLM_MODE=real
WENLV_LLM_API_KEY=xxx
WENLV_LLM_BASE_URL=https://xxx.compatible-mode/v1
WENLV_LLM_MODEL=qwen3.7-plus

# JWT
WENLV_JWT_SECRET=xxx
```

## 七、测试

```powershell
# 单元测试（图记忆 + 干预）
cd backend
python -m pytest tests/test_memory_intervention.py -v

# 端到端联调
python scripts/e2e_check.py

# 崩溃恢复测试
python scripts/recovery_test.py

# 压测
python deploy/loadtest.py 20 10
```

## 八、数据库表

- 业务：`users` / `travel_plans` / `agent_tasks` / `review_records` / `budget_records`
- 审计：`audit_logs`
- 图记忆：`graph_nodes` / `graph_edges` / `memory_events` / `interventions`

## 九、目录结构

```
wenlv/
├── backend/
│   ├── app/
│   │   ├── api/          # 路由（auth/plans/reviews/memory/ws）
│   │   ├── agents/       # LLMProvider + 8 Agent
│   │   ├── core/         # 配置/DB/Redis/安全/错误码
│   │   ├── graph/        # LangGraph 编排 + 节点
│   │   ├── memory/       # 图记忆引擎 + 强干预
│   │   ├── models/       # 10 张 ORM 表
│   │   ├── schemas/      # Pydantic 模型
│   │   └── services/     # 高德/原子写/锁/队列/恢复等
│   ├── scripts/          # 联调脚本
│   ├── tests/            # pytest
│   └── worker.py         # Worker 入口
├── frontend/             # React 前端
├── deploy/               # Prometheus/Grafana/Locust
├── docker-compose.yml
├── start.bat / stop.bat  # 一键启动/停止
├── .env                  # 密钥（不入 git）
└── .env.example          # 密钥模板
```
