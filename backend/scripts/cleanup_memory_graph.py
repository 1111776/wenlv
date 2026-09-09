"""记忆图谱去碎片化清理脚本（一次性运维工具）。

历史 LLM 抽取产生大量碎片节点（同概念散落多个类型、脏前缀 key），本脚本：
1. 类型归一化：Location/Destination/City/Place→Location、Interest/Theme/TravelStyle→Preference 等
2. key 清理：去「天」脏前缀 + 观察到的截断 key 人工别名（上海旅→上海、熊猫和→熊猫、user→用户）
3. 合并：同 (node_class, 规范type, 规范key) 的节点并为幸存节点
   （属性 dict 合并、version 取最大+1），其余为死节点
4. 边重指：死节点上的边端点改指幸存者；按 (src,dst,relation) 去重合并；删自环
5. 幸存节点若 type/key 变化则重算 embedding（与 extract_and_store 同格式 f"{type}:{key}"）

用法（dry-run 只看计划不动库）：
    docker exec -w /app -e PYTHONPATH=/app wenlv-api-1 python scripts/cleanup_memory_graph.py --dry-run
正式执行：
    docker exec -w /app -e PYTHONPATH=/app wenlv-api-1 python scripts/cleanup_memory_graph.py
"""

from __future__ import annotations

import asyncio
import sys

# 类型归一化（含 engine._normalize_type 全集 + 库中观察到的碎片类型 + 中文兜底）
TYPE_MAP: dict[str, str] = {
    # 目的地/城市/地点 → Location
    "Location": "Location", "Destination": "Location", "City": "Location",
    "Place": "Location", "Address": "Location",
    "地点": "Location", "城市": "Location", "位置": "Location",
    # 偏好/兴趣/主题/风格 → Preference
    "Preference": "Preference", "Interest": "Preference", "Theme": "Preference",
    "TravelStyle": "Preference", "TravelTheme": "Preference", "SceneryType": "Preference",
    "Style": "Preference", "Like": "Preference",
    "偏好": "Preference", "喜好": "Preference", "兴趣": "Preference",
    # 活动/景点 → Attraction
    "Activity": "Attraction", "Attraction": "Attraction", "Scenic": "Attraction",
    "Spot": "Attraction", "Event": "Attraction",
    "景点": "Attraction", "活动": "Attraction",
    # 约束（含预算/时间/人数规模等量化约束）→ Constraint
    "Constraint": "Constraint", "Restriction": "Constraint",
    "Budget": "Constraint", "Time": "Constraint", "GroupSize": "Constraint",
    "约束": "Constraint", "限制": "Constraint",
    # 食物/过敏 → Food
    "Food": "Food", "Allergy": "Food", "Allergen": "Food", "Dish": "Food",
    "美食": "Food", "食物": "Food", "过敏": "Food",
    # 用户 → User
    "User": "User", "Person": "User", "Traveler": "User",
    "用户": "User", "人物": "User",
    # 住宿 → Hotel
    "Hotel": "Hotel", "Accommodation": "Hotel", "Lodging": "Hotel",
    "酒店": "Hotel", "住宿": "Hotel",
    # 同行人 → Group
    "Group": "Group", "Party": "Group", "Family": "Group",
}

# 观察到的脏 key 人工别名（截断/英文）
KEY_ALIAS: dict[str, str] = {
    "上海旅": "上海",
    "熊猫和": "熊猫",
    "user": "用户",
}


def clean_type(t: str) -> str:
    t = (t or "").strip()
    return TYPE_MAP.get(t, t)


def clean_key(key: str) -> str:
    k = (key or "").strip().lstrip("天").strip()
    return KEY_ALIAS.get(k, k)


async def main(dry_run: bool) -> None:
    from sqlalchemy import delete, insert, select, update

    from app.core.database import session_scope
    from app.models import GraphEdge, GraphNode

    async with session_scope() as db:
        nodes = (
            await db.execute(select(GraphNode).where(GraphNode.node_class != "code_graph"))
        ).scalars().all()
        n_edges_before = len((await db.execute(select(GraphEdge.id))).all())
        n_code = len(
            (await db.execute(select(GraphNode.id).where(GraphNode.node_class == "code_graph"))).all()
        )

    # ---- 纯计算阶段（不动库）----
    ident: dict[int, tuple[str, str, str]] = {
        n.id: (n.node_class, clean_type(n.type), clean_key(n.key)) for n in nodes
    }
    groups: dict[tuple[str, str, str], list] = {}
    for n in nodes:
        groups.setdefault(ident[n.id], []).append(n)

    survivor_of: dict[int, int] = {}  # 节点id -> 幸存节点id
    survivor_updates: dict[int, dict] = {}  # 幸存节点id -> {type,key,properties,version}
    dead_node_ids: set[int] = set()
    renamed: list[tuple[int, str, str]] = []

    for identity, members in groups.items():
        _, new_type, new_key = identity
        exact = [m for m in members if (m.type, m.key) == (new_type, new_key)]
        survivor = min(exact, key=lambda m: m.id) if exact else min(members, key=lambda m: m.id)

        merged_props: dict = {}
        for m in sorted(members, key=lambda m: m.id):
            merged_props.update(m.properties or {})
        merged_ver = max(m.version for m in members) + 1

        if (survivor.type, survivor.key) != (new_type, new_key):
            renamed.append((survivor.id, new_type, new_key))
        if len(members) > 1 or (survivor.type, survivor.key) != (new_type, new_key):
            survivor_updates[survivor.id] = {
                "type": new_type, "key": new_key,
                "properties": merged_props, "version": merged_ver,
            }
        for m in members:
            survivor_of[m.id] = survivor.id
            if m.id != survivor.id:
                dead_node_ids.add(m.id)

    # 边端点重指映射（只记真正变化的）
    remap = {nid: sid for nid, sid in survivor_of.items() if nid != sid}

    print(f"节点（非 code_graph）：{len(nodes)} 个，code_graph 保留 {n_code} 个")
    print(f"规范分组：{len(groups)} 组 → 预计幸存 {len(groups)} 个节点")
    print(f"合并删除节点：{len(dead_node_ids)} 个；需改名重嵌入：{len(renamed)} 个")
    print(f"边：{n_edges_before} 条（重指 {len(remap)} 个端点映射，去重与自环在执行阶段统计）")
    if renamed:
        print("\n改名清单：")
        for nid, t, k in renamed:
            old = next(n for n in nodes if n.id == nid)
            print(f"  #{nid} {old.type}:{old.key} -> {t}:{k}")
    type_before: dict[str, int] = {}
    for n in nodes:
        type_before[n.type] = type_before.get(n.type, 0) + 1
    type_after: dict[str, int] = {}
    for (_c, t, _k) in groups:
        type_after[t] = type_after.get(t, 0) + 1
    print("\n类型分布：之前 -> 之后")
    all_types = sorted(set(type_before) | set(type_after), key=lambda x: -type_before.get(x, 0))
    for t in all_types:
        print(f"  {t:14s} {type_before.get(t, 0):3d} -> {type_after.get(t, 0):3d}")

    if dry_run:
        print("\n[dry-run] 未改动数据库。确认后去掉 --dry-run 正式执行。")
        return

    # ---- 执行阶段 ----
    # 边处理策略：在内存里算好最终边集（端点重指 + 去重合并 + 去自环），
    # 然后同一事务内「全删 → 整批回插」。逐条 UPDATE 会在改到一半时撞
    # uq_graph_edge(src_id,dst_id,relation) 唯一约束，全删重建则原子无瞬态冲突。
    async with session_scope() as db:
        # 1. 幸存节点：改名 + 合并属性
        for nid, vals in survivor_updates.items():
            await db.execute(update(GraphNode).where(GraphNode.id == nid).values(**vals))

        # 2. 计算最终边集
        edges = (await db.execute(select(GraphEdge))).scalars().all()
        egroups: dict[tuple[int, int, str], list] = {}
        for e in edges:
            new_src = survivor_of.get(e.src_id, e.src_id)
            new_dst = survivor_of.get(e.dst_id, e.dst_id)
            egroups.setdefault((new_src, new_dst, e.relation), []).append(e)

        final_edges: list[dict] = []
        dup_edges = 0
        self_loops = 0
        for (new_src, new_dst, rel), es in egroups.items():
            es.sort(key=lambda e: e.id)
            keep = es[0]
            dup_edges += len(es) - 1
            if new_src == new_dst:
                self_loops += 1  # 合并后自环，丢弃
                continue
            merged: dict = {}
            for e in es:
                merged.update(e.properties or {})
            hist = [x for e in es for x in (e.merged_from or [])]
            if len(es) > 1:
                hist.append({"merged_edge_ids": [e.id for e in es[1:]]})
            final_edges.append({
                "id": keep.id,
                "src_id": new_src,
                "dst_id": new_dst,
                "relation": rel,
                "properties": merged,
                "confidence": max(e.confidence for e in es),
                "merged_from": hist,
            })

        # 3. 全删 → 回插（保留幸存边原 id）
        await db.execute(delete(GraphEdge))
        for fe in final_edges:
            await db.execute(insert(GraphEdge).values(**fe))

        # 4. 死节点删除
        for nid in dead_node_ids:
            await db.execute(delete(GraphNode).where(GraphNode.id == nid))

    n_edges_after = len(final_edges)
    print(f"\n已执行：节点 {len(nodes)} -> {len(groups)}，边 {n_edges_before} -> {n_edges_after}"
          f"（去重合并 {dup_edges}、自环丢弃 {self_loops}）")

    # ---- 幸存者重嵌入（type/key 变了的，与 extract_and_store 同格式）----
    if renamed:
        texts = [f"{t}:{k}" for _nid, t, k in renamed]
        from app.memory.engine import _embed

        embs = await _embed(texts)
        async with session_scope() as db:
            for (nid, _t, _k), emb in zip(renamed, embs):
                await db.execute(
                    update(GraphNode).where(GraphNode.id == nid).values(embedding=emb)
                )
        print(f"重嵌入 {len(renamed)} 个改名节点，检索向量已同步")
    print("完成。")


if __name__ == "__main__":
    asyncio.run(main(dry_run="--dry-run" in sys.argv))
