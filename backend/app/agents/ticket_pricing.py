"""景点门票 / 餐厅人均 虚拟价格生成器（确定性）。

背景：高德 POI 的 cost 字段为空，拿不到真实票价/人均价。
这里按景点/餐厅类型生成**合理的虚拟价格**，标注「参考价」。
原则同 hotel_pricing：确定性哈希，同一名字永远同价。
"""

from __future__ import annotations

import hashlib


def _stable_int(seed: str, mod: int) -> int:
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % mod


def _price(base: int, seed: str) -> int:
    """基准价 ±20%，取整到 5。"""
    jitter = _stable_int(seed, 41) - 20
    price = base * (1 + jitter / 100)
    return int(round(price / 5) * 5)


def ticket_price(name: str, poi_type: str = "") -> int | None:
    """按景点类型返回门票参考价（元）。

    - 免费类：公园、广场、街区、博物馆（部分）→ 0 或低价
    - 收费类：风景名胜、寺庙、主题乐园 → 30~200
    """
    t = (poi_type or "") + name
    seed = f"{name}:{poi_type}"

    if any(k in t for k in ["公园", "广场", "街区", "老街", "步行街", "博物馆", "美术馆", "展览"]):
        return _price(20, seed)  # 0~30 低价
    if any(k in t for k in ["寺庙", "古城", "古镇", "故居", "园林", "古迹"]):
        return _price(50, seed)  # 40~60
    if any(k in t for k in ["风景", "山", "湖", "岛", "乐园", "世界", "森林", "国家公园", "景区"]):
        return _price(100, seed)  # 80~120
    if any(k in t for k in ["主题", "乐园", "度假", "滑雪", "温泉"]):
        return _price(180, seed)  # 140~220
    # 默认中等
    return _price(60, seed)


def meal_price(name: str, poi_type: str = "") -> int:
    """餐厅人均参考价（元），按餐饮类型 30~150。"""
    t = (poi_type or "") + name
    seed = f"{name}:{poi_type}"
    if any(k in t for k in ["小吃", "快餐", "面", "粉", "早餐", "包子"]):
        return _price(20, seed)
    if any(k in t for k in ["咖啡", "茶", "甜品", "饮品"]):
        return _price(35, seed)
    if any(k in t for k in ["火锅", "烧烤", "烤鱼", "海鲜", "日料", "西餐"]):
        return _price(120, seed)
    if any(k in t for k in ["中餐", "川菜", "粤菜", "家常", "酒楼", "餐厅"]):
        return _price(70, seed)
    # 默认
    return _price(60, seed)


def elder_ticket_discount(age: int) -> float:
    """按老人年龄返回门票折扣（首道大门票）。

    规则（国有/政府定价 A 级景区）：
    - 年龄 >= ticket_elder_free_age（默认 65）：免首道大门票（0.0）
    - ticket_elder_half_age（默认 60）<= 年龄 < free_age：半价（0.5）
    - 年龄 < half_age：按成人全价（1.0）

    注意：免票不含观光车/索道/游船/演出/园中园（这里只算首道大门票）。
    """
    from app.core.config import settings

    age = int(age or 0)
    if age >= settings.ticket_elder_free_age:
        return 0.0
    if age >= settings.ticket_elder_half_age:
        return 0.5
    return 1.0


def child_ticket_discount(age: int, height: float | None = None) -> float:
    """按儿童年龄/身高返回门票折扣（首道大门票）。

    规则（国有/政府定价 A 级景区）：
    - 年龄 <= 6 周岁，或身高 <= 1.2 米（二选一满足即可）→ 免首道大门票（0.0）
    - 6 < 年龄 < 18 周岁 → 半价（0.5）
    - 年龄 >= 18 → 按成人全价（1.0）

    注意：免票只针对首道大门票；民营商业景区无强制国标，以景区公示为准。
    """
    age = int(age or 0)
    try:
        h = float(height) if height not in (None, "", 0) else 0.0
    except (ValueError, TypeError):
        h = 0.0
    # 免票：年龄 6 周岁以下，或身高 1.2 米以下（二选一满足）
    if age <= 6 or (0 < h <= 1.2):
        return 0.0
    if age < 18:
        return 0.5
    return 1.0


def ticket_prices_by_party(
    name: str,
    poi_type: str,
    adults: int,
    children: int,
    elders: int,
    elders_detail: list[dict] | None = None,
    children_detail: list[dict] | None = None,
) -> dict:
    """按出行人结构计算景点门票，区分成人票/儿童票/老人票。

    折扣规则（国有/政府定价 A 级景区，只算首道大门票）：
    - 成人票 = ticket_price（基准价）
    - 儿童票：传 children_detail（[{age, height}, ...]）时按年龄/身高逐人分档
      （6周岁以下或1.2米以下免票，6-18周岁半价）；否则兜底用 ticket_child_discount。
    - 老人票：传 elders_detail（[{age, gender}, ...]）时按年龄逐人分档；
      否则兜底用 ticket_elder_discount（默认 0.0 免费）统一按人数算。

    返回：{adult_price, child_price, elder_price, adult_total, child_total,
           elder_total, child_breakdown, elder_breakdown, note, total}
    """
    from app.core.config import settings

    base = ticket_price(name, poi_type) or 0

    adults = max(int(adults or 0), 0)
    children = max(int(children or 0), 0)
    elders = max(int(elders or 0), 0)

    # 儿童按年龄/身高分档（每人 age/height→折扣→单价），无明细则兜底统一折扣
    child_breakdown: list[dict] = []
    if children_detail:
        for c in children_detail:
            if not isinstance(c, dict):
                continue
            age = int(c.get("age") or 0)
            height = c.get("height")
            discount = child_ticket_discount(age, height)
            price = int(round(base * discount))
            child_breakdown.append(
                {"age": age, "height": height, "discount": discount, "price": price}
            )
        child_total = sum(b["price"] for b in child_breakdown)
        child_price = int(round(child_total / len(child_breakdown))) if child_breakdown else 0
    else:
        child = int(round(base * settings.ticket_child_discount))
        child_price = child
        child_total = child * children

    # 老人按年龄分档（每人 age→折扣→单价），无明细则兜底统一折扣
    elder_breakdown: list[dict] = []
    if elders_detail:
        for e in elders_detail:
            if not isinstance(e, dict):
                continue
            age = int(e.get("age") or 0)
            gender = e.get("gender") or ""
            discount = elder_ticket_discount(age)
            price = int(round(base * discount))
            elder_breakdown.append(
                {"age": age, "gender": gender, "discount": discount, "price": price}
            )
        elder_total = sum(b["price"] for b in elder_breakdown)
        elder_price = int(round(elder_total / len(elder_breakdown))) if elder_breakdown else 0
    else:
        elder = int(round(base * settings.ticket_elder_discount))
        elder_price = elder
        elder_total = elder * elders

    # 优待备注：有儿童/老人时，标注该人群可享的免/半价政策（区别于"景点本身免费"）
    note = _preferential_note(children_detail or [], elders_detail or [], child_breakdown, elder_breakdown)

    return {
        "adult_price": base,
        "child_price": child_price,
        "elder_price": elder_price,
        "adult_total": base * adults,
        "child_total": child_total,
        "elder_total": elder_total,
        "child_breakdown": child_breakdown or None,
        "elder_breakdown": elder_breakdown or None,
        "note": note,
        "total": base * adults + child_total + elder_total,
    }


def _preferential_note(
    children_detail: list[dict],
    elders_detail: list[dict],
    child_breakdown: list[dict],
    elder_breakdown: list[dict],
) -> str | None:
    """生成景点优待备注（仅当同行有儿童/老人且能享受免/半价时）。

    说明：这是「特定人群优待政策」，不是面向全部游客的免费景点。
    """
    notes: list[str] = []
    if child_breakdown:
        has_free = any(b.get("discount") == 0.0 for b in child_breakdown)
        has_half = any(b.get("discount") == 0.5 for b in child_breakdown)
        if has_free or has_half:
            notes.append("儿童：6周岁以下或身高1.2米以下免首道大门票，6-18周岁半价")
    if elder_breakdown:
        notes.append("老人：60-64周岁半价，65周岁及以上免首道大门票")
    if not notes:
        return None
    notes.append("（仅限首道大门票，观光车/游乐项目另计；民营景区以公示为准）")
    return "；".join(notes)


def transport_ticket_prices(
    method: str,
    adult_price: float,
    adults: int,
    children_detail: list[dict] | None = None,
    elders: int = 0,
    students: int = 0,
) -> dict:
    """按交通方式 + 同行人年龄计算车票/机票，返回分档明细与购票备注。

    高铁（铁路）规则（按乘车日期年龄）：
    - <6周岁：1位持票成人可免费携带1名（不占座）；要单独占座或多出的买儿童优惠票
    - 6≤年龄<14周岁：儿童优惠票（半价）
    - ≥14周岁：成人全价
    飞机规则（按乘机日期年龄）：
    - <2周岁：婴儿票（成人全价10%，无座位）
    - 2≤年龄<12周岁：儿童票（成人全价5折，有座位）
    - ≥12周岁：成人票
    老人：无全国统一优惠，按成人全价。
    学生：高铁学生票仅限家校往返、旅游不适用；飞机无学生优惠。

    返回：{method, adult_price, adult_total, elder_price, elder_total,
           child_breakdown, child_total, note, total}
    """
    from app.core.config import settings

    adult_price = float(adult_price or 0)
    adults = max(int(adults or 0), 0)
    elders = max(int(elders or 0), 0)

    is_air = any(k in method for k in ("飞机", "航班", "航空"))
    is_rail = any(k in method for k in ("高铁", "火车", "铁路", "动车"))

    adult_unit = int(round(adult_price))
    adult_total = adult_unit * adults
    elder_unit = int(round(adult_price * settings.transport_elder_discount))
    elder_total = elder_unit * elders

    child_breakdown: list[dict] = []
    child_total = 0
    free_carry_left = adults  # 高铁：每位持票成人可免费携带 1 名 <6 周岁儿童（不占座）

    for c in children_detail or []:
        if not isinstance(c, dict):
            continue
        age = int(c.get("age") or 0)
        seat = bool(c.get("seat"))
        if is_air:
            if age < 2:
                price = int(round(adult_unit * 0.10))
                tag = "婴儿票(10%)"
            elif age < 12:
                price = int(round(adult_unit * 0.50))
                tag = "儿童票(5折)"
            else:
                price = adult_unit
                tag = "成人票"
        elif is_rail:
            if age < 6:
                if not seat and free_carry_left > 0:
                    price = 0
                    free_carry_left -= 1
                    tag = "免票(随成人不占座)"
                else:
                    price = int(round(adult_unit * 0.50))
                    tag = "儿童优惠票(半价)"
            elif age < 14:
                price = int(round(adult_unit * 0.50))
                tag = "儿童优惠票(半价)"
            else:
                price = adult_unit
                tag = "成人票"
        else:
            # 大巴/自驾等：按原折扣兜底
            if age < 6:
                price = 0
                tag = "免票"
            elif age < 14:
                price = int(round(adult_unit * settings.transport_child_discount))
                tag = "儿童票"
            else:
                price = adult_unit
                tag = "成人票"
        child_breakdown.append({"age": age, "seat": seat, "price": price, "tag": tag})
        child_total += price

    # 购票备注
    notes: list[str] = []
    if students and students > 0:
        if is_rail:
            notes.append(f"学生票仅限全日制家校往返，旅游出行不适用（{students}人请购普通票）")
        if is_air:
            notes.append("飞机无学生优惠票，请购普通成人折扣票")
    if child_breakdown:
        has_infant = any(c["age"] < 2 for c in child_breakdown)
        has_young = any(c["age"] < 14 for c in child_breakdown)
        if has_infant or has_young:
            notes.append("儿童/婴儿购票需身份证、户口本或出生证明")
    note = "；".join(notes) if notes else None

    return {
        "method": method,
        "adult_price": adult_unit,
        "adult_total": adult_total,
        "elder_price": elder_unit,
        "elder_total": elder_total,
        "child_breakdown": child_breakdown or None,
        "child_total": child_total,
        "note": note,
        "total": adult_total + elder_total + child_total,
    }
