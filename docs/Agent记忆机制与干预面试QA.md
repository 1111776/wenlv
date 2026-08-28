# Agent 记忆机制与运行态强干预 — 面试 QA 知识库

> 对应工单 7 任务四《Agent 记忆机制与干预面试 QA 知识库》
> 覆盖面试三问：记忆设计如何与多轮对话结合 / Mem0 式存储与检索规则 / 运行态强制修改原理

---

## 问题一：Agent 的记忆是如何设计的？它怎样和多轮对话结合？

### 核心答案

本项目采用**「共享图记忆」**架构，用 Labeled Property Graph（LPG）建模跨对话、跨行程的长期记忆。它不是简单地"把对话存下来"，而是把对话里的**事实抽成三元组**，沉淀成可检索的知识图谱。

### 分层设计

| 层 | 结构 | 说明 |
|---|---|---|
| 节点（Node） | `(type, key, properties)` | 实体，如 `User:advisor_demo`、`Food:海鲜`、`City:青岛` |
| 边（Edge） | `(relation, properties, confidence)` | 关系，如 `HAS_ALLERGY`、`PREFERS`、`PLANS_VISIT` |
| Schema 分类 | `chat_memory` / `domain_wiki` / `code_graph` | 三类记忆分域存储，`node_class` 字段区分 |

### 和多轮对话结合的关键机制

1. **同步抽取**：每个 Agent 节点（Intake/Sentiment/Itinerary）产出结果后，立即调用 `memory.extract_and_store()`，把文本抽成三元组入图。
2. **跨轮召回**：下一轮对话（新行程）执行前，节点入口调用 `memory.retrieve()`，把当前用户的约束（如"海鲜过敏"）捞回来。
3. **场景验证**：第 8 轮说"我母亲海鲜严重过敏"→ 抽成 `(User)-[HAS_ALLERGY]->(海鲜)`；第 15 轮做青岛游时，Itinerary 检索到这条约束，避免推荐海鲜餐厅——**语义遗忘被修复**。

### 一句话总结

> 记忆 = 对话事实的**三元组图谱**；多轮结合 = **上一轮抽取沉淀 → 下一轮检索召回**。

---

## 问题二：Mem0 式的存储和检索规则是怎样的？

### Mem0 式存储的三步

1. **抽取（Extract）**：从非结构化文本中识别实体和关系（如"母亲对海鲜过敏"→ `(User:母亲)-[HAS_ALLERGY]->(Food:海鲜)`）
2. **沉淀（Upsert）**：命中 `(src_key, dst_key, relation)` 即合并（属性覆盖 + confidence 加权），否则新建
3. **覆盖合并（Merge）**：同一事实新值到来，confidence 更高则覆盖，保留 `merged_from` 溯源链

### 多层级检索（本项目的双路融合）

| 路径 | 原理 | 适用 |
|---|---|---|
| **向量检索** | 文本 embedding 做 cosine top-k | 语义相似（"海鲜过敏"匹配"海鲜"） |
| **图拓扑检索** | 从锚点实体出发 1-2 跳邻域 | 关联扩展（User 的约束邻域） |

融合结果按 `confidence × 距离衰减` 排序，返回时附带 `retrieval_path`（可解释"为什么推荐这个"）。

### 缓存策略

- Redis `plan:{id}:memory` 缓存，`memory_version` 失效
- 保障检索耗时 **P95 < 150ms** 红线

### 一句话总结

> Mem0 式 = **抽取 → 三元组 upsert → 向量+图双路检索**，核心是"事实沉淀为图谱 + 双路召回"。

---

## 问题三：运行态强制修改（强干预）的原理是什么？

### 核心答案

强干预是在 **LangGraph 图运行过程中**，允许主管/外部程序**带验签地原子修改**运行中 thread 的 State 和图属性，使 Agent 下一次决策优先采用干预后的状态。

### 五步原理链路

| 步骤 | 机制 | 对应实现 |
|---|---|---|
| 1. 安全验签 | HMAC-SHA256(密钥, thread_id ∥ nonce ∥ sha256(patch)) | `mutator.verify_signature` |
| 2. 防重放 | nonce 单次消费（Redis SETNX，TTL 300s） | `_consume_nonce` |
| 3. 排他锁 | `memory_lock:{thread_id}` SETNX | 复用 `lock.py` Lua CAS |
| 4. 三写一事务 | ① 图节点属性 version+1 ② Checkpointer state 补丁区 ③ interventions 流水（含 prev_state） | `mutator.intervene` |
| 5. 生效 | 节点入口统一读 state → 发现未消费补丁 → 应用 → 回写回执 | `graph/context.py` 读取器 |

### 为什么不是"直接改数据库"？

- **安全**：验签 + nonce 防重放，杜绝越权和重放攻击
- **原子**：三写同事务，任一步失败整体回滚
- **可追溯**：每个干预留 `prev_state` 快照，版本链完整可回放，可回滚
- **不扰动主状态机**：干预是旁路能力，不改变 `travel_plans.status`

### 关键设计权衡

- **补丁写独立 `state.intervention` 键**，由节点入口读取器应用，而不是深改 LangGraph 框架内部——框架升级零侵入
- **成功口径 = 回执**：干预成功 = 下一节点实际读到补丁（`intervention_read_at`），不是 HTTP 200 假阳性

### 一句话总结

> 强干预 = **验签 + nonce + 排他锁 + 三写原子 + 节点入口应用补丁**，实现"运行中纠偏"。

---

## 附：面试速记卡

| 三问 | 一句话答案 |
|---|---|
| 记忆怎么设计 + 结合多轮 | 三元组图谱，上轮抽取下轮召回 |
| Mem0 式存储检索 | 抽取→upsert→向量+图双路 |
| 运行态强干预原理 | 验签+锁+三写事务+节点入口应用 |
