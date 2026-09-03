"""Itinerary Agent：日程编排（说明书 §5.1 第 5 节点）。

用高德真实数据编排行程：
- 读取 Web Research 节点通过高德 POI 搜索收集的真实景点；
- 用高德路径规划计算相邻景点间的真实驾车距离与耗时（并发，加速）；
- 按天生成上午/下午/晚上三段行程，附真实路线数据；
- night_risk 由 hitl_demo 开关控制（演示 HITL 用，真实数据下默认不触发）。
"""

from __future__ import annotations

import asyncio
import re
import uuid

from sqlalchemy import select

from app.agents.llm import build_system_prompt, get_llm
from app.core.config import settings
from app.core.database import session_scope
from app.core.logging import get_logger
from app.graph.state import TravelState
from app.models import AgentTask
from app.models.agent_task import TASK_STATUS
from app.services.amap import AmapError, driving_route, geocode

logger = get_logger(__name__)


def _party_size(preferences: dict) -> int:
    """计算出行总人数（成人+儿童+老人），最少 1 人。"""
    adults = preferences.get("adults")
    children = preferences.get("children", 0)
    elders = preferences.get("elders", 0)
    if adults is None:
        party = preferences.get("party") or {}
        adults = party.get("adults", 1)
        children = party.get("children", 0)
        elders = party.get("elders", 0)
    return max(int(adults or 1) + int(children or 0) + int(elders or 0), 1)


def _collect_pois(tasks: list[AgentTask]) -> tuple[list[dict], list[dict]]:
    """从 web_research 任务结果里汇总真实 POI，按类别分成「景点」和「餐厅」。

    返回 (attractions, restaurants)：
    - attractions：风景/公园/博物馆/购物等游玩类
    - restaurants：餐饮美食类（keyword=餐厅 的任务结果）
    """
    seen: set[str] = set()
    attractions: list[dict] = []
    restaurants: list[dict] = []

    for t in tasks:
        if t.agent_type != "web_research" or not t.result:
            continue
        keyword = t.result.get("keyword", "")
        # 餐饮类关键词：餐厅/美食/早餐/快餐/小吃/咖啡 等都算餐厅，供三餐编排
        is_food = any(k in keyword for k in ["餐厅", "美食", "早餐", "快餐", "小吃", "咖啡", "面", "火锅", "烧烤"])
        is_hotel = "酒店" in keyword or "住宿" in keyword
        is_transport = "地铁" in keyword or "交通" in keyword or "站" in keyword

        for p in t.result.get("pois", []):
            name = p.get("name")
            loc = p.get("location")
            if not name or not loc or loc == (None, None):
                continue
            if name in seen:
                continue
            seen.add(name)
            # 附带 keyword 信息，便于分类
            p = {**p, "_keyword": keyword}
            if is_food:
                restaurants.append(p)
            elif is_hotel or is_transport:
                # 酒店/地铁站等不进 daily_plan（酒店在酒店推荐章节，交通是设施非景点），跳过
                continue
            else:
                attractions.append(p)

    return attractions, restaurants


# 夜生活/娱乐场所关键词（这类 POI 只排晚上，不占白天景点位）
_NIGHTLIFE_KEYWORDS = [
    "KTV", "ktv", "酒吧", "酒馆", "夜店", "电竞", "网吧", "网咖", "网盟",
    "足浴", "洗浴", "桑拿", "电影院", "影院", "剧场", "演艺", "歌厅", "舞厅",
    "密室", "桌游", "清吧", "夜总会", "迪厅", "俱乐部", "Livehouse", "livehouse",
    "小酒馆", "烤吧", "餐吧",
]

# 家庭/老人出行不适宜的夜生活场所（有儿童或老人时直接剔除，只保留影院/剧场等全家友好型）
_FAMILY_UNFRIENDLY_NIGHTLIFE = [
    "网吧", "网咖", "网盟", "酒吧", "酒馆", "夜店", "夜总会", "KTV", "ktv",
    "足浴", "洗浴", "桑拿", "歌厅", "舞厅", "密室", "桌游", "清吧", "迪厅",
    "俱乐部", "Livehouse", "livehouse", "小酒馆", "烤吧", "餐吧", "电竞",
]

# 老人出行不适合的高强度/风险景点（高海拔/剧烈运动/长时间步行）
_ELDER_UNSUITABLE = [
    "滑雪", "漂流", "蹦极", "攀岩", "跳伞", "潜水", "冲浪", "登山", "徒步",
    "越野", "滑翔", "过山车", "极限", "索道", "雪山", "冰川", "高原", "爬山",
    "攀爬", "峡谷",
]

# 儿童出行不适合的景点/场所（部分与夜生活重叠，白天景点也可能出现）
_CHILD_UNSUITABLE = [
    "酒吧", "夜店", "KTV", "足浴", "桑拿", "密室", "桌游", "夜总会", "赌场",
]

# 儿童友好的景点（有儿童时排序靠前）
_CHILD_FRIENDLY_KEYWORDS = [
    "乐园", "动物园", "水族馆", "科技馆", "游乐园", "公园", "海洋", "亲子",
    "儿童", "城堡", "博物馆", "主题",
]

# 老人友好的景点（平缓、节奏慢，有老人时排序靠前）
_ELDER_FRIENDLY_KEYWORDS = [
    "公园", "园林", "博物馆", "古镇", "古城", "广场", "湖", "老街", "故居",
    "寺庙", "纪念馆", "美术馆",
]

# 兴趣标签 → POI 文本同义词（用于按兴趣优先排序景点）
_TAG_SYNONYMS = {
    "自然风光": ["公园", "风景", "山", "湖", "岛", "森林", "瀑布", "湿地", "海滩", "海湾", "草原", "峡谷", "河"],
    "人文历史": ["博物馆", "古城", "寺庙", "故居", "古迹", "老街", "遗址", "纪念馆", "古镇", "园林"],
    "美食": ["美食", "小吃", "餐厅", "夜市", "街", "巷", "市场"],
    "亲子": ["乐园", "动物园", "水族馆", "科技馆", "游乐园", "公园", "亲子", "儿童"],
    "购物": ["购物", "商场", "步行街", "百货", "奥莱", "免税"],
    "海岛": ["岛", "海滩", "海", "沙滩", "潜水", "游船", "海洋"],
    "滑雪": ["滑雪", "雪场", "雪"],
    "温泉": ["温泉", "汤"],
    "摄影": ["风景", "湖", "山", "塔", "观景", "日出", "日落"],
    "徒步": ["山", "峡谷", "栈道", "步道", "森林", "徒步"],
    "夜生活": ["酒吧", "夜市", "夜景", "剧场", "影院"],
    "宗教": ["寺", "庙", "教堂", "宫", "佛", "观"],
    "历史": ["博物馆", "古城", "遗址", "故居", "古迹", "古镇"],
    "文化": ["博物馆", "古城", "艺术", "故居", "纪念馆", "美术馆"],
}

# 购物/商场类（不是风景/景点，不排进每日观光行程，避免「自然风光」行程里塞满商场）
_SHOPPING_KEYWORDS = [
    "购物中心", "购物广场", "商场", "百货", "商贸", "商业街", "批发市场",
    "奥莱", "奥特莱斯", "免税店", "超市", "卖场",
]

# 餐次关键词：把餐厅归类到早餐/正餐/晚餐（避免早餐排火锅、午餐排烧烤）
_BREAKFAST_KEYWORDS = [
    "早餐", "包子", "粥", "豆浆", "油条", "馒头", "面包", "烘焙", "汉堡",
    "麦当劳", "肯德基", "德克士", "华莱士", "星巴克", "咖啡", "粉",
    "煎饼", "馄饨", "饺子", "汤包", "蒸饺", "豆腐脑", "烧饼", "肠粉", "米粉",
    "早茶", "点心", "甜品", "奶茶", "快餐", "面", "小吃",
]
_DINNER_KEYWORDS = [
    "火锅", "烧烤", "烤鱼", "海鲜", "日料", "西餐", "牛排", "夜宵",
    "大排档", "串串", "麻辣烫", "龙虾", "烤全羊", "铁板",
]


def _is_nightlife(poi: dict) -> bool:
    """判断 POI 是否夜生活/娱乐场所（KTV/酒吧/网吧/影院等），只适合晚上。"""
    text = f"{poi.get('name', '')} {poi.get('type', '')}"
    return any(k in text for k in _NIGHTLIFE_KEYWORDS)


def _is_family_unfriendly_nightlife(poi: dict) -> bool:
    """判断夜生活场所是否不适合儿童/老人（网吧/酒吧/KTV/足浴等）。"""
    text = f"{poi.get('name', '')} {poi.get('type', '')}"
    return any(k in text for k in _FAMILY_UNFRIENDLY_NIGHTLIFE)


def _is_unsuitable_for_party(poi: dict, has_elder: bool, has_child: bool) -> bool:
    """判断景点是否不适合当前出行人群（老人/儿童）。"""
    text = f"{poi.get('name', '')} {poi.get('type', '')}"
    if has_elder and any(k in text for k in _ELDER_UNSUITABLE):
        return True
    if has_child and any(k in text for k in _CHILD_UNSUITABLE):
        return True
    return False


def _tag_score(poi: dict, tags: list[str]) -> float:
    """按兴趣标签给 POI 打分，用于兴趣优先排序（匹配越多分越高）。"""
    text = f"{poi.get('name', '')} {poi.get('type', '')}"
    score = 0.0
    for tag in tags or []:
        if not tag:
            continue
        if tag in text:
            score += 2.0
        for syn in _TAG_SYNONYMS.get(tag, []):
            if syn in text:
                score += 1.5
    return score


def _party_friendly_score(poi: dict, has_elder: bool, has_child: bool) -> float:
    """按出行人群给景点适配加分（亲子/老人友好优先）。"""
    text = f"{poi.get('name', '')} {poi.get('type', '')}"
    score = 0.0
    if has_child and any(k in text for k in _CHILD_FRIENDLY_KEYWORDS):
        score += 3.0
    if has_elder and any(k in text for k in _ELDER_FRIENDLY_KEYWORDS):
        score += 3.0
    return score


def _is_shopping(poi: dict) -> bool:
    """判断 POI 是否购物/商场类（不进每日观光行程）。"""
    text = f"{poi.get('name', '')} {poi.get('type', '')}"
    return any(k in text for k in _SHOPPING_KEYWORDS)


def _rating(poi: dict) -> float:
    """POI 评分（高德 biz_ext.rating 是字符串），无评分返回 0。"""
    try:
        return float(poi.get("rating") or 0)
    except (TypeError, ValueError):
        return 0.0


def _classify_meal(poi: dict) -> str:
    """把餐厅归类为 breakfast / lunch / dinner（默认正餐 lunch）。

    优先级：POI 的调研关键词标签（_keyword）> 店名关键词。
    因为 planner 专门搜了「早餐」「快餐」关键词，用标签最可靠，
    能覆盖店名里不带通用早餐词的地方特色早餐（如云南米线/饵丝/早点）。
    """
    kw = poi.get("_keyword") or ""
    # 早餐/快餐关键词搜出来的，直接归早餐类（避免漏掉地方特色早餐店）
    if kw == "早餐" or kw == "快餐":
        return "breakfast"
    text = f"{poi.get('name', '')} {poi.get('type', '')}"
    for k in _BREAKFAST_KEYWORDS:
        if k in text:
            return "breakfast"
    for k in _DINNER_KEYWORDS:
        if k in text:
            return "dinner"
    return "lunch"


def _pick_meal(restaurants: list[dict], slot: str, day_idx: int, used_names: set[str] | None = None):
    """按餐次挑餐厅：优先类型匹配，否则轮转兜底；排除已用餐厅避免每天/每餐重复。"""
    if not restaurants:
        return None
    if slot == "breakfast":
        # 早餐只吃真正的早餐/快餐/轻食（包子/粥/豆浆/咖啡/面点等），
        # 没有早餐店就留空，绝不吃烤鸭/中餐/火锅等正餐
        breakfast_typed = [r for r in restaurants if _classify_meal(r) == "breakfast"]
        # 再过滤掉店名带晚餐类关键词的（如"快餐"误搜出的"海鲜""小龙虾"）
        breakfast_typed = [
            r for r in breakfast_typed
            if not any(k in f"{r.get('name','')} {r.get('type','')}" for k in _DINNER_KEYWORDS)
        ]
        if not breakfast_typed:
            return None
        pool = breakfast_typed
    elif slot == "dinner":
        # 晚餐优先火锅/烧烤等，其次正餐，最后全量兜底
        dinner_typed = [r for r in restaurants if _classify_meal(r) == "dinner"]
        lunch_typed = [r for r in restaurants if _classify_meal(r) == "lunch"]
        pool = (dinner_typed + lunch_typed) or restaurants
    else:  # lunch
        typed = [r for r in restaurants if _classify_meal(r) == "lunch"]
        pool = typed or restaurants

    # 排除本行程已用过的餐厅（跨餐次共享），让早餐/午餐/晚餐尽量不重样；
    # 只有当全部都用过时才回退到完整 pool 重新轮转。
    used_names = used_names or set()
    available = [r for r in pool if r.get("name") not in used_names]
    if available:
        pool = available

    # 用 day_idx 取模轮转（不用 day_idx*3+slot_idx，避免 pool 长度整除步长时恒命中同一家）
    idx = day_idx % len(pool)
    return pool[idx]


async def _route_between(origin, destination) -> dict | None:
    """高德路径规划，失败返回 None（降级为无路线数据，含超时）。"""
    try:
        return await driving_route(origin, destination)
    except Exception:
        return None


async def _estimate_transport(
    origin: str, destination: str, people: int = 1, adults: int = 1,
    elders: int = 0, children_detail: list[dict] | None = None, students: int = 0,
) -> dict | None:
    """用 LLM 规划出发地到目的地的完整交通方案（去程/返程/途中建议/票价）。

    price 为【成人】票价，按高铁/飞机购票规则分档儿童/老人票价，
    返回分档明细与购票备注（婴儿/儿童证件提示、学生票不适用等）。
    高德不提供票价，用 LLM 给合理方案。失败返回 None（不阻塞主流程）。
    """
    try:
        llm = get_llm()
        result = await llm.complete(
            [
                {"role": "system", "content": build_system_prompt(
                    "transport",
                    "规划两个城市之间的往返交通，严格输出 JSON，字段："
                    '{"method":"去程交通方式(高铁/火车/大巴/飞机/自驾)",'
                    '"price":"去程单人票价(元，数字)",'
                    '"duration":"去程耗时",'
                    '"depart_time":"建议出发时间",'
                    '"on_the_way":"途中建议/路上做什么",'
                    '"return_method":"返程交通方式","return_price":"返程单人票价(元，数字)",'
                    '"return_duration":"返程耗时","note":"总述"}'
                    "注意：price 和 return_price 都是【单人】票价数字。"
                )},
                {"role": "user", "content": f"从{origin}到{destination}，{people}人出行，怎么去，单人往返票价多少，路上做什么？"},
            ],
            schema={
                "type": "object",
                "properties": {
                    "method": {"type": "string"},
                    "price": {"type": "string"},
                    "duration": {"type": "string"},
                    "depart_time": {"type": "string"},
                    "on_the_way": {"type": "string"},
                    "return_method": {"type": "string"},
                    "return_price": {"type": "string"},
                    "return_duration": {"type": "string"},
                    "note": {"type": "string"},
                },
            },
        )
        info = result.structured
        if isinstance(info, dict) and info.get("method"):
            from app.agents.ticket_pricing import transport_ticket_prices

            def _num(s):
                try:
                    return float(s)
                except (ValueError, TypeError):
                    return 0.0

            info["people"] = people
            info["ticket"] = transport_ticket_prices(
                info.get("method", ""), _num(info.get("price", 0)),
                adults, children_detail, elders, students,
            )  # 去程分档
            info["return_ticket"] = transport_ticket_prices(
                info.get("return_method", ""), _num(info.get("return_price", 0)),
                adults, children_detail, elders, students,
            )  # 返程分档
            # 兼容旧字段：total_price = 去程总价
            info["total_price"] = info["ticket"]["total"]
            info["return_total_price"] = info["return_ticket"]["total"]
            return info
        return None
    except Exception as exc:
        logger.warning("交通票价估算失败：%s", exc)
        return None


async def itinerary_node(state: TravelState) -> dict:
    """编排真实日程（高德 POI + 路径规划）。"""
    plan_id = state["plan_id"]
    preferences = state.get("preferences", {})
    days = int(preferences.get("days") or 7)
    destination = preferences.get("destination") or "目的地"
    origin = preferences.get("origin") or None  # 出发地（可选）

    # 出行人结构（成人/儿童/老人）+ 兴趣标签，用于人群过滤与兴趣排序
    _party_prefs = preferences.get("party") or {}
    _adults = int(preferences.get("adults") or _party_prefs.get("adults") or 1)
    _children = int(preferences.get("children") or _party_prefs.get("children") or 0)
    _elders = int(preferences.get("elders") or _party_prefs.get("elders") or 0)
    # 老人明细（年龄+性别，可多个），用于门票按年龄分档
    _elders_detail = preferences.get("elders_detail") or _party_prefs.get("elders_detail") or []
    # 儿童明细（年龄+身高，可多个），用于门票按年龄/身高分档
    _children_detail = preferences.get("children_detail") or _party_prefs.get("children_detail") or []
    tags = preferences.get("tags") or []
    family_mode = _children > 0 or _elders > 0

    # 节点入口读取干预补丁（D9：Agent 下一次决策优先采用干预后状态）
    excluded_attractions: list[str] = []
    try:
        from app.memory import mutator

        patch = await mutator.read_intervention_patch(plan_id)
        if patch:
            excluded_attractions = patch.get("excluded_attractions", [])
            logger.info("Itinerary 应用干预补丁 plan=%s 剔除=%s", plan_id, excluded_attractions)
            # 补丁只消费一次（幂等）
            await mutator.mark_intervention_read(plan_id)
    except Exception as exc:
        logger.warning("读取干预补丁失败：%s", exc)

    # 读 web_research 收集的真实 POI
    async with session_scope() as db:
        tasks = (
            await db.execute(
                select(AgentTask)
                .where(AgentTask.plan_id == uuid.UUID(plan_id))
                .order_by(AgentTask.order_index)
            )
        ).scalars().all()

    attractions, restaurants = _collect_pois(tasks)
    # 应用干预：剔除被主管标记为 unavailable 的景点
    if excluded_attractions:
        attractions = [p for p in attractions if p.get("name") not in excluded_attractions]
    logger.info(
        "Itinerary 收集到 %d 个景点、%d 个餐厅（剔除干预 %d 个）",
        len(attractions), len(restaurants), len(excluded_attractions),
    )

    # 知识库检索（RAG B）：按目的地+景区政策/美食召回语料，作为景点备注/餐饮参考
    kb_hits: list[dict] = []
    try:
        from app.memory.kb_retrieve import search_kb

        kb_hits = await search_kb(f"{destination} 景区政策 美食", top_k=5)
    except Exception as exc:
        logger.warning("知识库检索失败（忽略）：%s", exc)

    # 分离：夜生活/娱乐场所（KTV/酒吧/网吧/影院等）只排晚上，不占白天景点位；
    # 购物/商场类不进观光行程；同一景点（如某公园的北园/南园）去重保留评分最高。
    day_attractions: list[dict] = []
    nightlife: list[dict] = []
    seen_day: dict[str, dict] = {}
    for p in attractions:
        if _is_shopping(p):
            continue  # 商场不进每日行程
        if _is_nightlife(p):
            # 家庭/老人出行：剔除网吧/酒吧/KTV 等不适宜场所，只留影院/剧场等
            if family_mode and _is_family_unfriendly_nightlife(p):
                continue
            nightlife.append(p)
        else:
            # 同名去重：拆「-」/「(」截取主干名，同主干保留评分最高
            base = re.split(r"[-—()（）]", p.get("name", ""))[0].strip()
            key = base or p.get("name")
            if key in seen_day:
                if _rating(p) > _rating(seen_day[key]):
                    seen_day[key] = p
            else:
                seen_day[key] = p
    day_attractions = list(seen_day.values())
    if not day_attractions:
        # 极端情况：全是夜生活/购物（如某城博物馆类被娱乐场所顶替），白天兜底用全部景点
        day_attractions = [p for p in attractions if not _is_nightlife(p)] or list(attractions)
        nightlife = []

    # 人群适配：剔除老人/儿童不适合的高强度/风险景点（滑雪/漂流/蹦极等）
    if family_mode:
        filtered = [p for p in day_attractions if not _is_unsuitable_for_party(p, _elders > 0, _children > 0)]
        if filtered:  # 过滤后仍有景点才采用，避免过度过滤导致空行程
            day_attractions = filtered

    # 兴趣推荐 + 人群适配：兴趣匹配、亲子/老人友好景点排前面
    day_attractions = sorted(
        day_attractions,
        key=lambda p: _tag_score(p, tags) + _party_friendly_score(p, _elders > 0, _children > 0),
        reverse=True,
    )

    logger.info(
        "白天景点 %d 个、夜生活 %d 个", len(day_attractions), len(nightlife),
    )

    # 按天分配景点（每天 3 段：上午/下午用白天景点，晚上优先夜生活）
    daily_plan: list[dict] = []
    cursor = 0

    # 先收集所有需要路径规划的点对，一次性并发计算（加速）
    route_pairs: list[tuple[int, int, tuple, tuple]] = []
    spots_per_day: list[tuple] = []
    n_day = len(day_attractions)
    n_night = len(nightlife)
    for day in range(1, days + 1):
        am = day_attractions[(cursor * 2) % n_day] if n_day else None
        pm = day_attractions[(cursor * 2 + 1) % n_day] if n_day else None
        ev = nightlife[cursor % n_night] if n_night else (day_attractions[(cursor * 2 + 2) % n_day] if n_day else None)
        cursor += 1
        spots_per_day.append((am, pm, ev))
        if am and pm and am.get("location") and pm.get("location"):
            route_pairs.append((day - 1, "am_pm", am["location"], pm["location"]))
        if pm and ev and pm.get("location") and ev.get("location"):
            route_pairs.append((day - 1, "pm_ev", pm["location"], ev["location"]))

    # 并发计算所有路径（asyncio.gather）
    route_results = await asyncio.gather(
        *[_route_between(o, d) for _, _, o, d in route_pairs],
        return_exceptions=True,
    )
    route_map: dict[tuple[int, str], dict | None] = {}
    for (day_idx, seg, o, d), res in zip(route_pairs, route_results):
        route_map[(day_idx, seg)] = res if not isinstance(res, Exception) else None

    # 组装 daily_plan（景点 + 三餐餐饮）
    from app.agents.ticket_pricing import meal_price, ticket_prices_by_party

    def _fmt_spot(poi, route_to_next):
        tp = ticket_prices_by_party(
            poi["name"], poi.get("type", ""), _adults, _children, _elders, _elders_detail, _children_detail
        )
        return {
            "spot": poi["name"],
            "address": poi.get("address", ""),
            "type": poi.get("type", ""),
            "route": route_to_next,
            "opentime": poi.get("opentime", ""),
            "rating": poi.get("rating", ""),
            "photo": poi.get("photo", ""),
            "ticket": tp,  # 门票分档结构（成人/儿童/老人）
            "price": tp["total"],  # 门票总价（兼容旧的 price 字段）
            "note": tp.get("note"),  # 老人/儿童优待备注
        }

    def _fmt_meal(poi):
        return {
            "name": poi["name"],
            "address": poi.get("address", ""),
            "type": poi.get("type", ""),
            "opentime": poi.get("opentime", ""),
            "rating": poi.get("rating", ""),
            "photo": poi.get("photo", ""),
            "price": meal_price(poi["name"], poi.get("type", "")),  # 人均价
        }

    # 跨天已用餐厅集合：保证每天/每餐尽量不重复（全用过才回退）
    used_meals: set[str] = set()

    for day_idx, (am, pm, ev) in enumerate(spots_per_day):
        am_pm_route = route_map.get((day_idx, "am_pm"))
        pm_ev_route = route_map.get((day_idx, "pm_ev"))

        # 三餐：按餐次类型匹配（早餐不吃火锅、晚餐优先火锅烧烤），同类型内轮转
        breakfast = _pick_meal(restaurants, "breakfast", day_idx, used_meals)
        lunch = _pick_meal(restaurants, "lunch", day_idx, used_meals)
        dinner = _pick_meal(restaurants, "dinner", day_idx, used_meals)
        for m in (breakfast, lunch, dinner):
            if m and m.get("name"):
                used_meals.add(m["name"])

        daily_plan.append(
            {
                "day": day_idx + 1,
                "morning": _fmt_spot(am, am_pm_route),
                "afternoon": _fmt_spot(pm, pm_ev_route),
                "evening": _fmt_spot(ev, None),
                "meals": {
                    "breakfast": _fmt_meal(breakfast) if breakfast else None,
                    "lunch": _fmt_meal(lunch) if lunch else None,
                    "dinner": _fmt_meal(dinner) if dinner else None,
                },
            }
        )

    # 路线串联（取每天首站）
    route_names = [d["morning"]["spot"] for d in daily_plan if d["morning"]["spot"]]
    route = f"{destination} → " + " → ".join(route_names) if route_names else destination

    # 出发地 → 目的地 路线（若填了出发地，用高德算 origin → 首个景点）
    # 注意：捕获所有异常（含 httpx 超时），拿不到路线不阻塞主流程
    origin_route = None
    if origin and attractions:
        try:
            origin_loc = await geocode(origin)
            first_spot = attractions[0]
            if origin_loc and first_spot.get("location") and first_spot["location"] != (None, None):
                origin_route = await driving_route(origin_loc, first_spot["location"])
        except Exception:
            origin_route = None

    # 出发地到目的地的交通方式 + 票价（LLM 估算，高德不提供票价）
    transport_info = None
    if origin and destination:
        try:
            people = _party_size(preferences)
            _a = preferences.get("adults", preferences.get("party", {}).get("adults", 1))
            _e = preferences.get("elders", preferences.get("party", {}).get("elders", 0))
            _cd = preferences.get("children_detail") or preferences.get("party", {}).get("children_detail") or []
            _stu = preferences.get("students") or preferences.get("party", {}).get("students") or 0
            transport_info = await _estimate_transport(origin, destination, people, _a, _e, _cd, _stu)
        except Exception:
            transport_info = None

    # 夜行风险：默认 False（真实数据下高德不返回夜行信息，不会误触发审核）
    night_risk = False

    itinerary = {
        "days": days,
        "destination": destination,
        "origin": origin,
        "origin_route": origin_route,  # 出发地到首站的真实路线（距离/耗时）
        "transport": transport_info,  # 交通方式 + 票价
        "daily_plan": daily_plan,
        "route": route,
        "night_risk": night_risk,
        "poi_count": len(attractions),
        "restaurant_count": len(restaurants),
        "kb_hits": kb_hits,  # 知识库检索结果（供报告引用）
        "data_source": "amap",
    }

    # 日程编排用高德数据 + 规则模板，无需 LLM（提速）
    async with session_scope() as db:
        from sqlalchemy import delete

        await db.execute(
            delete(AgentTask).where(
                AgentTask.plan_id == uuid.UUID(plan_id),
                AgentTask.agent_type == "itinerary",
            )
        )
        db.add(
            AgentTask(
                plan_id=uuid.UUID(plan_id),
                agent_type="itinerary",
                order_index=101,
                status=TASK_STATUS["COMPLETED"],
                task_data={"title": "日程编排"},
                result=itinerary,
            )
        )
        await db.flush()

    logger.info("Itinerary 生成完成 plan=%s days=%d 景点=%d 餐厅=%d", plan_id, days, len(attractions), len(restaurants))
    return {
        "night_risk": night_risk,
        "completed_nodes": state.get("completed_nodes", []) + ["itinerary"],
    }
