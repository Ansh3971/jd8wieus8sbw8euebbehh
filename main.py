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
# CLEAN TEXT SPLITTER
# =========================

def clean(text):
    return re.sub(r"\s+", " ", text).strip()

def split_text(text):
    """
    Convert long paragraph into structured chunks
    """
    text = clean(text)

    if len(text) < 80:
        return [text] if text else []

    # split by sentence boundaries
    parts = re.split(r"(?<=[.!?])\s+", text)

    return [clean(p) for p in parts if len(p.strip()) > 2]

# =========================
# NEW JSON NODE PARSER
# =========================

def parse_node(element):

    if not hasattr(element, "name"):
        return None

    node = {
        "tag": element.name,
        "attributes": {
            "id": element.get("id"),
            "class": element.get("class"),
            "href": element.get("href"),
            "src": element.get("src")
        },
        "content": [],
        "children": []
    }

    # ================= TEXT AS CLEAN CHUNKS =================
    raw_text = element.get_text(" ", strip=True)
    chunks = split_text(raw_text)

    if chunks:
        node["content"] = chunks

    # ================= CHILDREN =================
    seen = set()

    for child in element.children:

        if not hasattr(child, "name"):
            continue

        key = (child.name, child.get("id"))

        if key in seen:
            continue

        seen.add(key)

        child_node = parse_node(child)

        if child_node:
            node["children"].append(child_node)

    # remove empty noise
    if not node["content"]:
        node.pop("content")

    if not node["children"]:
        node.pop("children")

    return node

# =========================
# MAIN PARSER WRAPPER
# =========================

def parse_html_ai(html):

    soup = BeautifulSoup(html, "html.parser")

    result = {
        "title": clean(soup.title.get_text()) if soup.title else None,
        "meta": {},
        "structure": []
    }

    # META
    for meta in soup.find_all("meta"):
        key = meta.get("name") or meta.get("property") or meta.get("charset")
        val = meta.get("content") or meta.get("charset")

        if key and val:
            result["meta"][key] = val

    root = soup.body if soup.body else soup

    seen = set()

    for child in root.children:

        if not hasattr(child, "name"):
            continue

        key = (child.name, child.get("id"))

        if key in seen:
            continue

        seen.add(key)

        node = parse_node(child)

        if node:
            result["structure"].append(node)

    return result

# =========================
# FASTAPI (same flow as before)
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

        file_path = await client.download_media(file_message, file=DOWNLOAD_DIR)
        file_name = os.path.basename(file_path)

        response = {
            "status": True,
            "query": data.message,
            "file_name": file_name
        }

        if file_name.endswith(".html"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()

            response["parsed"] = parse_html_ai(html)

        return response

    except Exception as e:
        return {"status": False, "error": str(e)}

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body style="font-family:Arial;padding:40px;">
            <h2>Clean JSON HTML Parser</h2>
            <form action="/test" method="get">
                <input name="q" style="width:300px;height:40px;">
                <button>Search</button>
            </form>
        </body>
    </html>
    """
