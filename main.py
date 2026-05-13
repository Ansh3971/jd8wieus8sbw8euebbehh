import os
import re
import json
import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse

from pydantic import BaseModel

from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.sessions import StringSession

from bs4 import BeautifulSoup

# =========================
# LOAD ENV
# =========================

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BOT_USERNAME = os.getenv("BOT_USERNAME")
DOWNLOAD_BUTTON = os.getenv("DOWNLOAD_BUTTON", "Download")

# =========================
# FASTAPI
# =========================

app = FastAPI()

# =========================
# TELEGRAM CLIENT
# =========================

client = TelegramClient(
    StringSession(SESSION),
    API_ID,
    API_HASH
)

# =========================
# DOWNLOAD FOLDER
# =========================

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# REQUEST MODEL
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

# =========================
# SHUTDOWN
# =========================

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
        <head><title>Universal HTML Parser API</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h2>Universal HTML Parser API</h2>

            <form action="/test" method="get">
                <input type="text" name="q" placeholder="Enter query"
                    style="width:300px;height:40px;padding:10px;">
                <button style="height:40px;">Search</button>
            </form>

        </body>
    </html>
    """

# =========================
# 🔥 CLEAN UNIVERSAL PARSER (FIXED VERSION)
# =========================

def parse_html_universal(html):

    soup = BeautifulSoup(html, "html.parser")

    def clean(t):
        return re.sub(r"\s+", " ", t).strip()

    result = {
        "title": clean(soup.title.get_text()) if soup.title else None,
        "meta": {},
        "links": [],
        "images": [],
        "tables": [],
        "forms": [],
        "lists": [],
        "blocks": []
    }

    # =====================
    # META (NO DUPLICATES)
    # =====================
    for m in soup.find_all("meta"):
        k = m.get("name") or m.get("property") or m.get("charset")
        v = m.get("content") or m.get("charset")

        if k and v and k not in result["meta"]:
            result["meta"][k] = v

    # =====================
    # LINKS (NO DUPLICATES)
    # =====================
    seen_links = set()

    for a in soup.find_all("a"):
        href = a.get("href")
        text = clean(a.get_text())

        key = (text, href)

        if href and key not in seen_links:
            seen_links.add(key)
            result["links"].append({
                "text": text,
                "href": href
            })

    # =====================
    # IMAGES (NO DUPLICATES)
    # =====================
    seen_img = set()

    for img in soup.find_all("img"):
        src = img.get("src")

        if src and src not in seen_img:
            seen_img.add(src)
            result["images"].append({
                "src": src,
                "alt": clean(img.get("alt") or "")
            })

    # =====================
    # TABLES
    # =====================
    for table in soup.find_all("table"):
        rows = []

        for tr in table.find_all("tr"):
            cols = [clean(c.get_text()) for c in tr.find_all(["td", "th"])]
            if cols:
                rows.append(cols)

        if rows:
            result["tables"].append(rows)

    # =====================
    # LISTS
    # =====================
    for ul in soup.find_all(["ul", "ol"]):
        items = []

        for li in ul.find_all("li"):
            t = clean(li.get_text())
            if t:
                items.append(t)

        if items:
            result["lists"].append(items)

    # =====================
    # BLOCKS (NO DUPLICATE + NO BIG PARAGRAPH DUMP)
    # =====================
    seen_blocks = set()

    for tag in soup.find_all(["div", "section", "article"]):

        text = clean(tag.get_text(" "))

        if not text or len(text) < 3:
            continue

        if text in seen_blocks:
            continue

        seen_blocks.add(text)

        lines = [
            clean(x)
            for x in re.split(r"[•\n\.]", text)
            if clean(x)
        ]

        result["blocks"].append({
            "tag": tag.name,
            "text": text[:300],
            "lines": lines[:20]
        })

    return result

# =========================
# SEARCH FUNCTION
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
            return {"status": False, "error": "No file"}

        file_path = await client.download_media(file_message, file=DOWNLOAD_DIR)

        file_name = os.path.basename(file_path)

        response = {
            "status": True,
            "query": data.message,
            "file_name": file_name,
            "size": os.path.getsize(file_path)
        }

        if file_name.endswith(".html"):

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()

            response["parsed"] = parse_html_universal(html_content)

        return response

    except Exception as e:
        return {"status": False, "error": str(e)}

# =========================
# TEST
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
