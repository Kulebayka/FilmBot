from apscheduler.schedulers.asyncio import AsyncIOScheduler
from bot.api_tmdb import fetch_new_movies
from bot.config import TELEGRAM_API_TOKEN
from aiogram import Bot
from sqlalchemy import select
from bot.database.db import async_session
from bot.database.models import User

bot = Bot(token=TELEGRAM_API_TOKEN)
scheduler = AsyncIOScheduler()

async def send_new_movie_notifications():
    data = await fetch_new_movies()
    movies = data.get("results", [])[:3]
    if not movies:
        return

    message_texts = []
    for movie in movies:
        title = movie.get("title", "Без названия")
        release = movie.get("release_date", "неизвестно")
        overview = movie.get("overview", "Описание отсутствует")
        message_texts.append(f"<b>{title}</b> ({release})\n{overview[:300]}...\n")

    text = "\n\n".join(message_texts)

    async with async_session() as session:
        users = (await session.execute(select(User).filter_by(receive_notifications=True))).scalars().all()
        for user in users:
            try:
                await bot.send_message(user.telegram_id, f"🎬 Новые фильмы:\n\n{text}", parse_mode="HTML")
            except Exception as e:
                print(f"Ошибка отправки пользователю {user.telegram_id}: {e}")

def start():
    scheduler.add_job(send_new_movie_notifications, "interval", hours=24)
    scheduler.start()
