"""虚拟酒店房价生成器（确定性）。

背景：真实酒店房价 API（RollingGo/飞猪）未接入，这里生成**合理的虚拟房价**，
配合高德真实酒店 POI 名称，让行程报告中的酒店推荐与预算更完整。

原则：
- 确定性：同一目的地 + 同一酒店名，永远生成相同价格（用字符串哈希做种子）；
- 合理性：按城市等级分档，一线城市贵、旅游城市中等、其他便宜；
- 透明：报告里明确标注「价格为估算值」。

城市等级（房价基准，元/晚）：
- tier1 一线/热门旅游：北京 上海 广州 深圳 杭州 成都 三亚 厦门 丽江 大理 重庆 西安
- tier2 二线：其他省会/较大城市
- tier3 其他：县域/小城市
"""

from __future__ import annotations

import hashlib

# 城市等级 → 三档酒店基准价（经济/舒适/高档）
_TIER_BASE = {
    1: (280, 520, 1080),
    2: (220, 400, 800),
    3: (160, 300, 600),
}

_TIER1_CITIES = {
    "北京", "上海", "广州", "深圳", "杭州", "成都", "三亚", "厦门",
    "丽江", "大理", "重庆", "西安", "南京", "苏州", "武汉", "长沙",
    "青岛", "天津", "昆明", "贵阳",
}


def _city_tier(destination: str) -> int:
    """根据目的地判断城市等级（1/2/3）。"""
    d = (destination or "").strip()
    for city in _TIER1_CITIES:
        if city in d:
            return 1
    # 二线城市粗略判断：省会/较大城市名（非县城）
    # 简化：默认 2，无法识别时 2
    return 2


def _stable_int(seed: str, mod: int) -> int:
    """从字符串稳定哈希出一个 [0, mod) 的整数。"""
    h = hashlib.md5(seed.encode("utf-8")).hexdigest()
    return int(h[:8], 16) % mod


def _price(base: int, seed: str) -> int:
    """在基准价 ±20% 范围内生成确定性的整数价格（取整到十位）。"""
    jitter = _stable_int(seed, 41) - 20  # -20 ~ +20
    price = base * (1 + jitter / 100)
    return int(round(price / 10) * 10)


def generate_hotels(destination: str, hotel_names: list[str], nights: int) -> list[dict]:
    """为真实酒店 POI 生成虚拟房价。

    Args:
        destination: 目的地（决定城市等级）
        hotel_names: 高德搜到的真实酒店名列表（可为空）
        nights: 住宿晚数

    Returns:
        [{name, tier_label, room_type, price_per_night, rating, tags, total_price}]
    """
    tier = _city_tier(destination)
    econ_base, comfort_base, luxury_base = _TIER_BASE[tier]

    # 三档酒店（名称优先用真实 POI，不足用占位名）
    templates = [
        {"tier_label": "经济型", "base": econ_base, "room_type": "大床房", "rating_range": (4.3, 4.6)},
        {"tier_label": "舒适型", "base": comfort_base, "room_type": "双床房", "rating_range": (4.5, 4.8)},
        {"tier_label": "高档型", "base": luxury_base, "room_type": "家庭房", "rating_range": (4.6, 4.9)},
    ]

    hotels = []
    for i, tpl in enumerate(templates):
        # 酒店名：优先真实 POI，否则用占位
        if i < len(hotel_names) and hotel_names[i]:
            name = hotel_names[i]
        else:
            name = f"{destination}{tpl['tier_label']}酒店"

        seed = f"{destination}:{name}:{tpl['tier_label']}"
        price = _price(tpl["base"], seed)
        rating = tpl["rating_range"][0] + _stable_int(seed + ":rating", 40) / 100

        hotels.append(
            {
                "name": name,
                "tier_label": tpl["tier_label"],
                "room_type": tpl["room_type"],
                "price_per_night": price,
                "rating": round(rating, 1),
                "tags": ["免费取消", "含早餐", "近地铁"] if tpl["tier_label"] != "经济型" else ["免费取消"],
                "total_price": price * nights,
            }
        )
    return hotels


def hotel_total(destination: str, nights: int) -> int:
    """计算住宿总价（取舒适型作为默认推荐）。"""
    hotels = generate_hotels(destination, [], nights)
    # 取舒适型（中间档）作为预算基准
    comfort = hotels[1] if len(hotels) > 1 else hotels[0]
    return comfort["total_price"]
