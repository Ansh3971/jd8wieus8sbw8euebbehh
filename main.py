import os
import re
import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession

# =========================
# ENV
# =========================

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BOT_USERNAME = os.getenv("BOT_USERNAME")

# =========================
# APP
# =========================

app = FastAPI()

client = TelegramClient(
    StringSession(SESSION),
    API_ID,
    API_HASH
)

# =========================
# MODEL
# =========================

class Query(BaseModel):
    message: str

# =========================
# START / STOP
# =========================

@app.on_event("startup")
async def startup():
    await client.start()
    print("✅ Telegram Client Started")

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()

# =========================
# HOME
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body style="font-family:Arial;padding:30px;">
            <h2>PRO Scraper API</h2>
            <form action="/test" method="get">
                <input name="q" style="width:300px;height:40px">
                <button>Search</button>
            </form>
        </body>
    </html>
    """

# =========================
# CLEAN
# =========================

def clean_text(t):
    if not t:
        return ""
    return re.sub(r"\s+", " ", str(t)).strip()

# =========================
# PRO PAGINATION SCRAPER
# =========================

class TelegramPaginator:

    def __init__(self, client, bot_username, max_pages=20, delay=1.2):
        self.client = client
        self.bot = bot_username
        self.max_pages = max_pages
        self.delay = delay

    async def get_latest_message(self):
        msgs = await self.client.get_messages(self.bot, limit=1)
        return msgs[0] if msgs else None

    def is_next_button(self, text):
        if not text:
            return False
        t = text.lower()
        return t in ["➡", ">", "next", "»", "forward"] or "next" in t

    async def scrape(self):

        msg = await self.get_latest_message()
        if not msg:
            return []

        pages = []
        seen_ids = set()

        for _ in range(self.max_pages):

            text = msg.message or ""

            # prevent duplicate pages
            if msg.id in seen_ids:
                break

            seen_ids.add(msg.id)
            pages.append(text)

            clicked = False

            # =========================
            # BUTTON CLICK HANDLING
            # =========================
            try:
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if self.is_next_button(btn.text):
                                await btn.click()
                                clicked = True
                                break
                        if clicked:
                            break
            except Exception as e:
                print("Button error:", e)
                break

            if not clicked:
                break

            await asyncio.sleep(self.delay)

            # =========================
            # SAFE MESSAGE REFRESH
            # (IMPORTANT FIX)
            # =========================
            new_msg = await self.client.get_messages(self.bot, limit=1)
            if not new_msg:
                break

            msg = new_msg[0]

        return pages

# =========================
# RAW TEXT → JSON
# =========================

def parse_bot_text(text: str):

    lines = [clean_text(x) for x in text.split("\n") if clean_text(x)]

    blocks = []
    current = None

    for line in lines:

        # heading detection
        if len(line) < 60 and "📞" not in line and ":" not in line:
            current = {
                "heading": line,
                "content": []
            }
            blocks.append(current)
            continue

        if current is None:
            current = {
                "heading": "UNKNOWN",
                "content": []
            }
            blocks.append(current)

        current["content"].append(line)

    return {
        "total_blocks": len(blocks),
        "blocks": blocks
    }

# =========================
# API
# =========================

@app.post("/search")
async def search(data: Query):

    try:
        await client.send_message(BOT_USERNAME, data.message)

        paginator = TelegramPaginator(client, BOT_USERNAME)

        pages = await paginator.scrape()

        if not pages:
            return {
                "status": False,
                "error": "No data received"
            }

        full_text = "\n".join(pages)

        return {
            "status": True,
            "pages": len(pages),
            "parsed": parse_bot_text(full_text)
        }

    except Exception as e:
        return {
            "status": False,
            "error": str(e)
        }

# =========================
# TEST
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
