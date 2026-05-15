from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from fastapi.responses import FileResponse

from services.evening_planner import build_evening
from services.gemini_ai import find_movies_by_mood
from services.movies_feed import get_movie_discover
from services.tv_schedule import get_upcoming_episodes

app = FastAPI()

@app.get("/")
async def read_root():
    # Додаємо назву папки перед назвою файлу
    return FileResponse("templates/index.html")

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")


class MoodRequest(BaseModel):
    mood: str


class EveningRequest(BaseModel):
    hours: float = 3.0
    company: str = "alone"  # alone | couple | friends
    mood: str = ""
    format: str = "either"  # movie | series | either
    snacks: bool = True


@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/api/find-mood")
async def api_find_mood(request: MoodRequest):
    result = await find_movies_by_mood(request.mood)
    return result


@app.get("/api/movies/discover")
async def api_movies_discover():
    try:
        return await get_movie_discover()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Не вдалося завантажити новинки (Gemini / OMDb)",
        ) from exc


@app.post("/api/build-evening")
async def api_build_evening(request: EveningRequest):
    hours = max(1.5, min(6.0, request.hours))
    company = request.company if request.company in ("alone", "couple", "friends") else "alone"
    media_format = request.format if request.format in ("movie", "series", "either") else "either"

    try:
        return await build_evening(
            hours=hours,
            company=company,
            mood=request.mood,
            media_format=media_format,
            snacks=request.snacks,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Не вдалося скласти план вечора",
        ) from exc


@app.get("/api/tv/upcoming-episodes")
async def api_tv_upcoming_episodes():
    try:
        return await get_upcoming_episodes()
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail="Не вдалося завантажити розклад серіалів (TVmaze)",
        ) from exc
