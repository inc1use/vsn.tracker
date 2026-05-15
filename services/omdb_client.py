import asyncio
import urllib.parse

import httpx

from config import OMDB_API_KEY

PLACEHOLDER_POSTER = "https://placehold.co/300x450/111118/444?text=No+Poster"


async def fetch_omdb_info(title: str, year: str | None = None) -> dict:
    """Постер, рейтинг IMDb та короткий опис з OMDb."""
    return await asyncio.to_thread(_fetch_omdb_info_sync, title, year)


def _fetch_omdb_info_sync(title: str, year: str | None = None) -> dict:
    try:
        params = {"t": title, "apikey": OMDB_API_KEY}
        if year:
            params["y"] = year

        url = f"http://www.omdbapi.com/?{urllib.parse.urlencode(params)}"
        response = httpx.get(url, timeout=8.0)
        data = response.json()

        if data.get("Response") != "True":
            return _empty_info()

        poster = data.get("Poster", "N/A")
        if poster and poster != "N/A":
            poster = poster.replace("SX300", "SX600")
        else:
            poster = PLACEHOLDER_POSTER

        rating_raw = data.get("imdbRating", "N/A")
        vote = 0.0
        if rating_raw not in (None, "N/A"):
            try:
                vote = float(rating_raw)
            except ValueError:
                pass

        plot = (data.get("Plot") or "").strip()
        if plot == "N/A":
            plot = ""

        return {
            "poster_url": poster,
            "vote_average": vote,
            "overview": plot,
        }
    except Exception as exc:
        print(f"OMDb помилка для '{title}': {exc}")
        return _empty_info()


def _empty_info() -> dict:
    return {
        "poster_url": PLACEHOLDER_POSTER,
        "vote_average": 0.0,
        "overview": "",
    }
