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


def ticket_prices_by_party(name: str, poi_type: str, adults: int, children: int, elders: int) -> dict:
    """按出行人结构计算景点门票，区分成人票/儿童票/老人票。

    折扣比例可配（settings）：
    - 成人票 = ticket_price（基准价）
    - 儿童票 = 基准价 × ticket_child_discount（默认 0.5 半价）
    - 老人票 = 基准价 × ticket_elder_discount（默认 0.0 免费，可配）

    返回：{adult_price, child_price, elder_price, adult_total, child_total, elder_total, total}
    """
    from app.core.config import settings

    base = ticket_price(name, poi_type) or 0
    child = int(round(base * settings.ticket_child_discount))
    elder = int(round(base * settings.ticket_elder_discount))

    adults = max(int(adults or 0), 0)
    children = max(int(children or 0), 0)
    elders = max(int(elders or 0), 0)

    return {
        "adult_price": base,
        "child_price": child,
        "elder_price": elder,
        "adult_total": base * adults,
        "child_total": child * children,
        "elder_total": elder * elders,
        "total": base * adults + child * children + elder * elders,
    }
