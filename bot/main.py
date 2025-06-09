import logging
import asyncio
from aiogram import Bot, Dispatcher
from bot.commands import set_commands
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.client.bot import DefaultBotProperties
from bot.config import TELEGRAM_API_TOKEN
from bot.handlers import router
from bot.database import init_db

# Конфигурация логирования
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

logger = logging.getLogger(__name__)

# Параметры бота
bot_properties = DefaultBotProperties(parse_mode="HTML")

# Создание бота и диспетчера
def create_bot_and_dispatcher() -> tuple[Bot, Dispatcher]:
    bot = Bot(token=TELEGRAM_API_TOKEN, default=bot_properties)
    dp = Dispatcher(storage=MemoryStorage())
    dp.include_router(router)
    return bot, dp

# Основная точка входа
async def main():
    bot, dp = create_bot_and_dispatcher()
    try:
        logger.info("🔧 Инициализация базы данных...")
        await init_db()

        logger.info("🚀 Запуск бота...")
        await bot.delete_webhook(drop_pending_updates=True)
        await set_commands(bot)

        print("✅ Бот успешно запущен и готов к работе.")
        await dp.start_polling(bot)

    except Exception as e:
        logger.exception("❌ Не удалось запустить бота: %s", e)

    finally:
        logger.info("🔒 Завершение сессии бота.")
        await dp.storage.close()
        if hasattr(dp.storage, "wait_closed"):
            await dp.storage.wait_closed()
        await bot.session.close()
        logger.info("✅ Бот успешно завершил работу.")

# Точка запуска
if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Остановка по запросу пользователя.")
