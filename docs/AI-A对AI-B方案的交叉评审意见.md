# AI-A 对 AI-B 方案的交叉评审意见

> 三方对齐 · 第二轮 · 交叉评审
> 评审方：AI-A（分析型助手，Gemini 角色）
> 被评审文档：AI-B（Cursor）`architecture-design.md` v0.1
> 评审基准：任务工单 + AI-A 第一轮方案

---

## 总体评价

这是一份高质量的工程方案，多处设计优于我的初版，**我明确采纳**：

- ✅ 原子写入的 `os.replace`（Windows 兼容）+ **目录 fsync**（我初版遗漏）+ version header
- ✅ Redis Streams 的 **PEL + XAUTOCLAIM 崩溃接管**（比我初版"重启后 recover_all"更完整）
- ✅ 审核 **Lua CAS 抢占** 替代纯 SET NX 锁（抢占语义更准确）
- ✅ **禁用 pickle**、大对象下沉 ref 引用（教科书级正确）
- ✅ 错误码分段规范（40xxx/41xxx/50xxx/60xxx）
- ✅ 自加 Failed 终态、Reviewing 子状态（合理的状态机补全）

**但我不同意或发现问题的有 9 处**，其中 1 处数据依赖错误、1 处根本性分歧、4 处 MVP 过度设计，详见下表。

---

## 结构化评审意见

### 一、技术选型类

| 序号 | AI-B观点 | 我的评审意见 | 替代方案 | 是否需要学生裁决 |
|---|---|---|---|---|
| 1 | 自定义轻量DAG，不用LangGraph。理由：性能开销、planning-with-files职责重叠、拓扑固定 | **部分不同意**。"QPS 200性能不适合"论据不成立——编排层根本不在压测路径上（压测打的是同步API，Agent流程是异步的）。但"白盒可审计、贴合文件持久化"论据成立。真实风险：自研 Checkpointer+resume+条件边 ≈ 1.5~2人日，且是全系统正确性地基，出bug无框架兜底；LangGraph半天可用、自带Redis Checkpointer、且是工单首选项 | 保守选LangGraph（我原方案）；激进选自定义DAG（AI-B）。折中：**自定义一个仅含"节点+条件边+checkpoint接口"的200行微内核**，不实现图遍历框架 | **是（核心裁决点）** |
| 2 | Redis Streams + PEL/XAUTOCLAIM 做5秒恢复 | **同意且优于我的方案**。但补充：MVP单Worker部署时，"接管方"= Docker重启后的自己，实际时间线 = docker restart(~2-3s) + min-idle检测(2s)，**5秒预算很紧** | 恢复指标口径定为"**Worker进程就绪后5秒内完成resume**"，并实测记录docker重启耗时；min-idle 从2000ms下调到500ms | 是（口径确认） |
| 3 | 原子写：temp+fsync+rename+目录fsync | **完全同意**，比我初版完善。但"损坏则回退上一version"要求保留历史版本文件，方案未说明存储方式 | `workspace/{plan_id}/snapshots/v{n}.md` 保留最近5版，正式文件损坏时回退最大版本号 | 否（采纳+补充） |
| 4 | JSON+Pydantic序列化，禁用pickle | 同意 | — | 否 |
| 5 | 审核用Lua CAS抢占 + 会话租约锁双层 | **同意，优于我的纯锁方案** | — | 否 |
| 6 | 前端React 18+TS+Vite+SSE | 同意技术栈；**SSE优于我原方案的WebSocket**（单向推送足够、自动重连、实现简单），我接受 | — | 否 |
| 7 | React Flow 做DAG可视化 | **MVP过度设计**。工单要求的是"实时更新travel_plan.md看板"，任务表格+状态徽章+进度条即可满足验收 | MVP用Ant Design Table渲染Task List；React Flow列为二期加分项 | 是（建议砍） |
| 8 | 文件存储本地卷 vs MinIO（待定） | **MVP直接砍掉MinIO**。工单无多副本要求，单机Docker volume + 每行程一目录足够 | 本地卷 `workspace/{plan_id}/`，docker-compose挂volume持久化 | 是（建议定本地卷） |
| 9 | JWT access+refresh 双token | **MVP过度设计**。工单只要求JWT鉴权，7人日不值得做refresh轮换 | 单access token（过期时间设长，如24h），验收无影响 | 是（建议砍refresh） |
| 10 | roles+permissions两张表做RBAC | **过度设计**。工单明确只有两个角色（旅行顾问advisor、主管supervisor），JSONB权限矩阵无消费者 | users.role 枚举两值 + require_role依赖注入即可 | 是（建议简化） |

### 二、业务闭环类（重点发现）

| 序号 | AI-B观点 | 我的评审意见 | 替代方案 | 是否需要学生裁决 |
|---|---|---|---|---|
| 11 | 请求生命周期图中 **"Web Research ∥ Sentiment 并行执行"** | ❌ **数据依赖错误，必须改**。Sentiment Agent 的输入是 Web Research 抓取到的景点评价文本——**没有抓取结果就没有舆情可分析**，二者存在生产者-消费者依赖，不能纯并行 | MVP：**串行**（Web Research全部完成→Sentiment）。加分项：流水线化（每抓完一个网页立即送Sentiment），但复杂度显著上升 | **是（串行 vs 流水线）** |
| 12 | Redis 为"热状态真相源" | ⚠️ **根本分歧**。Redis 重启/AOF损坏时热状态丢失，"真相源"语义不成立；且与"文件断点续传"形成双真相源冲突 | **DB为权威真相源**（travel_plans.status），Redis仅做热缓存+Checkpointer。冲突时优先级：DB > 状态文件 > Redis。两层状态不一致由Worker单点顺序写入避免 | **是（核心裁决点）** |
| 13 | 状态机：驳回→回Planning rework | **不同意MVP做rework**。rework边意味着Agent要消化审核意见重新规划，Planner提示词、状态回退、二次审核的测试面全部扩大，7人日装不下 | 驳回→**Completed(rejected=true)终止**；用户可在前端复制该行程修改后重新提交（创建新plan）。rework列为二期 | 是 |
| 14 | 状态机五态+Failed（补充） | 同意加Failed。但**缺Cancelled终态**——方案有 POST /plans/{id}/cancel 接口，状态机图却没有Cancelled，Suspended期间能否取消未定义 | 增加 **Cancelled** 终态：Planning/Running/Suspended 均可→Cancelled；cancel需处理"取消时Worker正在执行"的竞态（通过版本号校验） | 否（采纳+补全） |
| 15 | 安全设计：数据/指令分离+sanitize+工具白名单 | 原则正确，但**缺拦截证据留存**——工单场景二要求"验证安全Agent能识别并拦截攻击"，必须有可断言的拦截记录 | 注入命中写入 `audit_logs`（action=security_block，含pattern、原文片段、source_url）或独立 `security_log.jsonl`，联调脚本据此断言 | 否（采纳+补充） |
| 16 | 数据模型无 budget 明细表（7张表） | **预算明细落库缺失**。工单交付物明确含"预算表"，压测/报告也需要结构化数据，只存Markdown不利于查询 | 恢复 `budget_records` 表（plan_id, category, item, amount），Report Agent双写文件+DB | 是（小裁决） |
| 17 | 决策清单未覆盖**重复提交防重** | 遗漏：用户连点提交按钮→同一行程入队两次。工单"高并发防重"除审批防重外应含**提交防重** | POST /plans 支持 Idempotency-Key 头，或Redis锁 `submit_lock:{user_id}` 5秒防抖 | 否（补充决策点） |
| 18 | 未定义审批人权限边界 | 遗漏：supervisor能否审批自己创建的行程？ | MVP职责分离：**advisor只创建、supervisor只审批**（supervisor不创建行程），从根上回避自审问题 | 是 |
| 19 | API只有login，无register | 可接受，但要在WBS写明 | seed脚本预置两个测试账号（advisor/supervisor各一） | 否 |

### 三、接口与状态机边界类

| 序号 | AI-B观点 | 我的评审意见 | 替代方案 | 是否需要学生裁决 |
|---|---|---|---|---|
| 20 | 错误码40xxx/41xxx/50xxx/60xxx分段 | 同意，比我初版连续编号更规范，**采纳AI-B方案** | — | 否 |
| 21 | Reviewing为Redis中的子状态 | 同意，但注意**两层状态模型不一致**：DB的status枚举只有五态，Reviewing只存在于Redis。需要明确映射规则 | DB层用 `status=suspended` + `review_records.status=reviewing` 表达；Redis热状态允许Reviewing。文档中写明两层映射表 | 否（补充） |
| 22 | 恢复粒度建议ReAct step级 | **工单只要求task级**（"从第6个网页断点续传"=网页task粒度），step级是加分项非必需 | MVP做**task级**checkpoint（每个网页抓完即存），step级列为加分项 | 是（建议task级） |
| 23 | hitl_reviews/agent_runs/audit_logs 三张审计类表 | agent_runs**保留**（Loop验证报告、任务四AI代码审查需要真实执行数据支撑）；audit_logs与安全日志**合并**为一张（action枚举含security_block） | 7张表收敛为：users、travel_plans、plan_tasks、agent_runs、hitl_reviews、budget_records、audit_logs | 是 |

---

## 与AI-A初版方案的分歧汇总（需学生拍板的核心争议）

| # | 争议点 | AI-A立场 | AI-B立场 | 争议焦点 |
|---|---|---|---|---|
| 1 | 编排框架 | LangGraph | 自定义DAG | 自研成本/风险 vs 框架黑盒/依赖 |
| 2 | 权威状态源 | DB权威 | Redis热真相源 | 真相源唯一性、崩溃后语义 |
| 3 | Sentiment时序 | 串行 | 并行 | AI-B存在数据依赖错误 |
| 4 | 驳回语义 | 终止 | 回Planning rework | MVP范围控制 |

## 建议的学生裁决包（一次性拍板清单）

> 以下是两个AI分歧+待定项的**我方建议裁决**，你逐条"同意/否决/修改"即可：

| 编号 | 裁决项 | 建议裁决 | 理由 |
|---|---|---|---|
| D1 | 编排框架 | **LangGraph**（若你想秀架构功底，可选AI-B的200行微内核折中） | 工期保险 |
| D2 | 权威状态源 | **DB权威，Redis为缓存+Checkpoint** | 真相源唯一 |
| D3 | Sentiment时序 | **串行** | 依赖正确性 |
| D4 | 驳回语义 | **MVP终止，rework二期** | 范围控制 |
| D5 | 状态机扩展 | **+Failed +Cancelled** | 状态完备 |
| D6 | 文件存储 | **本地卷，砍MinIO** | MVP够用 |
| D7 | RBAC | **role枚举，砍roles表** | 两角色无需权限矩阵 |
| D8 | JWT | **单token，砍refresh** | 验收无要求 |
| D9 | 恢复口径 | **Worker进程就绪后5秒内resume** | 可实测 |
| D10 | LLM | **开发/压测Mock，演示真调** | 成本+稳定 |
| D11 | 网页抓取 | **种子URL为主，验收演示真抓一次** | 反爬不稳定 |
| D12 | 超预算基准 | **用户预算×1.2，比例可配** | 工单语义 |
| D13 | 审批超时 | **24h未处理自动终止并通知** | 状态机要有出口 |
| D14 | 提交防重 | **Idempotency-Key或5秒防抖锁** | 补齐防重闭环 |
| D15 | QPS口径 | **同步接口（主要打status查询）** | 与验收方确认 |

---

## 结论

AI-B 方案工程成熟度高，**修正第11、12条缺陷 + 砍掉4处过度设计后即可作为定稿基础**。建议下一步：

1. 学生对 4 大分歧（编排框架/权威状态源/Sentiment时序/驳回语义）+ 15条裁决包逐条拍板；
2. 拍板后由 AI-B 按裁决结果修订 `architecture-design.md` 出 v0.2；
3. 用手册提示词 **1.3** 汇总双方共识生成《需求分析与WBS拆解文档》定稿，进入编码。
