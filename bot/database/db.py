import os

from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker
from sqlalchemy.orm import declarative_base

# Загрузка переменных из .env
load_dotenv()

# Строка подключения
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найдена в .env файле.")

# Базовый класс для моделей
Base = declarative_base()

# Определение, будет ли логироваться SQL-запросы в зависимости от окружения
SQL_ECHO = os.getenv("SQL_ECHO", "False").lower() == "true"

# Создание движка
engine = create_async_engine(DATABASE_URL, echo=SQL_ECHO)

# Фабрика асинхронных сессий
async_session = async_sessionmaker(engine, expire_on_commit=False)

# Инициализация базы данных (создание таблиц)
async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)