"""高德地图 Web 服务封装（真实数据源）。

封装三个核心接口，替换原虚假种子数据：
- 地理编码 geocode/geo：地址/城市名 → 经纬度
- POI 搜索 place/text：关键词 + 城市 → 真实景点/酒店/餐饮 POI
- 路径规划 direction/driving：起终点经纬度 → 真实路线 + 距离 + 耗时

特性：
- 结果带 Redis 缓存（TTL 见 config.amap_cache_ttl），减少高德调用量；
- 接口失败抛 ``AmapError``，由调用方降级到本地种子；
- 全部走 httpx 异步，不阻塞事件循环。
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger
from app.core.redis_client import get_redis, key

logger = get_logger(__name__)

_BASE = "https://restapi.amap.com/v3"


class AmapError(Exception):
    """高德接口异常。"""


def _url(path: str, params: dict[str, Any]) -> str:
    """构造带 key 的完整 URL（params 正确序列化为查询串）。"""
    clean = {k: v for k, v in params.items() if v not in (None, "")}
    clean["key"] = settings.amap_key
    query = "&".join(f"{k}={v}" for k, v in clean.items())
    return f"{_BASE}/{path}?{query}"


async def _get(path: str, params: dict[str, Any]) -> dict:
    """带缓存的 GET 请求，返回 JSON dict。"""
    if not settings.amap_enabled or not settings.amap_key:
        raise AmapError("高德地图未启用或未配置 key")

    cache_key = key(f"amap:{path}:{_stable(params)}")
    try:
        r = get_redis()
        cached = await r.get(cache_key)
        if cached:
            return json.loads(cached)
    except Exception:
        pass  # Redis 不可用则直接请求

    url = _url(path, params)

    # 带重试：高德偶发 INVALID_USER_KEY / 网络抖动，重试一次可大幅提高成功率
    last_exc: Exception | None = None
    for attempt in range(2):
        try:
            async with httpx.AsyncClient(timeout=15, trust_env=False) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
        except Exception as exc:
            last_exc = exc
            logger.warning("高德请求失败 path=%s attempt=%d err=%s", path, attempt, exc)
            await asyncio.sleep(0.5)
            continue

        if data.get("status") != "1":
            last_exc = AmapError(f"高德返回错误: {data.get('info')} (infocode={data.get('infocode')})")
            if data.get("infocode") == "10001":  # INVALID_USER_KEY，重试
                await asyncio.sleep(0.5)
                continue
            raise last_exc

        # 成功：写缓存并返回
        try:
            r = get_redis()
            await r.set(cache_key, json.dumps(data, ensure_ascii=False), ex=settings.amap_cache_ttl)
        except Exception:
            pass
        return data

    raise last_exc or AmapError("高德请求失败")


def _stable(params: dict[str, Any]) -> str:
    """稳定的参数字符串（用于缓存 key）。"""
    import hashlib

    raw = json.dumps(params, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# 三个核心接口
# --------------------------------------------------------------------------- #


async def geocode(address: str) -> tuple[float, float] | None:
    """地理编码：地址/城市名 → (经度, 纬度)。失败返回 None。"""
    data = await _get("geocode/geo", {"address": address})
    geos = data.get("geocodes") or []
    if not geos:
        return None
    loc = geos[0].get("location", "")
    try:
        lng, lat = loc.split(",")
        return float(lng), float(lat)
    except (ValueError, AttributeError):
        return None


async def search_poi(
    keywords: str,
    city: str,
    *,
    types: str | None = None,
    offset: int = 10,
) -> list[dict]:
    """POI 关键词搜索，返回 POI 列表（标准化字段）。

    返回每条：name, location(lng,lat), address, type, typecode, tel(可选), rating(可选)。
    """
    params = {
        "keywords": keywords,
        "city": city,
        "offset": offset,
        "page": 1,
        "extensions": "base",
    }
    if types:
        params["types"] = types
    data = await _get("place/text", params)
    pois = data.get("pois") or []
    result = []
    for p in pois:
        loc = p.get("location", "")
        lng, lat = (None, None)
        if loc:
            try:
                lng_s, lat_s = loc.split(",")
                lng, lat = float(lng_s), float(lat_s)
            except ValueError:
                pass
        result.append(
            {
                "name": p.get("name"),
                "location": (lng, lat),
                "address": p.get("address") or "",
                "type": p.get("type") or "",
                "typecode": p.get("typecode") or "",
                "tel": p.get("tel") or "",
            }
        )
    return result


async def driving_route(
    origin: tuple[float, float],
    destination: tuple[float, float],
) -> dict | None:
    """驾车路径规划，返回 {distance(米), duration(秒), steps}。失败返回 None。"""
    data = await _get(
        "direction/driving",
        {
            "origin": f"{origin[0]},{origin[1]}",
            "destination": f"{destination[0]},{destination[1]}",
            "strategy": 0,
            "extensions": "base",
        },
    )
    route = data.get("route") or {}
    paths = route.get("paths") or []
    if not paths:
        return None
    p = paths[0]
    return {
        "distance": int(p.get("distance", 0)),  # 米
        "duration": int(p.get("duration", 0)),  # 秒
        "steps": len(p.get("steps", [])),
    }


# --------------------------------------------------------------------------- #
# 天气接口（复用高德 key）
# --------------------------------------------------------------------------- #


async def _resolve_adcode(address: str) -> str | None:
    """把城市名/地址解析成 adcode（高德天气接口需要 adcode）。"""
    data = await _get("geocode/geo", {"address": address})
    geos = data.get("geocodes") or []
    if not geos:
        return None
    return geos[0].get("adcode")


async def weather_now(city: str) -> dict | None:
    """实时天气，返回 {weather, temperature, winddirection, windpower, humidity, reporttime}。"""
    adcode = await _resolve_adcode(city)
    if not adcode:
        return None
    data = await _get("weather/weatherInfo", {"city": adcode, "extensions": "base"})
    lives = data.get("lives") or []
    if not lives:
        return None
    l = lives[0]
    return {
        "city": l.get("city"),
        "weather": l.get("weather"),
        "temperature": l.get("temperature"),
        "winddirection": l.get("winddirection"),
        "windpower": l.get("windpower"),
        "humidity": l.get("humidity"),
        "reporttime": l.get("reporttime"),
    }


async def weather_forecast(city: str) -> list[dict]:
    """未来天气预报（约 4 天），返回 [{date, dayweather, nightweather, daytemp, nighttemp}]。"""
    adcode = await _resolve_adcode(city)
    if not adcode:
        return []
    data = await _get("weather/weatherInfo", {"city": adcode, "extensions": "all"})
    forecasts = data.get("forecasts") or []
    if not forecasts:
        return []
    return [
        {
            "date": c.get("date"),
            "dayweather": c.get("dayweather"),
            "nightweather": c.get("nightweather"),
            "daytemp": c.get("daytemp"),
            "nighttemp": c.get("nighttemp"),
            "daywind": c.get("daywind"),
            "daypower": c.get("daypower"),
        }
        for c in forecasts[0].get("casts", [])
    ]
