from aiogram import Router, types
from aiogram.filters import Command

router = Router()

@router.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer(
        "Привет! Я бот-модератор.\n"
        "Я слежу за порядком в чате и удаляю плохие слова."
    )
