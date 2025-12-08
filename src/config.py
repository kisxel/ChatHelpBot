import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = "7977275797:AAGJee8s_tr4Vcl2zzh0ZB_aFyStpGfxpAo"
DB_NAME = "bot.db"

if not BOT_TOKEN:
    exit("Error: BOT_TOKEN not found in .env")
