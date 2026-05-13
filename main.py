import os
import re
import asyncio

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.sessions import StringSession

# =========================
# ENV
# =========================

load_dotenv()

# Safe load with error if missing
APIID = os.getenv("APIID")
APIHASH = os.getenv("APIHASH")
SESSION = os.getenv("SESSION")
BOTUSERNAME = os.getenv("BOTUSERNAME")

if not APIID or not APIHASH or not SESSION or not BOTUSERNAME:
    raise RuntimeError("Missing one or more required environment variables: APIID, APIHASH, SESSION, BOTUSERNAME")

APIID = int(APIID)

# =========================
# APP
# =========================

app = FastAPI()

client = TelegramClient(
    StringSession(SESSION),
    APIID,
    APIHASH
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
# CLEAN
# =========================

def clean_text(t):
    return re.sub(r"\s+", " ", str(t)).strip() if t else ""

# =========================
# PAGINATION SCRAPER
# =========================

class TelegramPaginator:

    def __init__(self, client, bot, max_pages=20, delay=1.0):
        self.client = client
        self.bot = bot
        self.max_pages = max_pages
        self.delay = delay

    def is_next(self, text):
        if not text:
            return False
        t = text.lower()
        return ("➡" in t) or ("next" in t) or (t.strip() in [">", "»"])

    async def scrape(self, query):
        pages = []

        async with self.client.conversation(self.bot, timeout=120) as conv:
            await conv.send_message(query)

            for i in range(self.max_pages):
                try:
                    msg = await conv.get_response()
                except Exception as e:
                    print("No response:", e)
                    break

                text = msg.raw_text or ""
                print(f"DEBUG PAGE {i+1}:\n{text}\n")
                pages.append(text)

                clicked = False
                if msg.buttons:
                    print("DEBUG BUTTONS:", [[btn.text for btn in row] for row in msg.buttons])
                    for row in msg.buttons:
                        for btn in row:
                            if self.is_next(btn.text):
                                await btn.click()
                                clicked = True
                                break
                        if clicked:
                            break

                if not clicked:
                    break

                await asyncio.sleep(self.delay)

        return pages

# =========================
# RAW TEXT → JSON
# =========================

def parsebottext(text: str):
    lines = [clean_text(x) for x in text.split("\n") if clean_text(x)]

    records = []
    current = {}
    tel_count = 1
    addr_count = 1

    for line in lines:
        if ":" in line:
            key, val = line.split(":", 1)
            key = key.strip()
            val = val.strip()

            if key in current:
                if key.lower().startswith("telephone"):
                    key = f"Telephone_{tel_count}"
                    tel_count += 1
                elif key.lower().startswith("adres"):
                    key = f"Adres_{addr_count}"
                    addr_count += 1
                else:
                    key = key + "_dup"

            current[key] = val
        else:
            if current:
                records.append(current)
                current = {}
                tel_count = 1
                addr_count = 1

    if current:
        records.append(current)

    return {
        "total_records": len(records),
        "records": records
    }

# =========================
# API
# =========================

@app.post("/search")
async def search(data: Query):
    try:
        paginator = TelegramPaginator(client, BOTUSERNAME)
        pages = await paginator.scrape(data.message)

        if not pages:
            return {"status": False, "error": "No data"}

        full_text = "\n".join(pages)

        return {
            "status": True,
            "pages": len(pages),
            "parsed": parsebottext(full_text)
        }

    except Exception as e:
        return {"status": False, "error": str(e)}

# =========================
# TEST
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
