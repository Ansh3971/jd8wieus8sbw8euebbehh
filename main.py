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
from collections import defaultdict

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
# HOME
# =========================
@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body style="font-family:Arial;padding:40px;">
            <h2>Universal HTML Parser API</h2>
            <form action="/test" method="get">
                <input name="q" style="width:300px;height:40px" placeholder="Enter query">
                <button>Search</button>
            </form>
        </body>
    </html>
    """


# =========================
# CLEAN HELPER
# =========================
def clean_text(text):
    if not text:
        return ""
    text = re.sub(r"\s+", " ", text)
    return text.strip()


# =========================
# UNIVERSAL CLEAN PARSER (FIXED)
# =========================
def parse_html_universal(html):

    soup = BeautifulSoup(html, "html.parser")

    result = {
        "title": "",
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

    seen_texts = set()

    # TITLE
    if soup.title:
        result["title"] = clean_text(soup.title.get_text())

    # NAVIGATION
    nav = soup.find("div", class_="nav")
    if nav:
        for a in nav.find_all("a"):
            result["navigation"].append({
                "id": a.get("href", "").replace("#", ""),
                "label": clean_text(a.get_text())
            })

    # SECTIONS
    blocks = soup.find_all("div", class_="block")

    for block in blocks:

        section = {
            "id": block.get("id", ""),
            "heading": "",
            "description": "",
            "content_blocks": []
        }

        # heading
        h = block.find(class_="block-title")
        if h:
            section["heading"] = clean_text(h.get_text())

        # text block
        text_block = block.find(class_="block-text")

        if text_block:

            raw = clean_text(text_block.get_text(" "))

            if raw and raw not in seen_texts:
                seen_texts.add(raw)

                section["content_blocks"].append({
                    "type": "text",
                    "value": raw
                })

        # field extraction
        fields = defaultdict(list)

        if text_block:

            for b in text_block.find_all("b"):

                key = clean_text(b.get_text().replace(":", ""))

                value = ""

                code = b.find_next("code")
                if code:
                    value = clean_text(code.get_text())
                else:
                    nxt = b.next_sibling
                    if nxt:
                        value = clean_text(str(nxt))

                if key and value:

                    fields[key].append(value)

                    low = key.lower()

                    if "email" in low:
                        result["global_fields"]["emails"].append(value)

                    elif "telephone" in low or "phone" in low:
                        result["global_fields"]["phones"].append(value)

                    elif "adres" in low or "address" in low:
                        result["global_fields"]["addresses"].append(value)

                    elif "name" in low:
                        result["global_fields"]["names"].append(value)

                    elif "document" in low or "passport" in low:
                        result["global_fields"]["documents"].append(value)

                    elif "region" in low:
                        result["global_fields"]["regions"].append(value)

        if fields:
            section["content_blocks"].append({
                "type": "field_group",
                "fields": dict(fields)
            })

        result["sections"].append(section)

    # GLOBAL DEDUPE
    for k in result["global_fields"]:
        result["global_fields"][k] = list(set(result["global_fields"][k]))

    return result


# =========================
# SEARCH ROUTE (TELETHON FLOW)
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

        # HTML PARSE
        if file_name.endswith(".html"):

            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()

            response["parsed"] = parse_html_universal(html_content)

        return response

    except Exception as e:
        return {"status": False, "error": str(e)}


# =========================
# TEST ROUTE
# =========================
@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
