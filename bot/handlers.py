from aiogram import Router, types, Bot, F
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, Message, CallbackQuery
from bot.api_tmdb import GENRES, fetch_movies_by_genre, fetch_top_movies, fetch_recommendations, fetch_new_movies, search_movies_by_keyword, send_movie_preview
from bot.database.db import async_session
from bot.database.models import User
from sqlalchemy import select
from aiohttp import ClientSession
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from time import time
from bot.config import TMDB_API_KEY
from bot.database.crud import get_or_create_user_with_favorites, add_favorite, get_favorites, remove_favorite, get_user_by_id
import aiohttp
import logging

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

user_cooldowns = {}
router = Router()
user_data = {}

class SearchState(StatesGroup):
    waiting_for_query = State()

def genre_keyboard():
    buttons = [KeyboardButton(text=genre) for genre in GENRES]
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[buttons[i:i + 2] for i in range(0, len(buttons), 2)])
    keyboard.keyboard.append([KeyboardButton(text="🔥 Топ-3"), KeyboardButton(text="🎯 Рекомендации"), KeyboardButton(text="🆕 Новинки")])
    keyboard.keyboard.append([KeyboardButton(text="⭐ Избранное")])
    return keyboard

def back_keyboard():
    return ReplyKeyboardMarkup(resize_keyboard=True, keyboard=[[KeyboardButton(text="🔙 Назад к выбору жанра")]])

def more_movies_keyboard(genre):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Посмотреть ещё 🎥", callback_data=f"more_{genre}")],
        [InlineKeyboardButton(text="🔙 Назад", callback_data="back")]
    ])

def notification_keyboard(enabled: bool) -> InlineKeyboardMarkup:
    text = "🔕 Отключить уведомления" if enabled else "🔔 Включить уведомления"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=text, callback_data="toggle_notifications")]
        ]
    )

# Обработка команды /start — приветствие пользователя и показ клавиатуры с жанрами
@router.message(Command("start"))
async def start(message: types.Message):
    user_data[message.chat.id] = {"genre": None, "page": 1}

    async with async_session() as session:
        result = await session.execute(
            select(User).filter_by(telegram_id=message.from_user.id)
        )
        db_user = result.scalar_one_or_none()

        if not db_user:
            new_user = User(
                telegram_id=message.from_user.id,
                username=message.from_user.username
            )
            session.add(new_user)
            await session.commit()

    await message.answer("Привет! Выбери жанр фильма 👇", reply_markup=genre_keyboard())

@router.message(Command("search"))
async def search_command(message: Message, state: FSMContext):
    await message.answer("🔎 Введите название фильма для поиска:")
    await state.set_state(SearchState.waiting_for_query)

@router.message(SearchState.waiting_for_query)
async def handle_search_query(message: Message, state: FSMContext):
    query = message.text.strip()
    await state.clear()  # очищаем предыдущее состояние

    if not query:
        await message.answer("Пожалуйста, введите корректное название фильма.")
        return

    await state.update_data(query=query)  # сохраняем поисковый запрос в FSM

    async with ClientSession() as session:
        data = await search_movies_by_keyword(session, query, page=1)

    if "error" in data:
        await message.answer("Произошла ошибка при поиске. Попробуйте позже.")
        return

    results = data.get("results", [])
    if not results:
        await message.answer(f"По запросу «{query}» ничего не найдено.")
        return

    for movie in results[:5]:
        await send_movie_preview(message.bot, message.chat.id, movie)

    more_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔎 Посмотреть ещё", callback_data="search_more|2")
    ]])
    await message.answer("Хочешь посмотреть ещё результаты?", reply_markup=more_keyboard)

@router.callback_query(F.data.startswith("search_more|"))
async def handle_search_more_callback(callback: CallbackQuery, state: FSMContext):
    try:
        _, raw_page = callback.data.split("|")
        page = int(raw_page)
    except ValueError as e:
        logger.error(f"Ошибка разбора callback_data: {callback.data} — {e}")
        await callback.message.answer("Некорректные данные запроса.")
        return

    user_data = await state.get_data()
    query = user_data.get("query")

    if not query:
        await callback.message.answer("Поисковый запрос не найден. Повторите поиск.")
        return

    try:
        async with ClientSession() as session:
            data = await search_movies_by_keyword(session, query, page=page)
    except Exception as e:
        logger.error(f"Ошибка при запросе фильмов: {e}")
        await callback.message.answer("Ошибка при получении фильмов. Попробуйте позже.")
        return

    results = data.get("results", [])
    if not results:
        await callback.message.answer("Больше фильмов не найдено.")
        return

    for movie in results[:5]:
        await send_movie_preview(callback.bot, callback.message.chat.id, movie)

    next_page = page + 1
    more_keyboard = InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="🔎 Посмотреть ещё", callback_data=f"search_more|{next_page}")
    ]])
    await callback.message.answer("Ещё результаты:", reply_markup=more_keyboard)


# Обработка нажатия кнопки "Назад к выбору жанра" — возврат к жанрам
@router.message(lambda msg: msg.text == "🔙 Назад к выбору жанра")
async def go_back(message: types.Message):
    user_data[message.chat.id] = {"genre": None, "page": 1}
    await message.answer("Выбери жанр снова 👇", reply_markup=genre_keyboard())

# Обработка выбора жанра или кнопок "Топ-3", "Рекомендации", "Новинки", "Избранное"
@router.message(lambda message: not (message.text and message.text.startswith('/')))
async def handle_genre_selection(message: types.Message, bot: Bot):
    genre_name = message.text
    if genre_name in GENRES:
        user_data[message.chat.id] = {"genre": genre_name, "page": 1}
        await send_movies(bot, message.chat.id, genre_name, 1)
    elif genre_name == "🔥 Топ-3":
        await send_top_movies(bot, message.chat.id)
    elif genre_name == "🎯 Рекомендации":
        await send_recommendations(bot, message.chat.id)
    elif genre_name == "🆕 Новинки":
        await send_new_movies(bot, message.chat.id)
    elif genre_name == "⭐ Избранное":
        await show_favorites(message)
    else:
        await message.answer("Выбери жанр из списка кнопок ⬇", reply_markup=genre_keyboard())

# Обработка callback-запроса "Назад" — возврат к выбору жанра
@router.callback_query(lambda call: call.data == "back")
async def back_to_genres(call: types.CallbackQuery):
    user_data[call.message.chat.id] = {"genre": None, "page": 1}
    await call.message.answer("Выбери жанр снова 👇", reply_markup=genre_keyboard())
    await call.answer()

# Обработка callback-запроса "Посмотреть ещё" — загрузка следующей страницы фильмов
@router.callback_query(lambda call: call.data.startswith("more_"))
async def more_movies(call: types.CallbackQuery, bot: Bot):
    genre_name = call.data.split("_", 1)[1]
    user_data[call.message.chat.id]["page"] += 1
    page = user_data[call.message.chat.id]["page"]
    await send_movies(bot, call.message.chat.id, genre_name, page)
    await call.message.edit_reply_markup(reply_markup=None) # Удаляем старую клавиатуру, чтобы не было старых кнопок
    await call.answer()

async def get_movie_details(movie_id: int):
    url = f'https://api.themoviedb.org/3/movie/{movie_id}'
    params = {
        'api_key': TMDB_API_KEY,
        'language': 'ru'
    }

    async with aiohttp.ClientSession() as session:
        async with session.get(url, params=params) as response:
            data = await response.json()
            return data

@router.callback_query(lambda call: call.data.startswith("remove_fav_"))
async def remove_from_favorites(call: types.CallbackQuery, bot: Bot):
    movie_id = int(call.data.split("_")[2])
    chat_id = call.message.chat.id

    async with async_session() as session:
        user = await get_or_create_user_with_favorites(session, chat_id, "")
        favorites = await get_favorites(session, user)

        # Находим фильм в избранном
        favorite_movie = next((f for f in favorites if f.movie_id == movie_id), None)

        if favorite_movie:
            # Удаляем фильм из избранного
            session.delete(favorite_movie)
            await session.commit()
            await call.message.answer(f"✅ Фильм '{favorite_movie.movie_title}' удален из избранного.")
            # Отправляем обновленный список избранных
            await send_favorites(bot, chat_id)
        else:
            await call.message.answer("⚠️ Этот фильм не найден в вашем списке избранных.")

    await call.answer()

@router.callback_query(lambda call: call.data.startswith("del_"))
async def delete_from_favorites(call: types.CallbackQuery):
    movie_id = int(call.data.split("_")[1])
    chat_id = call.message.chat.id

    async with async_session() as session:
        user = await get_or_create_user_with_favorites(session, chat_id, call.from_user.username)
        success = await remove_favorite(session, user, movie_id)

    if success:
        await call.message.delete()  # Удалить сообщение с фильмом
        await call.answer("🗑 Фильм удалён из избранного.")
    else:
        await call.answer("⚠️ Не удалось удалить фильм.")

# Отправка фильмов по выбранному жанру
async def send_movies(bot, chat_id, genre_name, page):
    async with ClientSession() as session:
        data = await fetch_movies_by_genre(session, genre_name, page)

    results = data.get("results")
    if not results:
        await bot.send_message(chat_id, "Фильмы не найдены 😔")
        return

    last_movie_id = None
    for movie in results[:3]:
        title = movie.get("title", "Без названия")
        release = movie.get("release_date", "неизвестно")[:4]
        desc = movie.get("overview", "Описание отсутствует.")
        text = f"🎬 *{title} ({release})*\n\n{desc}"

        poster_path = movie.get("poster_path")
        poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
        poster_data = poster_path or "no_image"

        inline_button = InlineKeyboardButton(
            text="⭐ В избранное",
            callback_data=f"fav_{movie['id']}_{poster_data}"
        )
        inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[inline_button]])

        if poster_url:
            await bot.send_photo(chat_id, poster_url, caption=text, parse_mode="Markdown", reply_markup=inline_keyboard)
        else:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=inline_keyboard)

        last_movie_id = movie["id"]

    if last_movie_id:
        await bot.send_message(
            chat_id,
            "Не понравилось? Посмотри ещё фильмы 👇",
            reply_markup=more_movies_keyboard(genre_name)
        )

@router.callback_query(F.data.startswith("more_"))
async def show_more_movies(callback: CallbackQuery, bot: Bot):
    user_id = callback.from_user.id
    now = time()
    cooldown_seconds = 15

    last_time = user_cooldowns.get(user_id, 0)
    if now - last_time < cooldown_seconds:
        await callback.answer("Подождите немного перед следующим запросом.", show_alert=False)
        return

    user_cooldowns[user_id] = now

    genre_name = callback.data.split("_", 1)[1]
    user_data[user_id]["page"] += 1  # Увеличиваем страницу
    page = user_data[user_id]["page"]

    await send_movies(bot, callback.message.chat.id, genre_name, page)
    await callback.answer()

# Отправка новых фильмов
async def send_new_movies(bot: Bot, chat_id: int):
    async with ClientSession() as session:
        data = await fetch_new_movies(session)
        results = data.get("results")
        if not results:
            await bot.send_message(chat_id, "Новинки не найдены 😔", reply_markup=genre_keyboard())
            return

        for movie in data["results"][:5]:  # Показываем, первые 5 новинок
            title = movie.get("title", "Без названия")
            release = movie.get("release_date", "неизвестно")[:4]
            overview = movie.get("overview", "Описание отсутствует.")
            poster_path = movie.get("poster_path")
            poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None

            caption = f"🎬 *{title} ({release})*\n\n{overview}"

            inline_button = InlineKeyboardButton(
                text="⭐ В избранное",
                callback_data=f"fav_{movie['id']}_{poster_path or 'no_image'}"
            )
            inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[inline_button]])

            if poster_url:
                await bot.send_photo(
                    chat_id, poster_url, caption=caption,
                    parse_mode="Markdown", reply_markup=inline_keyboard
                )
            else:
                await bot.send_message(
                    chat_id, caption, parse_mode="Markdown",
                    reply_markup=inline_keyboard
                )

        await bot.send_message(chat_id, "Это новинки кино! 🆕", reply_markup=genre_keyboard())

# Отправка топ-3 фильмов
async def send_top_movies(bot, chat_id):
    async with ClientSession() as session:
        data = await fetch_top_movies(session)
        results = data.get("results")
        if not results:
            await bot.send_message(chat_id, "Фильмы не найдены 😔")
            return

        for movie in data["results"][:3]:
            title = movie.get("title", "Без названия")
            release = movie.get("release_date", "неизвестно")[:4]
            desc = movie.get("overview", "Описание отсутствует.")
            text = f"🎬 *{title} ({release})*\n\n{desc}"

            # Постер и кнопка
            poster_path = movie.get("poster_path", "")
            poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            inline_button = InlineKeyboardButton(
                text="⭐ В избранное",
                callback_data=f"fav_{movie['id']}_{poster_path or 'no_image'}"
            )
            inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[inline_button]])

            if poster:
                await bot.send_photo(chat_id, poster, caption=text, parse_mode="Markdown", reply_markup=inline_keyboard)
            else:
                await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=inline_keyboard)

        await bot.send_message(chat_id, "Это топ-3 фильмов! 🔥", reply_markup=back_keyboard())

# Отправка рекомендованных фильмов
async def send_recommendations(bot, chat_id):
    async with ClientSession() as session:
        data = await fetch_recommendations(session)
        results = data.get("results")
        if not results:
            await bot.send_message(chat_id, "Фильмы не найдены 😔")
            return

        for movie in data["results"][:3]:
            title = movie.get("title", "Без названия")
            release = movie.get("release_date", "неизвестно")[:4]
            desc = movie.get("overview", "Описание отсутствует.")
            text = f"🎬 *{title} ({release})*\n\n{desc}"

            poster_path = movie.get("poster_path", "")
            poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
            inline_button = InlineKeyboardButton(
                text="⭐ В избранное",
                callback_data=f"fav_{movie['id']}_{poster_path or 'no_image'}"
            )
            inline_keyboard = InlineKeyboardMarkup(inline_keyboard=[[inline_button]])

            if poster:
                await bot.send_photo(chat_id, poster, caption=text, parse_mode="Markdown", reply_markup=inline_keyboard)
            else:
                await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=inline_keyboard)

        await bot.send_message(chat_id, "Попробуй эти фильмы! 🎯", reply_markup=back_keyboard())

@router.callback_query(lambda call: call.data == "more_recommendations")
async def more_recommendations(call: types.CallbackQuery, bot: Bot):
    user_data[call.message.chat.id]["recommendations_page"] = user_data[call.message.chat.id].get(
        "recommendations_page", 1) + 1

    await send_recommendations(bot, call.message.chat.id)
    await call.answer()

# Отправка избранных фильмов — как обычных фильмов по жанру, с кнопкой удаления
async def send_favorites(bot, chat_id):
    async with async_session() as session:
        user = await get_or_create_user_with_favorites(session, chat_id, "")
        favorites = await get_favorites(session, user)

    if not favorites:
        await bot.send_message(chat_id, "У вас нет избранных фильмов 😔")
        return

    for favorite in favorites:
        title = favorite.movie_title
        desc = favorite.movie_overview or "Описание отсутствует."
        poster = favorite.poster_url
        text = f"🎬 *{title}*\n\n{desc}"

        # Кнопка "Удалить из избранного"
        keyboard = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🗑 Удалить из избранного", callback_data=f"del_{favorite.movie_id}")]
        ])

        if poster:
            await bot.send_photo(chat_id, photo=poster, caption=text, parse_mode="Markdown", reply_markup=keyboard)
        else:
            await bot.send_message(chat_id, text, parse_mode="Markdown", reply_markup=keyboard)

    await bot.send_message(chat_id, "Это ваш список избранных фильмов! ⭐", reply_markup=back_keyboard())

# Функция для отображения избранных фильмов
async def show_favorites(message: types.Message):
    async with async_session() as session:
        user = await get_or_create_user_with_favorites(session, message.chat.id, message.from_user.username)
        favorites = await get_favorites(session, user)

    if not favorites:
        await message.answer("У вас нет избранных фильмов 😔", reply_markup=back_keyboard())
        return

    for favorite in favorites:
        title = favorite.movie_title
        desc = favorite.movie_overview or "Описание отсутствует."
        poster = favorite.poster_url
        text = f"*{title}*\n\n{desc}"
        logger.info(f"[show_favorites] Poster URL для фильма {title}: {poster}")

        keyboard = InlineKeyboardMarkup(inline_keyboard=[[
            InlineKeyboardButton(text="🗑 Удалить из избранного", callback_data=f"del_{favorite.movie_id}")
        ]])

        try:
            if poster:
                await message.bot.send_photo(
                    chat_id=message.chat.id,
                    photo=poster,
                    caption=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
            else:
                await message.bot.send_message(
                    chat_id=message.chat.id,
                    text=text,
                    parse_mode="Markdown",
                    reply_markup=keyboard
                )
        except Exception as e:
            logger.error(f"Ошибка при отправке фильма {title}: {str(e)}")

    await message.answer("Это ваш список избранных фильмов! ⭐", reply_markup=back_keyboard())

@router.callback_query(lambda c: c.data.startswith("fav_"))
async def add_to_favorites(call: types.CallbackQuery):
    parts = call.data.split("_", 2)
    movie_id = int(parts[1])
    poster_path = parts[2] if len(parts) > 2 and parts[2] != 'no_image' else None

    chat_id = call.message.chat.id
    username = call.from_user.username

    message = call.message
    text = message.caption or message.text
    title = text.split("\n")[0].replace("🎬 *", "").replace("*", "")
    overview = "\n".join(text.split("\n")[1:]).strip()

    poster_url = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else None
    logger.info(f"[add_to_favorites] Poster URL для фильма {title}: {poster_url}")

    async with async_session() as session:
        user = await get_or_create_user_with_favorites(session, chat_id, username)
        movie_data = {
            "id": movie_id,
            "title": title,
            "overview": overview,
            "poster": poster_url
        }

        favorites = await get_favorites(session, user)

        if any(f.movie_id == movie_id for f in favorites):
            await call.message.answer("⚠️ Этот фильм уже в вашем списке избранного.")
        elif len(favorites) >= 10:
            await call.message.answer("❗ Вы достигли лимита в 10 избранных фильмов.")
        else:
            success = await add_favorite(session, user, movie_data)
            if success:
                await call.message.answer("✅ Фильм добавлен в избранное ⭐")
            else:
                await call.message.answer("⚠️ Не удалось добавить фильм. Повторите попытку.")
    await call.answer()

@router.message(Command("notifications"))
async def show_notifications_setting(message: Message):
    async with async_session() as session:
        user = await get_user_by_id(session, message.from_user.id)
        if not user:
            await message.answer("Сначала начни диалог с ботом командой /start.")
            return

        status_text = "🔔 Уведомления включены." if user.receive_notifications else "🔕 Уведомления отключены."
        kb = notification_keyboard(user.receive_notifications)

        await message.answer(f"{status_text}\nВы можете изменить настройки:", reply_markup=kb)

@router.callback_query(F.data == "toggle_notifications")
async def handle_toggle_notifications_callback(callback: CallbackQuery):
    async with async_session() as session:
        result = await session.execute(
            select(User).filter_by(telegram_id=callback.from_user.id)
        )
        user = result.scalar_one_or_none()

        if not user:
            await callback.answer("Сначала начни с команды /start.")
            return

        user.receive_notifications = not user.receive_notifications
        await session.commit()

        text = "🔔 Уведомления включены." if user.receive_notifications else "🔕 Уведомления отключены."
        new_kb = notification_keyboard(user.receive_notifications)

        await callback.message.edit_reply_markup(reply_markup=new_kb)
        await callback.answer(text)