"""检索质量评估：对知识库检索跑测试集，计算 Hit@k / Recall@k / MRR。

用法：
    cd backend && python scripts/eval_retrieval.py

输出：终端打印逐条结果 + 汇总指标，并可生成 Markdown 报告到 docs/检索质量评估.md。
"""

import asyncio

from app.memory.kb_retrieve import search_kb

# 测试集：query -> 期望命中的 doc_id（标准答案）
# 覆盖 7 类语料 + 精确名词 + 语义模糊 + 政策类
TEST_SET: list[tuple[str, str]] = [
    ("老人门票免票政策", "ticket_policy"),
    ("儿童门票半价规则", "ticket_policy"),
    ("迪士尼儿童票怎么买", "attractions_more"),
    ("故宫门票多少钱", "attractions"),
    ("云南过桥米线", "food"),
    ("广州早茶吃什么", "food"),
    ("重庆火锅辣吗", "food_more"),
    ("武汉热干面", "food_more"),
    ("高铁儿童免票标准", "transport"),
    ("飞机婴儿票价格", "transport"),
    ("学生票高铁能用吗", "transport"),
    ("高原反应老人注意什么", "travel_tips"),
    ("带老人出行注意事项", "travel_tips"),
    ("海岛旅行防晒", "travel_tips"),
    ("冬季滑雪温泉推荐", "seasons_more"),
    ("夏季避暑去哪里", "seasons"),
    ("带老人住宿注意什么", "hotel"),
    ("带儿童住宿选什么酒店", "hotel"),
    ("景区观光车免票吗", "ticket_policy"),
    ("老人免票要什么证件", "ticket_policy"),
]


async def evaluate(k: int = 5) -> dict:
    """跑测试集，计算命中率、召回率、MRR。"""
    hits_at = {1: 0, 3: 0, 5: 0}
    rr_sum = 0.0  # 倒数排名求和（MRR）
    total = len(TEST_SET)
    details = []

    for query, expected in TEST_SET:
        results = await search_kb(query, top_k=k)
        returned_docs = [r["doc_id"] for r in results]
        # 期望 doc 在结果中的位置
        rank = None
        for i, d in enumerate(returned_docs, start=1):
            if d == expected:
                rank = i
                break

        # 命中判定
        for kk in (1, 3, 5):
            if rank is not None and rank <= kk:
                hits_at[kk] += 1

        # MRR：第一个命中位置的倒数
        if rank is not None:
            rr_sum += 1.0 / rank

        top1 = returned_docs[0] if returned_docs else "-"
        top1_title = results[0]["title"] if results else "-"
        details.append({
            "query": query,
            "expected": expected,
            "top1": top1,
            "hit": rank is not None,
            "rank": rank,
            "top1_title": top1_title,
        })

    metrics = {
        "total": total,
        "hit_at_1": hits_at[1] / total,
        "hit_at_3": hits_at[3] / total,
        "hit_at_5": hits_at[5] / total,
        "mrr": rr_sum / total,
    }
    return metrics, details


def render_md(metrics: dict, details: list) -> str:
    """生成 Markdown 评估报告。"""
    lines = []
    lines.append("# 检索质量评估报告")
    lines.append("")
    lines.append("> 自动生成 · 评估对象：文旅知识库混合检索（pgvector 向量 + BM25 关键词，RRF 融合）")
    lines.append("")
    lines.append("## 一、汇总指标")
    lines.append("")
    lines.append("| 指标 | 数值 |")
    lines.append("|---|---|")
    lines.append(f"| 测试集规模 | {metrics['total']} 条 |")
    lines.append(f"| Hit@1（首位命中率） | **{metrics['hit_at_1']:.1%}** |")
    lines.append(f"| Hit@3（前三命中率） | **{metrics['hit_at_3']:.1%}** |")
    lines.append(f"| Hit@5（前五命中率） | **{metrics['hit_at_5']:.1%}** |")
    lines.append(f"| MRR（平均倒数排名） | **{metrics['mrr']:.3f}** |")
    lines.append("")
    lines.append("## 二、逐条结果")
    lines.append("")
    lines.append("| # | 查询 | 期望文档 | 首位命中 | 命中排名 |")
    lines.append("|---|---|---|---|---|")
    for i, d in enumerate(details, start=1):
        hit_mark = "✅" if d["hit"] else "❌"
        rank = str(d["rank"]) if d["rank"] else "-"
        lines.append(f"| {i} | {d['query']} | {d['expected']} | {hit_mark} {d['top1']} | {rank} |")
    lines.append("")
    lines.append("## 三、说明")
    lines.append("")
    lines.append("- **Hit@k**：top-k 结果中命中期望文档的占比（越高越好）")
    lines.append("- **MRR**：命中文档排名的倒数平均值（越接近 1 越好，1.0 = 全部首位命中）")
    lines.append("- 评估口径：每个查询标注 1 个期望文档，检索 top-5 是否包含该文档")
    return "\n".join(lines)


async def main():
    metrics, details = await evaluate(k=5)
    # 打印终端
    print("=== 检索质量评估 ===")
    print(f"测试集 {metrics['total']} 条")
    print(f"Hit@1  = {metrics['hit_at_1']:.1%}")
    print(f"Hit@3  = {metrics['hit_at_3']:.1%}")
    print(f"Hit@5  = {metrics['hit_at_5']:.1%}")
    print(f"MRR    = {metrics['mrr']:.3f}")
    print()
    for d in details:
        mark = "✅" if d["hit"] else "❌"
        print(f"{mark} {d['query']} -> 期望 {d['expected']} / 首位 {d['top1']} (排名 {d.get('rank', '-')})")

    # 生成报告（优先写项目根 docs/，取不到则写当前目录）
    md = render_md(metrics, details)
    import os
    import pathlib

    base = os.environ.get("WENLV_WORKSPACE_ROOT")
    if base:
        out = pathlib.Path(base).resolve().parents[0] / "docs" / "检索质量评估.md"
    else:
        # 回退：__file__ 的 parents[2]（backend/scripts -> 项目根）
        try:
            out = pathlib.Path(__file__).resolve().parents[2] / "docs" / "检索质量评估.md"
        except IndexError:
            out = pathlib.Path("检索质量评估.md")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(md, encoding="utf-8")
    print(f"\n评估报告已写入：{out}")


if __name__ == "__main__":
    asyncio.run(main())
