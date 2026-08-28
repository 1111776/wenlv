# AI-B（工程实现型助手）对 AI-A 方案的评审意见

> 三方对齐 · 第一轮 · 交叉评审
> 评审对象：AI-A《需求转述与技术方案》
> 评审方：AI-B（Claude Code 角色承担）

## 前置说明（一句话）

AI-A 引入了一个我此前没有拿到的关键约束——**"7 人日"**。这个约束直接改变了我上一轮"自定义 DAG"的倾向：在 7 人日 + 验收演示的前提下，AI-A 的 LangGraph / Mock LLM / 单 Worker 是**务实且可辩护**的。因此本评审不"为了反对而反对"，只在两处地方给出实质不同意见：**恢复真相源的单一化**、**原子写细节的两个事实错误**。

---

## 第一部分：技术方案可行性评审（逐条）

| 序号 | AI-A 观点 | 我的评审意见 | 替代方案 | 是否需要学生裁决 |
|---|---|---|---|---|
| T1 | 编排框架用 **LangGraph**，理由"7人日不允许重造轮子" | 部分同意。**8节点+3条件边的DAG自己写约200行**，远非"重造轮子"；LangGraph 的代价是重依赖、版本 churn、黑盒调试、状态序列化开销。真正的决定变量是**团队是否已有 LangGraph 经验**：有→LangGraph 省时；没有→7人日里"学框架+踩坑"未必比手写快。 | 无经验→手写轻量 DAG（借鉴 LangGraph 的 StateGraph/Checkpointer 模型，不引依赖）；有经验→LangGraph。 | **是**（团队 LangGraph 经验 + 7人日是否为硬约束） |
| T2 | 异步队列用 **Redis Streams**（Consumer Group 匹配多 Worker） | 同意。工单指定，PEL + XAUTOCLAIM 原生支持断点接管。**但注意**：单 Worker 模式下 XAUTOCLAIM 的"崩溃接管"价值无法发挥（没有第二个 consumer 接管），恢复只能靠 worker 重启 + recover_all()。 | 无（Celery 更重，不满足 QPS 目标）。 | 否（已定） |
| T3 | **travel_plan.md + Redis Checkpointer 双写**，DB 为权威、文件做台账 | 需澄清。这实际是**三套状态源**（DB / 文件 / Checkpointer），而恢复机制到底由谁驱动没说清。关键矛盾：DB 只有 task 级状态，文件/Checkpointer 才有 step 级（ReAct 步）状态。"DB 为权威"对**对外展示**成立，但对**断点恢复**粒度不够。 | 明确**单一恢复驱动源**：Checkpointer（或文件）为恢复真相源（step 级），DB 为对外状态展示源，两者由 Worker 单点更新 + version 对账。 | **是**（恢复真相源归属） |
| T4 | travel_plans 表冗余 `resume_from VARCHAR` 做"双保险" | 不同意。冗余的 denormalized 字符串字段是 bug 源，会 stale；没有对账机制的"双保险"其实是"双真相"，比单真相更糟。 | 删 `resume_from`，用 `agent_tasks.status`（task 级）+ Checkpointer（step 级）做唯一进度真相。 | **是**（若保留须补对账策略） |
| T5 | 表结构 **5 张**：users / travel_plans / agent_tasks / review_records / budget_records | 有遗漏。缺 `reports`（报告落库）、`audit_logs`（安全审计需求）；`agent_tasks` 缺 `attempt/max_attempt`（重试追踪）、`tokens_used/cost`（与预算/成本联动）。RBAC 若只有 advisor/supervisor 两个角色，role 列字符串可接受；否则需 `roles/permissions` 表。 | 补 reports + audit_logs + agent_tasks.attempt/max_attempt；RBAC 范围待定（见 D13）。 | **是**（RBAC 范围决定是否加 roles 表） |
| T6 | 8 个 Agent"依次跑" | 遗漏并行。Web Research 与 Sentiment 无依赖，应 **fan-out/fan-in 并行**，否则整体延迟翻倍。LangGraph 支持 `add_edge(["web_research","sentiment"], "itinerary")`。 | 图中显式并行分支。 | **是**（确认并行分支） |
| T7 | 实时推送用 **WebSocket** `/ws/plans/{id}` | 可行但过重。单向 server→client 推送用 **SSE** 更简：自动重连、走 HTTP、无需 WS 握手、FastAPI 原生 StreamingResponse。WS 的双向能力本场景用不上。 | `GET /plans/{id}/events`（SSE）。 | 否（建议改 SSE，小改动） |
| T8 | **单 Worker**（MVP） | 同步 API（QPS 200）由 FastAPI 多 uvicorn worker 扛，与单 Agent Worker 解耦，故单 Worker 对同步指标无影响。**但端到端吞吐 = Worker 数 / plan 时长**：单 Worker 处理分钟级 plan，200 QPS 创建会瞬间堆积。缺"plan 吞吐（plans/hour）"指标。 | 明确端到端吞吐目标；单 Worker 可接受的前提是"创建率 << 处理率"。留多 Worker 扩展时需 plan→worker affinity 或 per-plan 锁。 | **是**（验收是否关心 plan 积压） |
| T9 | 限流只提 LLM 429 重试 | 遗漏队列背压。LLM 慢时 pending 无界增长，打爆内存与 LLM 账单。 | 每 worker 加最大并发 LLM 调用数（信号量）+ Stream MAXLEN 限制 + 队列深度告警。 | 否（工程补强） |
| T10 | 恢复时"重做最后 task（幂等）" | **"幂等"被断言、未设计**。LLM 调用天然非幂等，重跑 Planner 会得到不同拆解。 | 恢复只重跑"无持久化结果"的 task；结果落库/落文件与进度推进放进同一原子操作，`completed = 已持久化 = 不重跑`。 | **是**（恢复正确性核心） |
| T11 | 安全用 `injection_detector` + `ContentSanitizer` | 混淆了两件事。需求 #6"网页内容安全过滤"= **有害/非法内容过滤**，与 Prompt 注入防御是**两个独立问题**；AI-A 主要做了注入防御，ContentSanitizer 职责未明。 | 显式拆两个模块：ContentSafetyFilter（有害内容）+ PromptInjectionDetector（注入），各自独立。 | 否（补齐即可） |
| T12 | 仅 login 返回 JWT | 遗漏 refresh token + 过期/刷新流；access 过期后需重新登录。 | access（短）+ refresh（长）+ `/auth/refresh`。 | 否（MVP 可先省 refresh，但需注明） |
| T13 | 错误率 < 0.1% 无度量方案 | 遗漏。需定义错误口径（5xx / 超时 / 业务失败各算不算）、埋点、压测验证方式。 | locust 打同步接口，先定义"错误"集合，再谈 0.1%。 | **是**（错误率口径） |
| T14 | **未指定 LLM 供应商/模型** | 这是 AI-A 方案最大的遗漏之一。全文说"真 LLM/Mock LLM"，但没说接谁。供应商决定 ReAct 靠 function-calling 还是 prompt 解析、上下文长度、单次成本。 | 抽象 `LLMProvider` 接口，默认接主流模型；明确是否支持 function-calling。 | **是**（阻塞实现） |

---

## 第二部分：五个异常场景防御策略评审

| 序号 | AI-A 观点 | 我的评审意见 | 替代方案 | 是否需要学生裁决 |
|---|---|---|---|---|
| E1 | 文件并发写三层防御：temp+fsync+rename / `.sha256` 副文件 / 每 plan 单 Worker | 方向正确，但**两处事实错误**：① Windows 下 `os.rename()` **不能覆盖已存在文件**，须用 `os.replace()`；② rename 后应 **fsync 目录**（否则断电 rename 本身可能丢）。③ 更大的错误——"回退读取 `.tmp` 备份"不成立：`.tmp` 是**写了一半的临时文件**，不是备份。 | 保留上一版为 `.prev`（写前 cp）或直接依赖 Redis checkpoint 做回退；`.tmp` 只作为启动时孤儿清理对象。 | 否（实现修正） |
| E2 | LLM 限流三级降级：429 退避→降级→挂起，绝不静默丢弃 | 同意，方案是好的。补充：① L2 降级（正则/关键词规则）的结果要打 `degraded` 标志，否则报告看不出质量降级；② L3 挂起要与 HITL 审核台打通，挂起原因分类入库。 | 给结果加 `quality: degraded` 元数据。 | 否 |
| E3 | Prompt 注入：规则引擎前置 + 数据/指令分离 | 同意，"不能指望同一个 LLM 既被注入又防注入"是对的。补充两点：① **工具调用白名单**（ReAct 只允许 fetch/search，禁 shell/文件操作）；② **输出侧也要 sanitize**（LLM 输出可能含注入片段传播到报告）。关键词黑名单可被绕过，**结构隔离（分隔符 + 明确指令）才是主防线，规则是辅助**。 | 加工具白名单 + 输出过滤。 | 否 |
| E4 | 断点检测："半成品永不当成品"，tmp→fsync→rename + resume_from 推进 | 核心原则正确。补充：① 补目录 fsync；② "幂等重做最后 task"对 LLM 非真幂等（见 T10）；③ **recover_all() 与 LangGraph Checkpointer 是两套恢复路径**，未明确以谁为准，存在双轨漂移风险。 | 单一恢复驱动：Checkpointer resume 或文件 replay **二选一**。 | **是**（恢复驱动源，与 T3 同源） |
| E5 | 重复审批：行程级分布式锁 + DB pending 兜底 | **同意，这是全文最扎实的一处**。"锁是性能优化、DB pending 检查是正确性保证"是正确工程直觉。补充：① 锁 `EX=10s` 过短，审核详情页打开可能超 10s，需续期或用状态机 CAS 抢占；② DB pending 检查要带 version CAS 或放进事务，防 TOCTOU。 | 状态机 CAS（Suspended→Reviewing 原子 Lua）比纯锁更贴合"抢占"语义；锁仅作会话租约。 | 否（可优化） |

---

## 第三部分：需学生裁决的决策点汇总

> 覆盖 AI-A 已提的 10 条 + 我新增的遗漏项。AI-A 已倾向且我同意的，标"否（已定）"。

| 序号 | AI-A 观点 / 待决点 | 我的评审意见 | 替代方案 | 是否需要学生裁决 |
|---|---|---|---|---|
| D1 | Agent 真 LLM vs Mock（倾向 Mock） | 同意 B。7 人日 + 压测成本下 Mock 是唯一现实解。但 Mock 接口签名必须与真 LLM 完全一致，保证可无缝切换。 | Mock 实现 LLMProvider 同一接口。 | 否（已定方向，需确认接口） |
| D2 | 抓取真搜索 vs 种子 URL（倾向种子） | 同意 B 为主。真抓取有反爬/不稳定风险。补充：种子 URL 要覆盖"舆情正负例"，否则 Sentiment 无数据可用。 | 种子 URL + 一次真抓取验收。 | 否（已定方向） |
| D3 | 状态权威源 DB vs 文件（倾向 DB） | 需细化（见 T3）。"DB 权威"对展示成立，对恢复粒度不够；恢复真相源应落到 Checkpointer/文件。 | 分层：DB=对外展示真相，Checkpointer=恢复真相。 | **是** |
| D4 | 5 秒恢复计时起点（倾向进程启动） | 问题拆错了：真正的歧义不是"起点"，而是**"恢复"指什么**——(a) worker 崩溃 5s 内任务被接管，(b) 整个系统冷启动 5s 就绪。前者合理，后者需激进 HA 且 Docker 冷启动本身就超 5s。 | 先定"恢复"含义，再定计时起点。 | **是** |
| D5 | Human Review 时 Worker 阻塞 vs 释放（倾向释放） | 完全同意 B。阻塞会把 Worker 池占满（10 个挂起行程 = 池饿死）。释放后审批通过重新入队是标准做法。 | 挂起→worker 释放→审批通过→重新入队续跑。 | 否（已定） |
| D6 | 超预算 20% 基数（倾向用户原始预算） | 同意 A，但"20%"应是**可配置**（env），不是硬编码。 | 阈值配置化。 | 否（已定方向，确认可配） |
| D7 | 审批超时（倾向 24h 自动终止） | 同意必须有出口（状态机不完备则挂起堆积）。但"自动终止"语义未定：是 auto-reject 还是 auto-escalate 到更高级主管？24h 也是拍脑袋值。 | 明确超时动作（拒绝/升级）+ 时长可配。 | **是**（超时动作语义） |
| D8 | QPS 200 口径（倾向 status 查询） | 同意 B，与我上一轮一致。但要和验收方白纸黑字确认，否则压测报告会被质疑。 | 明确"同步接口 200 QPS + 长任务异步化"。 | **是**（跟验收方确认） |
| D9 | 单 Worker vs 多 Worker（倾向单 Worker） | 同意 MVP 单 Worker，但注意它使 Streams 的 XAUTOCLAIM 崩溃接管失效（无第二 consumer），恢复退回 recover_all()。且缺端到端吞吐指标（见 T8）。 | 单 Worker MVP + 留 plan→worker affinity 扩展点。 | **是**（连带吞吐指标） |
| D10 | travel_plan.md 粒度 per-plan vs 全局（倾向 per-plan） | 完全同意 A。全局单文件并发写无解，per-plan 是唯一合理解。 | workspace/{plan_id}/travel_plan.md。 | 否（已定） |
| D11 | （新增）编排框架 LangGraph vs 自定义 DAG | 见 T1。核心变量是团队 LangGraph 经验。 | 无经验→手写轻量 DAG。 | **是** |
| D12 | （新增）8 Agent 是否并行分支 | AI-A 未提并行（见 T6）。 | fan-out Web Research + Sentiment。 | **是** |
| D13 | （新增）RBAC 范围：2 角色硬编码 vs roles/permissions 表 | 需求写"RBAC"，但 2 角色（advisor/supervisor）硬编码 role 列就够 MVP。 | 2 角色→硬编码；多角色→roles 表。 | **是** |
| D14 | （新增）端到端 plan 吞吐（plans/hour）缺失 | 同步 QPS 达标 ≠ 系统真能消化 200 plan/s（见 T8）。 | 补充吞吐指标 + 队列深度监控。 | **是** |
| D15 | （新增）恢复驱动源：LangGraph Checkpointer vs 文件 replay | 与 T3/E4 同源，AI-A 两套并存未定谁为主。 | 单一驱动，另一个降级为兜底/审计。 | **是** |
| D16 | （新增）报告输出格式 | AI-A 未提报告长什么样：Markdown / PDF / 图表 / 可分享链接。 | 影响 Report Agent 与前端渲染。 | **是** |

---

## 四、给学生的"最高优先级裁决"清单（建议先拍这 5 条）

按阻塞程度排序：

1. **D14 + T8**：端到端吞吐指标——这是 QPS 200 达标后最容易被验收方打回来的点。
2. **T14**：LLM 供应商/模型——决定 ReAct 实现与成本，AI-A 完全没提。
3. **D4**："5 秒恢复"含义——决定恢复架构难度，差一个量级。
4. **T3 / D15**：恢复真相源单一化——决定 LangGraph 与自研文件 replay 谁主谁从。
5. **D11**：LangGraph vs 手写——取决于团队经验，7 人日内不可逆。

---

## 五、一句话总评

AI-A 方案在**选型方向（Streams、单 Worker、Mock、种子 URL）和 HITL 并发控制（E5 锁+DB兜底）**上是扎实的；真正的软肋在**恢复/状态一致性的单一化**（T3/T4/E4 三处暴露了三套真相源并存、两套恢复路径并存）和**两个原子写实现细节的错误**（E1 的 `os.replace` 与目录 fsync、`.tmp` 不是备份）。这些不解决，断点续传的"5 秒恢复"会是最容易翻车的地方。
