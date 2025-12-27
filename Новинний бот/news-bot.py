import os
import feedparser
import sqlite3
import hashlib
import asyncio
import threading
from aiogram import Bot, Dispatcher, types
from aiogram.utils import executor
from flask import Flask
from threading import Thread

# ---------------- Flask для UptimeRobot ----------------
app = Flask('')

@app.route('/')
def home():
    return "I'm alive!"

def run_flask():
    app.run(host='0.0.0.0', port=8080)

def keep_alive():
    t = Thread(target=run_flask)
    t.start()

keep_alive()

# ---------------- Telegram Bot ----------------
BOT_TOKEN = os.getenv("BOT_TOKEN")
OWNER_ID = int(os.getenv("OWNER_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# ---------------- SQLite ----------------
DB = sqlite3.connect("news.db", check_same_thread=False)
CURSOR = DB.cursor()
DB_LOCK = threading.Lock()

CURSOR.execute("""
CREATE TABLE IF NOT EXISTS news (
    hash TEXT PRIMARY KEY
)
""")
CURSOR.execute("""
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT
)
""")
DB.commit()

# ---------------- Функції для налаштувань ----------------
def get_setting(key, default="on"):
    with DB_LOCK:
        CURSOR.execute("SELECT value FROM settings WHERE key=?", (key,))
        row = CURSOR.fetchone()
        if row:
            return row[0]
        CURSOR.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (key, default))
        DB.commit()
        return default

def set_setting(key, value):
    with DB_LOCK:
        CURSOR.execute("REPLACE INTO settings VALUES (?,?)", (key, value))
        DB.commit()

# ---------------- RSS та аналіз ----------------
RSS_FEEDS = [
    "https://www.pravda.com.ua/rss/",
    "https://ain.ua/feed/",
    "https://mon.gov.ua/ua/news/rss"
]

CATEGORIES = {
    "Технології": ["ai", "штучний інтелект", "технолог", "software"],
    "Освіта в Україні": ["освіта", "школ", "університет", "мон"],
    "Бюджети на освіту": ["бюджет", "фінансування", "субвенц"],
    "Комп'ютери": ["комп'ютер", "ноутбук", "сервер"],
    "Інвертори та енергетика": ["інвертор", "резервне живлення", "акумулятор"]
}

def detect_category(text):
    t = text.lower()
    for cat, keys in CATEGORIES.items():
        if any(k in t for k in keys):
            return cat
    return None

def seo_score(text):
    score = 0
    seo_keys = ["ринок", "попит", "державн", "програма", "тендер", "бюджет"]
    for k in seo_keys:
        if k in text.lower():
            score += 1
    if score >= 3:
        return "ВИСОКИЙ"
    if score == 2:
        return "СЕРЕДНІЙ"
    return "НИЗЬКИЙ"

def is_new(text):
    h = hashlib.md5(text.encode()).hexdigest()
    with DB_LOCK:
        CURSOR.execute("SELECT 1 FROM news WHERE hash=?", (h,))
        if CURSOR.fetchone():
            return False
        CURSOR.execute("INSERT OR IGNORE INTO news VALUES (?)", (h,))
        DB.commit()
        return True

def analysis_block(category, seo):
    return f"""📌 Чому це важливо:
– вплив на напрям «{category}»
– потенційні наслідки для України

📊 SEO-потенціал: **{seo}**

✍️ Ідея для статті:
– аналітичний матеріал + практичні висновки
– фокус на український контекст"""

# ---------------- Telegram команди ----------------
@dp.message_handler(commands=["ping"])
async def ping(msg: types.Message):
    if msg.from_user.id == OWNER_ID:
        await msg.answer("✅ Бот працює")

@dp.message_handler(commands=["pause"])
async def pause(msg: types.Message):
    if msg.from_user.id != OWNER_ID:
        return
    current = get_setting("paused")
    new = "off" if current == "on" else "on"
    set_setting("paused", new)
    await msg.answer(f"🔕 Сповіщення: {'ВИМКНЕНО' if new=='off' else 'УВІМКНЕНО'}")

# ---------------- Перевірка новин ----------------
async def check_news():
    if get_setting("paused") == "off":
        return
    for feed_url in RSS_FEEDS:
        feed = feedparser.parse(feed_url)
        for e in feed.entries[:5]:
            text = f"{e.title} {e.get('summary','')}"
            category = detect_category(text)
            if category and is_new(text):
                seo = seo_score(text)
                msg = f"""🟦 Категорія: {category}

🔹 {e.title}

{e.get('summary','')[:350]}

{analysis_block(category, seo)}

🔗 Джерело: {e.link}
"""
                await bot.send_message(OWNER_ID, msg)

async def scheduler():
    while True:
        try:
            await check_news()
        except Exception as e:
            await bot.send_message(OWNER_ID, f"⚠️ Помилка: {e}")
        await asyncio.sleep(300)

# ---------------- Запуск ----------------
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(scheduler())
    executor.start_polling(dp, skip_updates=True)




