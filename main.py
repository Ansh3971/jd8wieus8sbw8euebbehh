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
# STARTUP
# =========================

@app.on_event("startup")
async def startup():
    await client.start()
    print("Telegram Client Started")

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
            <h2>Parser API</h2>
            <form action="/test" method="get">
                <input name="q" style="width:300px;height:40px">
                <button>Search</button>
            </form>
        </body>
    </html>
    """

# =========================
# CLEAN TEXT
# =========================

def clean_text(t):
    if not t:
        return ""
    return re.sub(r"\s+", " ", str(t)).strip()

# =========================
# PAGINATION SCRAPER (FIXED)
# =========================

class TelegramPaginator:

    def __init__(self, client, bot_username, max_pages=30, delay=1.5):
        self.client = client
        self.bot = bot_username
        self.max_pages = max_pages
        self.delay = delay

    async def start_msg(self):
        await asyncio.sleep(2)
        msgs = await self.client.get_messages(self.bot, limit=1)
        return msgs[0] if msgs else None

    def is_next(self, text):
        if not text:
            return False
        t = text.lower()
        return t in ["➡", ">", "next", "»"] or "next" in t

    async def scrape(self):

        msg = await self.start_msg()
        if not msg:
            return []

        pages = []
        seen_ids = set()

        for _ in range(self.max_pages):

            # ✅ FIX: correct access
            text = msg.message or ""

            if msg.id in seen_ids:
                break

            seen_ids.add(msg.id)
            pages.append(text)

            clicked = False

            try:
                if msg.buttons:
                    for row in msg.buttons:
                        for btn in row:
                            if self.is_next(btn.text):
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

            msgs = await self.client.get_messages(self.bot, ids=msg.id)
            if msgs:
                msg = msgs[0]
            else:
                break

        return pages

# =========================
# RAW TEXT → JSON (NO KEY MAP)
# =========================

def parse_bot_text(text: str):

    lines = [clean_text(x) for x in text.split("\n") if clean_text(x)]

    blocks = []
    current = None

    for line in lines:

        # new block detection (simple heuristic)
        if len(line) < 60 and ("📞" not in line) and (":" not in line):
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
        "count": len(blocks),
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
            return {"status": False, "error": "No data"}

        full_text = "\n".join(pages)

        return {
            "status": True,
            "pages": len(pages),
            "parsed": parse_bot_text(full_text)
        }

    except Exception as e:
        return {"status": False, "error": str(e)}

# =========================
# TEST
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
