"""团建规划路由（秒出模板版）。

团建 ≠ 旅游：核心是「场地 + 活动 + 餐饮 + 人均预算」，不是景点/门票。
预置 6 类团建模板，用户填类型/人数/时长/预算 → 秒出方案 + 人均预算明细。
"""

from __future__ import annotations

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from app.schemas.common import ok

router = APIRouter(prefix="/teambuild", tags=["teambuild"])


class TeamBuildRequest(BaseModel):
    team_type: str = Field(..., description="团建类型：聚餐/桌游轰趴/烧烤/拓展/郊游/会议")
    people: int = Field(..., ge=1, le=500)
    duration_hours: float = Field(..., gt=0, le=12)
    budget: float = Field(default=0, ge=0)  # 总预算，0 表示不限
    outdoor: bool = Field(default=False)  # 是否偏好户外


# 6 类团建模板：场地 + 活动 + 餐饮 + 人均参考价
_TEAM_TEMPLATES = {
    "聚餐": {
        "label": "聚餐",
        "venues": ["包场餐厅", "私房菜馆", "火锅店", "海鲜酒楼"],
        "activities": ["破冰开场", "圆桌交流", "敬酒/茶话", "合影留念"],
        "food": "正餐一桌（10 人/桌，按人头配菜）",
        "venue_per_person": 80,
        "food_per_person": 100,
        "note": "适合部门聚餐、欢迎会、庆功宴，氛围轻松。",
    },
    "桌游轰趴": {
        "label": "桌游轰趴",
        "venues": ["轰趴馆", "桌游吧", "剧本杀店", "电竞馆"],
        "activities": ["狼人杀/剧本杀", "麻将/桌游", "KTV", "台球/街机"],
        "food": "简餐/外卖 + 零食饮料",
        "venue_per_person": 60,
        "food_per_person": 50,
        "note": "适合年轻团队、小团队（10-30 人），互动性强。",
    },
    "烧烤": {
        "label": "烧烤",
        "venues": ["农家乐", "烧烤庄园", "河边烧烤场", "自助烧烤基地"],
        "activities": ["户外烧烤", "篝火晚会", "垂钓", "果蔬采摘"],
        "food": "烧烤食材自助（肉类+蔬菜+主食）",
        "venue_per_person": 50,
        "food_per_person": 80,
        "note": "适合户外团建、周末休闲，注意天气。",
    },
    "拓展": {
        "label": "拓展",
        "venues": ["拓展基地", "户外训练营", "团建营地"],
        "activities": ["破冰分组", "信任背摔", "真人 CS", "高空断桥", "团队协作游戏"],
        "food": "基地团餐（桌餐或自助）",
        "venue_per_person": 120,
        "food_per_person": 60,
        "note": "适合正式团建、培训，有专业教练带队。",
    },
    "郊游": {
        "label": "郊游",
        "venues": ["郊野公园", "古镇老街", "景区步道", "湖畔草地"],
        "activities": ["徒步/骑行", "野餐", "摄影", "放风筝", "亲子游戏"],
        "food": "野餐餐盒 + 饮用水",
        "venue_per_person": 20,
        "food_per_person": 40,
        "note": "适合轻量团建、亲子团建，成本低。",
    },
    "会议": {
        "label": "会议",
        "venues": ["酒店会议厅", "共享会议室", "培训中心"],
        "activities": ["主题会议", "头脑风暴", "分组讨论", "茶歇"],
        "food": "商务简餐 + 茶歇点心",
        "venue_per_person": 100,
        "food_per_person": 50,
        "note": "适合季度会、培训会，需投影/白板等设备。",
    },
}


@router.post("/plan")
async def plan_team_build(body: TeamBuildRequest, request: Request):
    """团建规划：按类型匹配模板，生成方案 + 人均预算明细。"""
    tmpl = _TEAM_TEMPLATES.get(body.team_type)
    if tmpl is None:
        from app.core.errors import Err

        raise Err.INVALID_PARAM.to_http()

    people = body.people
    duration = body.duration_hours
    budget = body.budget

    # 预算计算
    venue_cost = tmpl["venue_per_person"] * people
    food_cost = tmpl["food_per_person"] * people
    activity_cost = 0  # 大部分活动含在场地费里
    total = venue_cost + food_cost + activity_cost
    per_person = total / people if people else 0

    # 预算是否超
    over = budget > 0 and total > budget
    over_ratio = ((total - budget) / budget) if (budget > 0 and over) else 0.0

    # 时间安排（按小时排）
    schedule = []
    schedule.append(f"开始（0:00-0:15）到场集合、签到")
    schedule.append(f"破冰热身（0:15-0:30）")
    mid = duration / 2
    schedule.append(f"主活动（0:30-{mid:.1f} 小时）{tmpl['activities'][0]} 等")
    schedule.append(f"餐饮（{mid:.1f}-{mid+0.75:.1f} 小时）{tmpl['food']}")
    schedule.append(f"自由活动/收尾（剩余时间）合影留念、返程")

    # 户外郊游/烧烤建议
    tips = []
    if body.team_type in ("烧烤", "郊游") and not body.outdoor:
        tips.append("户外活动，建议提前查看天气，备好防晒/雨具")
    if people > 50:
        tips.append("人数较多，建议提前预订场地并分组管理")

    return ok({
        "team_type": tmpl["label"],
        "people": people,
        "duration_hours": duration,
        "venues": tmpl["venues"],
        "activities": tmpl["activities"],
        "food": tmpl["food"],
        "note": tmpl["note"],
        "schedule": schedule,
        "budget": {
            "venue": venue_cost,
            "food": food_cost,
            "activity": activity_cost,
            "total": total,
            "per_person": round(per_person, 1),
            "budget_limit": budget,
            "over": over,
            "over_ratio": round(over_ratio, 2),
        },
        "tips": tips,
    })


@router.get("/types")
async def list_types(request: Request):
    """团建类型列表。"""
    items = [
        {"value": k, "label": v["label"], "note": v["note"]}
        for k, v in _TEAM_TEMPLATES.items()
    ]
    return ok({"items": items})
