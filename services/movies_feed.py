import asyncio
import json
from datetime import datetime, timedelta
from typing import Any

from google import genai

from config import GEMINI_API_KEY
from services.omdb_client import fetch_omdb_info

_cache: dict[str, tuple[datetime, Any]] = {}
CACHE_TTL_SECONDS = 3600

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-flash-lite"


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


async def _enrich_movie(item: dict) -> dict:
    omdb = await fetch_omdb_info(item["title"], item.get("year"))
    overview = item.get("overview") or omdb["overview"]
    if len(overview) > 220:
        overview = overview[:217].rstrip() + "…"

    vote = item.get("vote_average") or omdb["vote_average"]
    if omdb["vote_average"] > 0:
        vote = omdb["vote_average"]

    return {
        "id": f"{item['title']}-{item.get('year', '')}",
        "title": item["title"],
        "release_date": item.get("release_date") or item.get("year", ""),
        "poster_url": omdb["poster_url"],
        "vote_average": round(float(vote or 0), 1),
        "popularity": int(item.get("popularity") or 0),
        "overview": overview,
    }


async def _enrich_list(items: list[dict]) -> list[dict]:
    if not items:
        return []
    enriched = await asyncio.gather(*[_enrich_movie(m) for m in items])
    return list(enriched)


def _fetch_lists_from_gemini() -> dict:
    year = datetime.now().year
    prompt = f"""
    You are a film industry analyst. Today is {datetime.now().strftime("%Y-%m-%d")}.

    Return STRICTLY a JSON object with three arrays of REAL movies (English original titles).
    Use your knowledge of cinema in {year} and recent years. Each array must have exactly 10 items.

    Categories:
    1. now_playing — films currently in wide theatrical release or very recent blockbusters ({year}).
    2. upcoming — films announced or releasing soon (next 3–6 months).
    3. popular — all-time or recent audience favorites with high cultural impact.

    Each item:
    {{
        "title": "Exact English title",
        "year": "YYYY",
        "release_date": "YYYY-MM-DD or YYYY if unknown",
        "overview": "One sentence in Ukrainian.",
        "vote_average": 7.5,
        "popularity": 85
    }}

    vote_average: realistic IMDb-style 0–10.
    popularity: arbitrary buzz score 1–100 (higher = more popular).

    JSON only, no markdown.
    """

    response = client.models.generate_content(
        model=MODEL,
        contents=prompt,
        config={"response_mime_type": "application/json"},
    )
    return json.loads(response.text)


async def get_movie_discover() -> dict:
    cache_key = "movie_discover_gemini"
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached

    raw = await asyncio.to_thread(_fetch_lists_from_gemini)

    now_playing, upcoming, popular = await asyncio.gather(
        _enrich_list(raw.get("now_playing", [])[:10]),
        _enrich_list(raw.get("upcoming", [])[:10]),
        _enrich_list(raw.get("popular", [])[:10]),
    )

    result = {
        "now_playing": now_playing,
        "upcoming": upcoming,
        "popular": popular,
        "source": "gemini+omdb",
    }
    _cache_set(cache_key, result)
    return result
