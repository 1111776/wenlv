"""全国城市数据导出：解析 docs/knowledge/cities_*.md → 城市数据导出.md / .csv。

用法（容器内，知识库目录挂载在 /app/knowledge）：
    python scripts/export_cities.py /app/knowledge --outdir /tmp
然后 docker cp /tmp/城市数据导出.{md,csv} 到宿主机 docs/。

字段从每节正文中按固定句式解析：
    {城市}是{定位}，{必游}是必游。{美食}是特色。{提示}
解析失败的节回退为整段放入「出行提示」列（并在 stdout 提示）。
"""

from __future__ import annotations

import argparse
import csv
import re
from pathlib import Path

# 按省份归入大区（与分区域文件一致）
_HENAN = {"郑州", "平顶山", "安阳", "鹤壁", "新乡", "焦作", "濮阳", "许昌", "漯河",
          "三门峡", "南阳", "商丘", "信阳", "周口", "驻马店"}
_HUBEI = {"黄石", "十堰", "襄阳", "鄂州", "荆门", "孝感", "荆州", "黄冈", "咸宁",
          "随州", "恩施土家族苗族自治州"}
_HUNAN = {"株洲", "湘潭", "衡阳", "邵阳", "岳阳", "常德", "益阳", "郴州", "永州",
          "怀化", "娄底", "湘西土家族苗族自治州"}
_GUANGDONG = {"韶关", "汕头", "佛山", "江门", "湛江", "茂名", "肇庆", "惠州", "梅州",
              "汕尾", "河源", "阳江", "清远", "东莞", "中山", "潮州", "揭阳", "云浮"}
_GUANGXI = {"南宁", "柳州", "梧州", "防城港", "钦州", "贵港", "玉林", "百色", "贺州",
            "河池", "来宾", "崇左"}
_HAINAN = {"三沙", "儋州"}

# cities_guide.md（核心 60 城）→ 大区
_GUIDE_REGION = {}
for _c in "北京 天津 秦皇岛 承德 大同 平遥 呼和浩特 呼伦贝尔".split():
    _GUIDE_REGION[_c] = "华北"
for _c in "上海 南京 苏州 扬州 杭州 厦门 青岛 泰安 黄山 武夷山 庐山 乌镇".split():
    _GUIDE_REGION[_c] = "华东"
for _c in "洛阳 开封 武汉 宜昌 长沙 张家界 凤凰".split():
    _GUIDE_REGION[_c] = "华中"
for _c in "广州 深圳 珠海 桂林 北海 三亚 海口".split():
    _GUIDE_REGION[_c] = "华南"
for _c in "成都 重庆 九寨沟 贵阳 昆明 大理 丽江 西双版纳 香格里拉 拉萨 林芝".split():
    _GUIDE_REGION[_c] = "西南"
for _c in "西安 华山 敦煌 张掖 西宁 银川 乌鲁木齐 伊犁".split():
    _GUIDE_REGION[_c] = "西北"
for _c in "大连 哈尔滨 长白山 漠河".split():
    _GUIDE_REGION[_c] = "东北"
for _c in "香港 澳门 台北".split():
    _GUIDE_REGION[_c] = "港澳台"

_FILE_REGION = {
    "cities_huabei": "华北",
    "cities_dongbei": "东北",
    "cities_xinan": "西南",
    "cities_xibei": "西北",
}

# 主句式：{城市}是{定位}，{必游}是必游。{美食}是特色[美食]。{提示}
_BODY_RE = re.compile(r"^(.+?)是(.+?)，(.+?)是必游。(.+?)是特色(?:美食)?。(.*)$", re.S)
# 变体 1：必游/特色顺序颠倒（guide·广州）
_BODY_SWAP_RE = re.compile(r"^(.+?)是(.+?)，(.+?)是特色(?:美食)?。(.+?)是必游。(.*)$", re.S)
# 变体 2：因山得名（guide·泰安）
_BODY_NAMED_RE = re.compile(r"^(.+?)因(.+?)得名，(.+?)是必游。(.+?)是特色(?:美食)?。(.*)$", re.S)
_REGION_ORDER = ["华北", "东北", "华东", "华中", "华南", "西南", "西北", "港澳台"]


def _region_of(doc_id: str, city: str) -> str:
    if doc_id in _FILE_REGION:
        return _FILE_REGION[doc_id]
    if doc_id == "cities_huadong":
        return "港澳台" if city in {"高雄", "台南"} else "华东"
    if doc_id == "cities_zhongnan":
        if city in _HENAN or city in _HUBEI or city in _HUNAN:
            return "华中"
        if city in _GUANGDONG or city in _GUANGXI or city in _HAINAN:
            return "华南"
    return _GUIDE_REGION.get(city, "其他")


def _parse(base: Path) -> list[dict]:
    rows: list[dict] = []
    for fp in sorted(base.glob("cities_*.md")):
        doc_id = fp.stem
        title, buf = "", []
        sections: list[tuple[str, str]] = []

        def flush():
            if title and any(s.strip() for s in buf):
                sections.append((title, "\n".join(buf).strip()))

        for line in fp.read_text(encoding="utf-8").splitlines():
            if line.startswith("## "):
                flush()
                title, buf = line[3:].strip(), []
            else:
                buf.append(line)
        flush()

        for city, body in sections:
            m = _BODY_RE.match(body)
            if m:
                loc, spots, food, tip = m.group(2), m.group(3), m.group(4), m.group(5).strip()
            elif (m := _BODY_SWAP_RE.match(body)):
                loc, spots, food, tip = m.group(2), m.group(4), m.group(3), m.group(5).strip()
            elif (m := _BODY_NAMED_RE.match(body)):
                loc, spots, food, tip = f"因{m.group(2)}得名", m.group(3), m.group(4), m.group(5).strip()
            else:
                loc = spots = food = "—"
                tip = body
                print(f"[warn] 句式解析失败，整段放入提示列：{doc_id} / {city}")
            rows.append({
                "区域": _region_of(doc_id, city),
                "城市": city,
                "来源": doc_id,
                "城市定位": loc,
                "必游景点": spots,
                "特色美食": food,
                "出行提示": tip.rstrip("。"),
            })
    return rows


def _write_md(rows: list[dict], out: Path) -> None:
    lines = [
        "# 全国城市数据导出（353 城全量版）",
        "",
        "> 来源：`docs/knowledge/` 下 7 篇城市速览（cities_guide 核心版 + 华北/东北/华东/中南/西南/西北分区域详版），",
        "> 与知识库入库语料完全同源。可用 `backend/scripts/export_cities.py` 重新生成。",
        "",
        "## 区域分布",
        "",
        "| 区域 | 城市数 |",
        "|---|---|",
    ]
    for reg in _REGION_ORDER:
        n = sum(1 for r in rows if r["区域"] == reg)
        lines.append(f"| {reg} | {n} |")
    lines.append(f"| **合计** | **{len(rows)}** |")
    lines += ["", "## 分区域详情", ""]
    idx = 0
    for reg in _REGION_ORDER:
        sub = [r for r in rows if r["区域"] == reg]
        if not sub:
            continue
        lines += [f"### {reg}（{len(sub)} 城）", "", "| 序号 | 城市 | 城市定位 | 必游景点 | 特色美食 | 出行提示 |", "|---|---|---|---|---|---|"]
        for r in sub:
            idx += 1
            lines.append(
                f"| {idx} | {r['城市']} | {r['城市定位']} | {r['必游景点']} | {r['特色美食']} | {r['出行提示']} |"
            )
        lines.append("")
    out.write_text("\n".join(lines), encoding="utf-8")


def _write_csv(rows: list[dict], out: Path) -> None:
    with out.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["序号", "区域", "城市", "城市定位", "必游景点", "特色美食", "出行提示"])
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["区域"], r["城市"], r["城市定位"], r["必游景点"], r["特色美食"], r["出行提示"]])


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("knowledge_dir")
    ap.add_argument("--outdir", default=".")
    args = ap.parse_args()
    rows = _parse(Path(args.knowledge_dir))
    outdir = Path(args.outdir)
    outdir.mkdir(parents=True, exist_ok=True)
    _write_md(rows, outdir / "城市数据导出.md")
    _write_csv(rows, outdir / "城市数据导出.csv")
    print(f"导出完成：{len(rows)} 城 → {outdir}/城市数据导出.md / .csv")


if __name__ == "__main__":
    main()
