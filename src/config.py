import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DB_NAME = "bot.db"

if not BOT_TOKEN:
    exit("Error: BOT_TOKEN not found in .env")
