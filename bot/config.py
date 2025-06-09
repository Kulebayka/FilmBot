from dotenv import load_dotenv
import os

# Загрузка переменных окружения из файла .env
load_dotenv()

# Функция безопасного получения переменных окружения
def get_env_variable(key: str, default: str = None, required: bool = True) -> str:
    value = os.getenv(key, default)
    if required and value is None:
        raise EnvironmentError(f"Обязательная переменная окружения '{key}' не найдена.")
    return value

# Получение значений токенов и ключей
TELEGRAM_API_TOKEN = get_env_variable("TELEGRAM_API_TOKEN")
TMDB_API_KEY = get_env_variable("TMDB_API_KEY")
DATABASE_URL = get_env_variable("DATABASE_URL")