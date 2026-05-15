import json
from google import genai

from config import GEMINI_API_KEY
from services.omdb_client import fetch_omdb_info

client = genai.Client(api_key=GEMINI_API_KEY)

async def find_movies_by_mood(mood_query: str) -> dict:
    try:
        model_name = 'gemini-3.1-flash-lite'
        
        prompt = f"""
        You are a cinematic curator. The user input is: "{mood_query}"
        
        RULES:
        1. IF the user explicitly names a specific movie or TV show, YOUR FIRST RESULT MUST BE THAT EXACT TITLE. The next 2 results should be similar recommendations.
        2. IF the user describes a mood/vibe, recommend 3 perfectly matching titles.
        3. EXACT TITLE IN ORIGINAL LANGUAGE: You must provide the original English title (e.g., "From" for "ЗЗОВНІ").
        4. You can recommend both MOVIES and TV SHOWS.
        
        Return STRICTLY a JSON object:
        {{
            "movies": [
                {{
                    "title": "Exact Title in English",
                    "year": "Release Year",
                    "match_reason": "Brief explanation in Ukrainian."
                }}
            ]
        }}
        """
        
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={'response_mime_type': 'application/json'}
        )
        
        result_data = json.loads(response.text)
        
        for movie in result_data.get("movies", []):
            omdb = await fetch_omdb_info(movie["title"], movie.get("year"))
            movie["poster"] = omdb["poster_url"]
                    
        return result_data

    except Exception as e:
        print(f"Помилка генерації: {e}")
        return {
            "movies": [
                {
                    "title": "Помилка системи",
                    "year": "ERROR",
                    "match_reason": str(e),
                    "poster": "https://placehold.co/300x450/111111/333333?text=ERROR"
                }
            ]
        }