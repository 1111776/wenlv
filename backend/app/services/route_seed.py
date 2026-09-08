"""经典线路模板种子数据（旅行社固定路线库）。

预置 6 条经典线路，用户选模板即可秒出行程，再按需微调。
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import RouteTemplate

# 经典线路模板（结构化 daily_plan：每天上午/下午/晚上 + 餐饮提示）
SEED_ROUTES = [
    {
        "name": "昆大丽 6 日经典游",
        "destination": "云南",
        "days": 6,
        "tags": ["自然风光", "人文历史", "休闲"],
        "suitable_for": "亲子家庭 / 老人",
        "budget_ref": 4800,
        "description": "昆明-大理-丽江经典线路，洱海苍山、古城雪山一网打尽",
        "daily_plan": [
            {"day": 1, "morning": "昆明翠湖公园", "afternoon": "云南民族村", "evening": "南屏街夜市", "meal": "过桥米线"},
            {"day": 2, "morning": "昆明→大理", "afternoon": "大理古城", "evening": "洱海月夜", "meal": "白族三道茶"},
            {"day": 3, "morning": "洱海环湖", "afternoon": "喜洲古镇", "evening": "双廊", "meal": "酸辣鱼"},
            {"day": 4, "morning": "大理→丽江", "afternoon": "丽江古城", "evening": "四方街", "meal": "腊排骨火锅"},
            {"day": 5, "morning": "玉龙雪山", "afternoon": "蓝月谷", "evening": "束河古镇", "meal": "纳西烤鱼"},
            {"day": 6, "morning": "丽江古城自由活动", "afternoon": "返程", "evening": "", "meal": ""},
        ],
    },
    {
        "name": "华东五市 5 日游",
        "destination": "华东",
        "days": 5,
        "tags": ["人文历史", "美食", "购物"],
        "suitable_for": "情侣 / 朋友 / 家庭",
        "budget_ref": 4200,
        "description": "南京-无锡-苏州-上海-杭州五城联动，江南水乡精华",
        "daily_plan": [
            {"day": 1, "morning": "南京中山陵", "afternoon": "夫子庙", "evening": "秦淮河", "meal": "盐水鸭"},
            {"day": 2, "morning": "无锡鼋头渚", "afternoon": "灵山大佛", "evening": "南长街", "meal": "无锡排骨"},
            {"day": 3, "morning": "苏州拙政园", "afternoon": "虎丘", "evening": "平江路", "meal": "松鼠桂鱼"},
            {"day": 4, "morning": "上海外滩", "afternoon": "东方明珠", "evening": "南京路", "meal": "本帮菜"},
            {"day": 5, "morning": "杭州西湖", "afternoon": "灵隐寺", "evening": "返程", "meal": "西湖醋鱼"},
        ],
    },
    {
        "name": "京沪 5 日双城游",
        "destination": "北京-上海",
        "days": 5,
        "tags": ["人文历史", "地标", "都市"],
        "suitable_for": "家庭 / 学生研学",
        "budget_ref": 4500,
        "description": "北京皇城根 + 上海摩登都市，一北一南双城经典",
        "daily_plan": [
            {"day": 1, "morning": "故宫", "afternoon": "景山公园", "evening": "王府井", "meal": "北京烤鸭"},
            {"day": 2, "morning": "八达岭长城", "afternoon": "鸟巢水立方", "evening": "簋街", "meal": "炸酱面"},
            {"day": 3, "morning": "颐和园", "afternoon": "天坛", "evening": "飞上海", "meal": ""},
            {"day": 4, "morning": "外滩", "afternoon": "豫园", "evening": "南京路", "meal": "本帮菜"},
            {"day": 5, "morning": "迪士尼乐园", "afternoon": "田子坊", "evening": "返程", "meal": ""},
        ],
    },
    {
        "name": "川西环线 5 日游",
        "destination": "川西",
        "days": 5,
        "tags": ["自然风光", "摄影", "雪山"],
        "suitable_for": "青年 / 摄影爱好者（老人儿童慎选）",
        "budget_ref": 5500,
        "description": "四姑娘山-丹巴-新都桥-稻城亚丁，摄影天堂",
        "daily_plan": [
            {"day": 1, "morning": "成都→四姑娘山", "afternoon": "双桥沟", "evening": "日隆镇", "meal": "藏餐"},
            {"day": 2, "morning": "四姑娘山", "afternoon": "丹巴藏寨", "evening": "丹巴", "meal": "藏香猪"},
            {"day": 3, "morning": "丹巴→新都桥", "afternoon": "塔公草原", "evening": "新都桥", "meal": "牦牛肉"},
            {"day": 4, "morning": "新都桥→稻城", "afternoon": "海子山", "evening": "香格里拉镇", "meal": ""},
            {"day": 5, "morning": "稻城亚丁", "afternoon": "冲古寺", "evening": "返程", "meal": ""},
        ],
    },
    {
        "name": "西北大环线 7 日游",
        "destination": "西北",
        "days": 7,
        "tags": ["自然风光", "摄影", "自驾"],
        "suitable_for": "青年 / 摄影（海拔较高，老人儿童慎选）",
        "budget_ref": 6800,
        "description": "青海湖-茶卡盐湖-敦煌-张掖，大西北壮美风光",
        "daily_plan": [
            {"day": 1, "morning": "西宁→青海湖", "afternoon": "环湖", "evening": "黑马河", "meal": "手抓羊肉"},
            {"day": 2, "morning": "茶卡盐湖", "afternoon": "翡翠湖", "evening": "大柴旦", "meal": ""},
            {"day": 3, "morning": "大柴旦→敦煌", "afternoon": "鸣沙山月牙泉", "evening": "敦煌夜市", "meal": "驴肉黄面"},
            {"day": 4, "morning": "莫高窟", "afternoon": "阳关", "evening": "沙洲夜市", "meal": ""},
            {"day": 5, "morning": "敦煌→嘉峪关", "afternoon": "嘉峪关关城", "evening": "张掖", "meal": "羊肉粉汤"},
            {"day": 6, "morning": "张掖丹霞", "afternoon": "祁连草原", "evening": "西宁", "meal": ""},
            {"day": 7, "morning": "塔尔寺", "afternoon": "返程", "evening": "", "meal": ""},
        ],
    },
    {
        "name": "三亚休闲 4 日游",
        "destination": "三亚",
        "days": 4,
        "tags": ["海岛", "亲子", "休闲"],
        "suitable_for": "亲子家庭 / 情侣 / 老人",
        "budget_ref": 5200,
        "description": "亚龙湾-蜈支洲-南山，阳光沙滩度假首选",
        "daily_plan": [
            {"day": 1, "morning": "亚龙湾", "afternoon": "海底世界", "evening": "第一市场", "meal": "海鲜"},
            {"day": 2, "morning": "蜈支洲岛", "afternoon": "潜水/沙滩", "evening": "三亚湾", "meal": "海南鸡饭"},
            {"day": 3, "morning": "南山文化旅游区", "afternoon": "天涯海角", "evening": "大东海", "meal": "椰子鸡"},
            {"day": 4, "morning": "免税店", "afternoon": "返程", "evening": "", "meal": ""},
        ],
    },
]


async def seed_routes(db: AsyncSession) -> None:
    """幂等写入经典线路模板：已存在（同名）则跳过。"""
    for r in SEED_ROUTES:
        existing = await db.execute(select(RouteTemplate).where(RouteTemplate.name == r["name"]))
        if existing.scalar_one_or_none() is None:
            db.add(
                RouteTemplate(
                    name=r["name"],
                    destination=r["destination"],
                    days=r["days"],
                    tags=r["tags"],
                    suitable_for=r["suitable_for"],
                    budget_ref=r["budget_ref"],
                    description=r["description"],
                    daily_plan=r["daily_plan"],
                )
            )
    await db.flush()
