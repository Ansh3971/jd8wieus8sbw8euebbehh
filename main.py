import os
import re
import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.sessions import StringSession

from bs4 import BeautifulSoup

# =========================
# ENV
# =========================

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BOT_USERNAME = os.getenv("BOT_USERNAME")
DOWNLOAD_BUTTON = os.getenv("DOWNLOAD_BUTTON", "Download")

# =========================
# APP
# =========================

app = FastAPI()

client = TelegramClient(
    StringSession(SESSION),
    API_ID,
    API_HASH
)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

class Query(BaseModel):
    message: str

# =========================
# STARTUP / SHUTDOWN
# =========================

@app.on_event("startup")
async def startup():
    await client.start()
    print("Telegram Client Started")

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()

# =========================
# HOME PAGE
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body style="font-family:Arial;padding:40px;">
            <h2>HTML Parser API</h2>
            <form action="/test" method="get">
                <input name="q" style="width:300px;height:40px;" placeholder="Enter query">
                <button>Search</button>
            </form>
        </body>
    </html>
    """

# =========================
# CLEAN HTML PARSER (NO DUPLICATION FIX)
# =========================

def parse_html_ai(html):
    soup = BeautifulSoup(html, "html.parser")

    def clean(text):
        return re.sub(r"\s+", " ", text).strip()

    result = {
        "title": clean(soup.title.get_text()) if soup.title else None,
        "meta": {},
        "sections": []
    }

    # ================= META =================
    for meta in soup.find_all("meta"):
        key = meta.get("name") or meta.get("property") or meta.get("charset")
        val = meta.get("content") or meta.get("charset")
        if key and val:
            result["meta"][key] = val

    # ================= FIXED BLOCK EXTRACTION =================
    seen = set()

    blocks = soup.body.find_all(["div", "section", "article"], recursive=False) if soup.body else []

    # fallback if body empty
    if not blocks:
        blocks = soup.find_all(["div", "section", "article"], recursive=False)

    for block in blocks:

        text = clean(block.get_text(" "))

        if not text or len(text) < 3:
            continue

        key = (text[:120], block.get("id"))

        if key in seen:
            continue

        seen.add(key)

        item = {
            "tag": block.name,
            "text": text,
            "attributes": {
                "id": block.get("id"),
                "class": block.get("class")
            }
        }

        # ================= LINKS INSIDE BLOCK =================
        links = []

        for a in block.find_all("a"):
            href = a.get("href")
            link_text = clean(a.get_text())

            if href and link_text:
                links.append({
                    "text": link_text,
                    "href": href
                })

        if links:
            item["links"] = links

        result["sections"].append(item)

    return result

# =========================
# TELEGRAM SEARCH FLOW
# =========================

@app.post("/search")
async def search(data: Query):

    try:
        await client.send_message(BOT_USERNAME, data.message)

        await asyncio.sleep(3)

        messages = await client.get_messages(BOT_USERNAME, limit=1)

        if not messages:
            return {"status": False, "error": "No response"}

        reply = messages[0]

        try:
            await reply.click(text=DOWNLOAD_BUTTON)
        except:
            try:
                await reply.click(0)
            except Exception as e:
                return {"status": False, "error": str(e)}

        file_message = None

        for _ in range(20):
            await asyncio.sleep(1)
            latest = await client.get_messages(BOT_USERNAME, limit=1)

            if latest and latest[0].file:
                file_message = latest[0]
                break

        if not file_message:
            return {"status": False, "error": "No file received"}

        file_path = await client.download_media(
            file_message,
            file=DOWNLOAD_DIR
        )

        file_name = os.path.basename(file_path)

        response = {
            "status": True,
            "query": data.message,
            "file_name": file_name
        }

        # ================= HTML PARSE =================
        if file_name.endswith(".html"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()

            response["parsed"] = parse_html_ai(html)

        return response

    except Exception as e:
        return {"status": False, "error": str(e)}

# =========================
# TEST ROUTE
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
