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
# APP INIT
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
# HOME PAGE
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <body style="font-family:Arial;padding:40px;">
            <h2>AI HTML Extractor API</h2>
            <form action="/test" method="get">
                <input name="q" style="width:300px;height:40px;" placeholder="Enter query">
                <button>Search</button>
            </form>
        </body>
    </html>
    """

# =========================
# CLEAN AI HTML PARSER
# =========================

def parse_html_ai(html):
    soup = BeautifulSoup(html, "html.parser")

    def clean(text):
        return re.sub(r"\s+", " ", text).strip()

    def valid(text):
        return text and len(text) > 3

    def is_noise(tag):
        bad = ["nav", "footer", "header", "menu", "sidebar", "ads", "advert", "cookie"]
        cls = " ".join(tag.get("class", [])).lower() if tag.get("class") else ""
        tid = tag.get("id", "").lower()
        return any(x in cls or x in tid for x in bad)

    # remove junk
    for t in soup(["script", "style", "noscript"]):
        t.decompose()

    result = {
        "title": clean(soup.title.get_text()) if soup.title else None,
        "meta": {},
        "content": [],
        "links": [],
        "images": [],
        "tables": [],
        "lists": [],
        "code": []
    }

    # ================= META =================
    for meta in soup.find_all("meta"):
        k = meta.get("name") or meta.get("property")
        v = meta.get("content")
        if k and v:
            result["meta"][k] = v

    # ================= LINKS =================
    seen_links = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        text = clean(a.get_text())

        if href not in seen_links and valid(text):
            seen_links.add(href)
            result["links"].append({
                "text": text,
                "url": href
            })

    # ================= IMAGES =================
    seen_img = set()
    for img in soup.find_all("img", src=True):
        src = img["src"]

        if src not in seen_img:
            seen_img.add(src)
            result["images"].append({
                "url": src,
                "alt": img.get("alt", "")
            })

    # ================= TABLES =================
    for table in soup.find_all("table"):
        rows = []
        for tr in table.find_all("tr"):
            cols = [clean(td.get_text()) for td in tr.find_all(["td", "th"])]
            if cols:
                rows.append(cols)
        if rows:
            result["tables"].append(rows)

    # ================= LISTS =================
    for ul in soup.find_all(["ul", "ol"]):
        items = []
        for li in ul.find_all("li"):
            txt = clean(li.get_text())
            if valid(txt):
                items.append(txt)
        if items:
            result["lists"].append(items)

    # ================= CODE =================
    seen_code = set()
    for code in soup.find_all(["pre", "code"]):
        txt = clean(code.get_text())
        if valid(txt) and txt not in seen_code:
            seen_code.add(txt)
            result["code"].append(txt)

    # ================= MAIN ARTICLE EXTRACTION =================
    candidates = soup.find_all(["article", "main", "div", "section"])
    best_block = None
    best_score = 0

    for block in candidates:
        if is_noise(block):
            continue

        text = clean(block.get_text(" "))
        score = len(text)

        if score > best_score:
            best_score = score
            best_block = block

    if not best_block:
        best_block = soup.body or soup

    seen_text = set()

    for tag in best_block.find_all(["h1", "h2", "h3", "h4", "p"]):
        text = clean(tag.get_text())

        if not valid(text):
            continue

        if text in seen_text:
            continue

        seen_text.add(text)

        if tag.name.startswith("h"):
            result["content"].append({
                "type": "heading",
                "level": tag.name,
                "text": text,
                "children": []
            })
        else:
            if result["content"] and result["content"][-1]["type"] == "heading":
                result["content"][-1]["children"].append(text)
            else:
                result["content"].append({
                    "type": "paragraph",
                    "text": text
                })

    return result

# =========================
# SEARCH FLOW (TELEGRAM BOT)
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

        # click button
        try:
            await reply.click(text=DOWNLOAD_BUTTON)
        except:
            try:
                await reply.click(0)
            except Exception as e:
                return {"status": False, "error": str(e)}

        # wait file
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

        # parse HTML if exists
        if file_name.endswith(".html"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html = f.read()

            response["parsed"] = parse_html_ai(html)

        return response

    except Exception as e:
        return {"status": False, "error": str(e)}

# =========================
# TEST ENDPOINT
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))
