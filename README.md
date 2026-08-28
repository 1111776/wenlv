# 文旅多 Agent 行程规划系统 — 实现说明与运行指南

基于《需求与技术方案说明书 v1.0》实现的多 Agent 协作文旅调研与个性化行程规划系统。

## 一、已实现功能（对照说明书场景）

| 场景 | 状态 | 验证方式 |
|---|---|---|
| 场景 A 正常行程生成 | ✅ | `scripts/e2e_check.py` |
| 场景 B kill -9 崩溃恢复 | ✅ | `scripts/recovery_test.py` |
| 场景 C Prompt 注入拦截 | ✅ | 第 7 页 `blocked` + `audit_logs.action=security_block` |
| 场景 D HITL 挂起 + 审批 | ✅ | `scripts/e2e_check.py` |

**8 个 Agent 全部实现**（`app/graph/nodes/`）：
Intake → Planner → Web Research(ReAct) → Sentiment → Itinerary → Budget → Human Review → Report

## 二、技术栈

- 后端：Python 3.12 / FastAPI / Pydantic v2 / SQLAlchemy 2 (async) / LangGraph
- 队列/缓存：Redis Streams（consumer group + PEL 断点续传）
- 数据库：PostgreSQL 15（六表 + audit_logs）
- 前端：React 18 / TypeScript / Vite / Ant Design
- 部署：Docker Compose（api / worker / redis / postgres / frontend / prometheus / grafana）

## 三、目录结构

```
wenlv/
├── backend/
│   ├── app/
│   │   ├── core/          # 配置/DB/Redis/安全/错误码
│   │   ├── models/        # 六张 ORM 表
│   │   ├── schemas/       # Pydantic 请求/响应模型
│   │   ├── agents/        # LLMProvider + 种子数据
│   │   ├── graph/         # LangGraph DAG + 8 节点 + 条件边
│   │   ├── services/      # 原子写/注入检测/内容安全/锁/队列/恢复/编排
│   │   ├── api/           # 路由（auth/plans/reviews/ws/health）
│   │   └── main.py        # FastAPI 入口
│   ├── scripts/           # 联调脚本（e2e + recovery）
│   ├── worker.py          # Worker 入口
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/              # React 前端
├── deploy/                # prometheus/locust/grafana 配置
└── docker-compose.yml
```

## 四、快速启动

### 方式一：本地开发（当前已跑通）

```powershell
# 1. 启动依赖（Redis 已在本机 6379；Postgres 用 Docker）
docker run -d --name wenlv-postgres -e POSTGRES_USER=wenlv -e POSTGRES_PASSWORD=wenlv -e POSTGRES_DB=wenlv -p 5432:5432 postgres:15-alpine

# 2. 启动 API（后端目录）
cd backend
$env:WENLV_DATABASE_URL="postgresql+asyncpg://wenlv:wenlv@localhost:5432/wenlv"
$env:WENLV_REDIS_URL="redis://localhost:6379/0"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 3. 启动 Worker（另一个终端）
$env:WENLV_DATABASE_URL="postgresql+asyncpg://wenlv:wenlv@localhost:5432/wenlv"
$env:WENLV_REDIS_URL="redis://localhost:6379/0"
python -m worker
```

### 方式二：Docker Compose 一键拉起

```powershell
docker compose up -d --build
```

服务端口：API `8000`、前端 `3000`、Redis `6379`、Postgres `5432`、Prometheus `9090`、Grafana `3001`。

## 五、预置账号

| 用户名 | 角色 | 密码 |
|---|---|---|
| `advisor_demo` | 旅行顾问（创建行程） | `wenlv123` |
| `supervisor_demo` | 主管（审核） | `wenlv123` |

## 六、运行验证脚本

```powershell
cd backend

# 场景 A/C/D：正常生成 + 注入拦截 + HITL 审批
python scripts/e2e_check.py

# 场景 B：kill -9 崩溃恢复
python scripts/recovery_test.py
```

## 七、核心设计要点

1. **断点续传**：`travel_plan.md` YAML 头含 `version` + `checksum` + `resume_from`；
   原子写入 = temp → fsync → `os.replace` → 目录 fsync，快照保留最近 5 版。
2. **崩溃恢复**：Worker 启动 `recover_all()` 扫描 running/recovering 行程，
   按 `resume_from` 跳过已 completed 页（幂等），从断点续跑。
3. **HITL**：超预算 20% / 高危夜行 / 严重舆情 → 挂起，Worker 释放；
   审批通过重新入队续跑；Lua CAS 抢占 + DB pending 兜底防重复审批。
4. **安全**：PromptInjectionDetector + ContentSafetyFilter 双模块；
   注入拦截写 `audit_logs.action=security_block`；工具白名单（fetch/search）。
5. **状态机**：planning/running/suspended/recovering/completed/failed/cancelled。

## 八、验证结果摘要

- ✅ 10 页抓取（第 7 页注入 → blocked，第 8 页负面 → 舆情风险，第 9 页夜行 → 夜行风险）
- ✅ 注入拦截审计 `security_block` 可查询，报告不含注入目标
- ✅ HITL 挂起 → 审批通过 → completed 完整闭环
- ✅ kill -9 后重启，从 `resume_from=page_6` 续跑，已完成任务数不变（无重复抓取）

## 九、性能指标（已验证）

**压测结果（本机 Docker 环境，20 并发 / 10 秒）：**

| 指标 | 实测 | 验收标准 | 结果 |
|---|---|---|---|
| QPS | **1109** | ≥ 200 | ✅ 超出 5.5 倍 |
| P95 延迟 | **35.4 ms** | < 300ms | ✅ 快 8 倍 |
| 错误率 | **0.000%** | < 0.1% | ✅ |

压测方式：`python deploy/loadtest.py 20 10`（纯 asyncio 并发，无需 Locust 环境）。
另有 Locust 脚本 `deploy/locustfile.py`（80% status + 15% 列表/详情 + 5% 创建）。

## 十、一键启动

```powershell
# Windows
.\start.ps1              # 构建并启动（首次约 2-5 分钟）
.\start.ps1 -NoBuild     # 快速重启
.\start.ps1 -Stop        # 停止
.\start.ps1 -Logs        # 查看日志

# Linux / macOS
./start.sh
```

**访问地址（已避开本机常见端口冲突）：**

| 服务 | 地址 |
|---|---|
| 前端看板 | http://localhost:8080 |
| 后端 API 文档 | http://localhost:8001/docs |
| Prometheus | http://localhost:9091 |
| Grafana | http://localhost:3002 (admin/admin) |

**端口映射说明**：因本机 3000/8000/6379/5432 等被其他项目占用，本项目统一改用
8080(前端)/8001(API)/6380(Redis)/5433(Postgres)/9091(Prometheus)/3002(Grafana)。
容器内部仍用标准端口，互不影响。

## 十一、容器化部署验证记录

已通过 `docker compose up -d --build` 一键启动并做完整端到端验证（登录 → 创建行程 →
8 Agent 执行 → HITL 挂起 → 审批通过 → completed → 报告含每日行程）。

验证过程中修复了一个**本地单进程测试无法暴露的真实 bug**：
- 创建行程 / 审批通过时，`publish_request` 在 DB 事务 commit **之前**就入队，
  导致 Worker 抢在数据落库前消费，报"行程不存在"。
- 修复：入队前显式 `await db.commit()`（见 `api/plans.py`、`api/reviews.py`）。
