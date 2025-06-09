from bot.database.models import User, Favorite
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from sqlalchemy.orm import selectinload
import logging

# Настройка логгера
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Уровень логирования (INFO, DEBUG, ERROR, и т.д.)

# Создание обработчика для записи логов в консоль
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)

# Формат логов
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
console_handler.setFormatter(formatter)

# Добавление обработчика к логгеру
logger.addHandler(console_handler)

MAX_FAVORITES = 10  # 🔢 Максимальное количество избранных фильмов

# Получить или создать пользователя с избранными фильмами
async def get_or_create_user_with_favorites(session: AsyncSession, telegram_id: int, username: Optional[str] = None) -> User:
    result = await session.execute(
        select(User)
        .filter_by(telegram_id=telegram_id)
        .options(selectinload(User.favorites))  # загружаем избранные фильмы
    )
    user = result.scalar_one_or_none()  # гарантирует, что будет только один результат, или None
    if not user:
        user = User(telegram_id=telegram_id, username=username)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user

# Добавить фильм в избранное (если ещё не добавлен и не превышен лимит)
async def add_favorite(session: AsyncSession, user: User, movie_data: dict) -> str:
    try:
        # Обновление информации о пользователе для актуальности данных
        await session.refresh(user, attribute_names=["favorites"])

        # Проверка на лимит
        if len(user.favorites) >= MAX_FAVORITES:
            return "Достигнут лимит избранных фильмов."

        # Проверка на существование фильма
        movie_exists = await session.scalar(select(Favorite).filter_by(
            user_id=user.id,
            movie_id=movie_data["id"]
        ))
        if movie_exists:
            return "Этот фильм уже в избранном."

        # Создание объекта фильма для добавления
        favorite = Favorite(
            user_id=user.id,
            movie_id=movie_data["id"],
            movie_title=movie_data["title"],
            movie_overview=movie_data.get("overview", ""),
            poster_url=movie_data.get("poster") or None  # Если нет poster, ставим None
        )

        # Добавление фильма в сессию
        session.add(favorite)
        await session.commit()

        return "Фильм успешно добавлен в избранное."

    except Exception as e:
        # Логируем ошибку
        logger.error(f"Ошибка при добавлении фильма {movie_data['title']} в избранное: {str(e)}")
        await session.rollback()  # Откат изменений в случае ошибки
        return "Ошибка при добавлении фильма в избранное. Повторите попытку."


# Удаление фильма из избранного
async def remove_favorite(session: AsyncSession, user: User, movie_id: int) -> bool:
    result = await session.execute(
        select(Favorite).filter_by(user_id=user.id, movie_id=movie_id)
    )
    favorite = result.scalar_one_or_none()

    if not favorite:
        return False  # Фильм не найден

    await session.delete(favorite)
    await session.commit()
    return True

# Получить список избранных фильмов пользователя
async def get_favorites(session: AsyncSession, user: User) -> list[Favorite]:
    await session.refresh(user, attribute_names=["favorites"])
    return user.favorites

async def get_user_by_id(session: AsyncSession, telegram_id: int):
    result = await session.execute(
        select(User).filter_by(telegram_id=telegram_id)
    )
    return result.scalar_one_or_none()