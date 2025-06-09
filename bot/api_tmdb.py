import aiohttp
import logging
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from datetime import datetime
from aiogram import Bot
from bot.config import TMDB_API_KEY

logger = logging.getLogger(__name__)

GENRES = {
    "Боевик 🎬": 28, "Приключения 🏝️": 12, "Анимация 🎨": 16, "Комедия 😂": 35,
    "Криминал 🚔": 80, "Документальный 🎥": 99, "Драма 🎭": 18, "Фэнтези 🧙‍♂️": 14,
    "Ужасы 👻": 27, "Детектив 🔍": 9648, "Мелодрама 💕": 10749, "Фантастика 🚀": 878,
    "Триллер 😱": 53, "Вестерн 🤠": 37
}

BASE_URL = "https://api.themoviedb.org/3"


def base_params() -> dict:
    """Базовые параметры для всех запросов к TMDB API."""
    return {
        "api_key": TMDB_API_KEY,
        "language": "ru-RU"
    }


async def fetch(session: aiohttp.ClientSession, url: str, params: dict) -> dict:
    """Выполняет HTTP GET-запрос к TMDB API."""
    try:
        async with session.get(url, params=params) as response:
            if response.status != 200:
                error_msg = f"TMDB API error: {response.status} - {await response.text()}"
                logger.error(error_msg)
                return {"error": error_msg}
            return await response.json()
    except aiohttp.ClientError as e:
        logger.exception(f"Ошибка при выполнении запроса к TMDB: {e}")
        return {"error": str(e)}


async def fetch_movies_by_genre(session: aiohttp.ClientSession, genre_name: str, page: int = 1) -> dict:
    genre_id = GENRES.get(genre_name)
    if genre_id is None:
        return {"error": "Неверный жанр."}

    url = f"{BASE_URL}/discover/movie"
    params = {
        **base_params(),
        "with_genres": genre_id,
        "sort_by": "popularity.desc",
        "primary_release_date.gte": f"{datetime.now().year - 10}-01-01",
        "page": page
    }
    return await fetch(session, url, params)


async def fetch_top_movies(session: aiohttp.ClientSession, page: int = 1) -> dict:
    url = f"{BASE_URL}/movie/top_rated"
    params = {
        **base_params(),
        "page": page
    }
    return await fetch(session, url, params)


async def fetch_recommendations(session: aiohttp.ClientSession) -> dict:
    url = f"{BASE_URL}/trending/movie/week"
    params = base_params()
    return await fetch(session, url, params)


async def fetch_new_movies(session: aiohttp.ClientSession, page: int = 1) -> dict:
    url = f"{BASE_URL}/movie/now_playing"
    params = {
        **base_params(),
        "page": page
    }
    return await fetch(session, url, params)


async def search_movies_by_keyword(session: aiohttp.ClientSession, query: str, page: int = 1) -> dict:
    url = f"{BASE_URL}/search/movie"
    params = {
        **base_params(),
        "query": query,
        "page": page,
        "include_adult": "false"
    }
    return await fetch(session, url, params)

async def send_movie_preview(bot: Bot, chat_id: int, movie: dict):
    movie_id = movie.get("id")
    title = movie.get("title", "Без названия")
    release = movie.get("release_date", "неизвестно")[:4]
    overview = movie.get("overview", "Описание отсутствует")
    poster_path = movie.get("poster_path")

    caption = f"<b>{title}</b> ({release})\n{overview[:300]}..."

    keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="⭐ В избранное", callback_data=f"fav_{movie_id}")
    ]])

    if poster_path:
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}"
        await bot.send_photo(chat_id, photo=poster_url, caption=caption, parse_mode="HTML", reply_markup=keyboard)
    else:
        await bot.send_message(chat_id, text=caption, parse_mode="HTML", reply_markup=keyboard)