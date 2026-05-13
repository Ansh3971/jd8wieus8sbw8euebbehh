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
# DOWNLOAD DIR
# =========================

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# REQUEST MODEL
# =========================

class Query(BaseModel):
    message: str

# =========================
# START / STOP
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
        <head><title>Parser API</title></head>
        <body style="font-family:Arial;padding:40px;">
            <h2>Universal HTML Parser API</h2>
            <form action="/test" method="get">
                <input name="q" placeholder="Enter query"
                    style="width:300px;height:40px;padding:10px;">
                <button type="submit">Search</button>
            </form>
        </body>
    </html>
    """

# =========================
# CLEAN HELPERS
# =========================

def clean_text(t):
    if not t:
        return ""
    return re.sub(r"\s+", " ", t).strip()

def unique_list(lst):
    seen = set()
    out = []
    for x in lst:
        x = clean_text(x)
        if x and x not in seen:
            seen.add(x)
            out.append(x)
    return out

# =========================
# 🔥 CLEAN HTML PARSER (FIXED)
# =========================

def parse_html_universal(html):
    soup = BeautifulSoup(html, "html.parser")

    result = {
        "title": clean_text(soup.title.get_text() if soup.title else ""),
        "navigation": [],
        "sections": [],
        "global_fields": {
            "emails": [],
            "phones": [],
            "addresses": [],
            "names": [],
            "documents": [],
            "regions": []
        }
    }

    # -------------------------
    # NAVIGATION
    # -------------------------
    for a in soup.select(".nav a"):
        result["navigation"].append({
            "id": a.get("href", "").replace("#", ""),
            "label": clean_text(a.get_text())
        })

    # -------------------------
    # SECTIONS
    # -------------------------
    for block in soup.select("div.block"):

        sec_id = block.get("id", "")
        heading = clean_text(block.select_one(".block-title").get_text() if block.select_one(".block-title") else "")

        section = {
            "id": sec_id,
            "heading": heading,
            "description": "",
            "content_blocks": []
        }

        text_tag = block.select_one(".block-text")

        if text_tag:

            full_text = clean_text(text_tag.get_text(" "))

            # TEXT BLOCK
            section["content_blocks"].append({
                "type": "text",
                "value": full_text
            })

            # FIELD GROUP (NO DUPLICATES FIXED)
            fields = {}

            for b in text_tag.find_all("b"):
                key = clean_text(b.get_text()).replace(":", "")
                if not key:
                    continue

                value = ""
                code = b.find_next("code")

                if code:
                    value = clean_text(code.get_text())
                elif b.next_sibling:
                    value = clean_text(str(b.next_sibling))

                if value:
                    fields.setdefault(key, set()).add(value)

            if fields:
                section["content_blocks"].append({
                    "type": "field_group",
                    "fields": {k: list(v) for k, v in fields.items()}
                })

            # GLOBAL EXTRACTION
            result["global_fields"]["phones"].extend(
                re.findall(r"\b\d{10,15}\b", full_text)
            )

            result["global_fields"]["emails"].extend(
                re.findall(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+", full_text)
            )

        result["sections"].append(section)

    # FINAL CLEANUP
    for k in result["global_fields"]:
        result["global_fields"][k] = unique_list(result["global_fields"][k])

    return result

# =========================
# SEARCH API
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
            await reply.click(0)

        file_message = None

        for _ in range(20):
            await asyncio.sleep(1)
            latest = await client.get_messages(BOT_USERNAME, limit=1)

            if latest and latest[0].file:
                file_message = latest[0]
                break

        if not file_message:
            return {"status": False, "error": "No file"}

        file_path = await client.download_media(
            file_message,
            file=DOWNLOAD_DIR
        )

        file_name = os.path.basename(file_path)

        response = {
            "status": True,
            "query": data.message,
            "file_name": file_name,
            "size": os.path.getsize(file_path)
        }

        if file_name.endswith(".html"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()

            response["parsed"] = parse_html_universal(html)

        return response

    except Exception as e:
        return {"status": False, "error": str(e)}

# =========================
# TEST ROUTE
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
