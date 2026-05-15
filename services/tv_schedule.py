import asyncio
import re
from datetime import date, datetime, timedelta
from typing import Any

import httpx

TVMAZE_BASE = "https://api.tvmaze.com"
SCHEDULE_DAYS = 14
MIN_SHOW_WEIGHT = 80
MAX_EPISODES = 40

_cache: dict[str, tuple[datetime, Any]] = {}
CACHE_TTL_SECONDS = 1800


def _cache_get(key: str) -> Any | None:
    entry = _cache.get(key)
    if not entry:
        return None
    expires_at, data = entry
    if datetime.now() >= expires_at:
        del _cache[key]
        return None
    return data


def _cache_set(key: str, data: Any) -> None:
    _cache[key] = (datetime.now() + timedelta(seconds=CACHE_TTL_SECONDS), data)


def _strip_html(text: str | None) -> str:
    if not text:
        return ""
    clean = re.sub(r"<[^>]+>", "", text).strip()
    if len(clean) > 180:
        clean = clean[:177].rstrip() + "…"
    return clean


def _show_poster(show: dict) -> str:
    image = show.get("image") or {}
    return (
        image.get("medium")
        or image.get("original")
        or "https://placehold.co/112x160/111118/444?text=TV"
    )


def _network_name(show: dict) -> str:
    network = show.get("network") or {}
    if network.get("name"):
        return network["name"]
    web = show.get("webChannel") or {}
    return web.get("name", "")


async def _fetch_day_schedule(
    client: httpx.AsyncClient, day: date
) -> list[dict]:
    response = await client.get(
        f"{TVMAZE_BASE}/schedule",
        params={"date": day.isoformat()},
        timeout=12.0,
    )
    response.raise_for_status()
    return response.json()


def _normalize_episode(entry: dict) -> dict | None:
    show = entry.get("show") or {}
    airdate = entry.get("airdate")
    if not airdate:
        return None

    try:
        air = date.fromisoformat(airdate)
    except ValueError:
        return None

    if air < date.today():
        return None

    weight = show.get("weight") or 0
    if weight < MIN_SHOW_WEIGHT:
        return None

    season = entry.get("season")
    number = entry.get("number")
    if season is None or number is None:
        return None

    return {
        "show_id": show.get("id"),
        "show_name": show.get("name") or "Без назви",
        "poster_url": _show_poster(show),
        "season": season,
        "episode": number,
        "episode_name": entry.get("name") or "Нова серія",
        "air_date": airdate,
        "airtime": entry.get("airtime") or "",
        "overview": _strip_html(entry.get("summary")),
        "network": _network_name(show),
        "show_weight": weight,
    }


async def get_upcoming_episodes() -> dict:
    cache_key = "tv_schedule_tvmaze"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    today = date.today()
    days = [today + timedelta(days=i) for i in range(SCHEDULE_DAYS)]

    async with httpx.AsyncClient() as client:
        daily = await asyncio.gather(
            *[_fetch_day_schedule(client, d) for d in days],
            return_exceptions=True,
        )

    # Найближча майбутня серія для кожного серіалу (за популярністю TVmaze weight)
    best_per_show: dict[int, dict] = {}

    for batch in daily:
        if isinstance(batch, Exception):
            continue
        for entry in batch:
            ep = _normalize_episode(entry)
            if not ep:
                continue
            sid = ep["show_id"]
            if sid is None:
                continue
            existing = best_per_show.get(sid)
            if not existing or ep["air_date"] < existing["air_date"]:
                best_per_show[sid] = ep

    items = sorted(
        best_per_show.values(),
        key=lambda x: (x["air_date"], -x["show_weight"]),
    )[:MAX_EPISODES]

    for item in items:
        item.pop("show_weight", None)

    result = {"episodes": items, "source": "tvmaze"}
    _cache_set(cache_key, result)
    return result
