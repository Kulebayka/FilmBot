from aiogram import Bot
from aiogram.types import BotCommand

async def set_commands(bot: Bot):
    commands = [
        BotCommand(command="start", description="Начать работу с ботом"),
        BotCommand(command="search", description="Поиск фильма по ключевому слову"),
        BotCommand(command="notifications", description="Настройки уведомлений"),
    ]
    await bot.set_my_commands(commands)