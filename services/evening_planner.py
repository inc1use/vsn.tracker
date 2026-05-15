import asyncio
import json
from typing import Any

from google import genai

from config import GEMINI_API_KEY
from services.omdb_client import fetch_omdb_info

client = genai.Client(api_key=GEMINI_API_KEY)
MODEL = "gemini-3.1-flash-lite"

COMPANY_LABELS = {
    "alone": "наодинці",
    "couple": "вдвоє (пара)",
    "friends": "з друзями / компанією",
}

FORMAT_LABELS = {
    "movie": "фільм(и)",
    "series": "серіал (кілька серій)",
    "either": "на вибір ШІ",
}


def _build_prompt(
    hours: float,
    company: str,
    mood: str,
    media_format: str,
    snacks: bool,
) -> str:
    company_ua = COMPANY_LABELS.get(company, company)
    format_ua = FORMAT_LABELS.get(media_format, media_format)
    snacks_ua = "так, включи перерви на перекус" if snacks else "мінімум перерв"

    mood_line = mood.strip() if mood.strip() else "універсальний затишний вечір"

    return f"""
    You are an expert evening planner for movie nights. Create a realistic timeline in Ukrainian.

    User parameters:
    - Available time: {hours} hours ({int(hours * 60)} minutes total, including breaks)
    - Company: {company_ua}
    - Mood / vibe: {mood_line}
    - Preferred format: {format_ua}
    - Snack breaks: {snacks_ua}

    RULES:
    1. Fill the timeline to fit within {hours} hours. Include prep, watch blocks, and breaks.
    2. For "movie": usually 1 main film (+ optional short backup slot).
    3. For "series": 2-4 episodes of ONE series (state episode range, e.g. S01E01-E03).
    4. For "either": pick what fits best for the mood and time.
    5. Titles in ORIGINAL ENGLISH. Descriptions in Ukrainian.
    6. Be creative with break activities (popcorn, discussion, stretch) — match the company type.
    7. Include exactly ONE backup pick if the main choice does not land.

    Return STRICTLY this JSON (no markdown):
    {{
        "title": "Catchy evening plan title in Ukrainian",
        "subtitle": "One line mood summary in Ukrainian",
        "total_minutes": 180,
        "timeline": [
            {{
                "time_label": "19:00",
                "type": "prep",
                "label": "Старт",
                "description": "What to do in Ukrainian",
                "duration_minutes": 15
            }},
            {{
                "time_label": "19:15",
                "type": "watch",
                "label": "Головний перегляд",
                "title": "Exact English Title",
                "year": "YYYY",
                "media_type": "movie",
                "episode_info": "",
                "duration_minutes": 120,
                "description": "Why this fits the evening, in Ukrainian"
            }},
            {{
                "time_label": "21:15",
                "type": "break",
                "label": "Пауза",
                "description": "Break activity in Ukrainian",
                "duration_minutes": 15
            }}
        ],
        "backup": {{
            "title": "Exact English Title",
            "year": "YYYY",
            "media_type": "movie",
            "reason": "Why this backup in Ukrainian"
        }},
        "tip": "One fun pro-tip for this specific evening in Ukrainian"
    }}

    Types for timeline items: "prep", "watch", "break" only.
    For series watch items set media_type to "series" and episode_info like "S01E01–E03".
    """


async def _enrich_watch_item(item: dict) -> None:
    if item.get("type") != "watch" or not item.get("title"):
        return
    omdb = await fetch_omdb_info(item["title"], item.get("year"))
    item["poster_url"] = omdb["poster_url"]


async def _enrich_backup(backup: dict) -> None:
    if not backup.get("title"):
        return
    omdb = await fetch_omdb_info(backup["title"], backup.get("year"))
    backup["poster_url"] = omdb["poster_url"]


async def build_evening(
    hours: float,
    company: str,
    mood: str,
    media_format: str,
    snacks: bool,
) -> dict:
    prompt = _build_prompt(hours, company, mood, media_format, snacks)

    response = await asyncio.to_thread(
        lambda: client.models.generate_content(
            model=MODEL,
            contents=prompt,
            config={"response_mime_type": "application/json"},
        )
    )

    plan: dict[str, Any] = json.loads(response.text)

    timeline = plan.get("timeline", [])
    enrich_tasks = [_enrich_watch_item(item) for item in timeline]
    enrich_tasks.append(_enrich_backup(plan.get("backup") or {}))
    await asyncio.gather(*enrich_tasks)

    plan["source"] = "gemini+omdb"
    return plan
