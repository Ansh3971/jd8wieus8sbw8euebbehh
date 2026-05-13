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
DOWNLOAD_BUTTON = os.getenv(
    "DOWNLOAD_BUTTON",
    "Download"
)

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

os.makedirs(
    DOWNLOAD_DIR,
    exist_ok=True
)

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

    print(
        "Telegram Client Started"
    )

# =========================
# SHUTDOWN
# =========================

@app.on_event("shutdown")
async def shutdown():

    await client.disconnect()

# =========================
# HOME PAGE
# =========================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def home():

    return """
    <html>

        <head>
            <title>
                Universal HTML Parser API
            </title>
        </head>

        <body
            style="
                font-family: Arial;
                padding: 40px;
            "
        >

            <h2>
                Universal HTML Parser API
            </h2>

            <form
                action="/test"
                method="get"
            >

                <input
                    type="text"
                    name="q"
                    placeholder="Enter query"
                    style="
                        width:300px;
                        height:40px;
                        padding:10px;
                    "
                >

                <button
                    type="submit"
                    style="
                        height:40px;
                    "
                >
                    Search
                </button>

            </form>

        </body>

    </html>
    """

# =========================
# UNIVERSAL HTML PARSER
# =========================

def parse_html_universal(html):

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    result = {
        "title": None,
        "meta": {},
        "links": [],
        "images": [],
        "tables": [],
        "forms": [],
        "lists": [],
        "codes": [],
        "texts": [],
        "blocks": []
    }

    # =====================
    # TITLE
    # =====================

    if soup.title:
        result["title"] = (
            soup.title.get_text(
                " ",
                strip=True
            )
        )

    # =====================
    # META TAGS
    # =====================

    metas = soup.find_all("meta")

    for meta in metas:

        name = (
            meta.get("name")
            or meta.get("property")
            or meta.get("charset")
        )

        content = (
            meta.get("content")
            or meta.get("charset")
        )

        if name and content:
            result["meta"][name] = content

    # =====================
    # LINKS
    # =====================

    for a in soup.find_all("a"):

        href = a.get("href")

        result["links"].append({
            "text": a.get_text(
                " ",
                strip=True
            ),
            "href": href
        })

    # =====================
    # IMAGES
    # =====================

    for img in soup.find_all("img"):

        result["images"].append({
            "src": img.get("src"),
            "alt": img.get("alt")
        })

    # =====================
    # TABLES
    # =====================

    for table in soup.find_all("table"):

        rows_data = []

        rows = table.find_all("tr")

        for row in rows:

            cols = row.find_all(
                ["td", "th"]
            )

            row_data = []

            for col in cols:

                row_data.append(
                    col.get_text(
                        " ",
                        strip=True
                    )
                )

            if row_data:
                rows_data.append(
                    row_data
                )

        if rows_data:
            result["tables"].append(
                rows_data
            )

    # =====================
    # FORMS
    # =====================

    for form in soup.find_all("form"):

        inputs = []

        for inp in form.find_all(
            ["input", "textarea", "select"]
        ):

            inputs.append({
                "type": inp.get("type"),
                "name": inp.get("name"),
                "value": inp.get("value"),
                "placeholder": inp.get(
                    "placeholder"
                )
            })

        result["forms"].append({
            "action": form.get("action"),
            "method": form.get("method"),
            "inputs": inputs
        })

    # =====================
    # LISTS
    # =====================

    for ul in soup.find_all(
        ["ul", "ol"]
    ):

        items = []

        for li in ul.find_all("li"):

            items.append(
                li.get_text(
                    " ",
                    strip=True
                )
            )

        if items:
            result["lists"].append(
                items
            )

    # =====================
    # CODE BLOCKS
    # =====================

    for code in soup.find_all(
        ["code", "pre"]
    ):

        text = code.get_text(
            "\n",
            strip=True
        )

        if text:

            result["codes"].append(
                text
            )

    # =====================
    # TEXT BLOCKS
    # =====================

    text_tags = soup.find_all([
        "p",
        "span",
        "div",
        "section",
        "article"
    ])

    for tag in text_tags:

        text = tag.get_text(
            " ",
            strip=True
        )

        text = re.sub(
            r"\\s+",
            " ",
            text
        )

        if (
            text
            and len(text) > 2
        ):

            result["texts"].append(
                text
            )

    # =====================
    # UNIVERSAL BLOCK PARSER
    # =====================

    all_blocks = soup.find_all(
        [
            "div",
            "section",
            "article",
            "table"
        ]
    )

    for block in all_blocks:

        item = {}

        # HEADINGS

        heading = block.find(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "b"
            ]
        )

        if heading:

            item["heading"] = (
                heading.get_text(
                    " ",
                    strip=True
                )
            )

        # RAW TEXT

        raw_text = block.get_text(
            "\n",
            strip=True
        )

        raw_text = re.sub(
            r"\\n+",
            "\\n",
            raw_text
        )

        if raw_text:

            item["text"] = raw_text

        # KEYS VALUES

        kv = {}

        bolds = block.find_all("b")

        for b in bolds:

            key = b.get_text(
                " ",
                strip=True
            )

            key = key.replace(
                ":",
                ""
            ).strip()

            value = ""

            code = b.find_next(
                "code"
            )

            if code:

                value = code.get_text(
                    " ",
                    strip=True
                )

            else:

                nxt = b.next_sibling

                if nxt:

                    value = str(
                        nxt
                    ).strip()

            value = (
                value
                .replace("\\n", " ")
                .replace("<br/>", "")
                .replace("<br>", "")
                .strip()
            )

            if value:

                if key in kv:

                    if isinstance(
                        kv[key],
                        list
                    ):

                        kv[key].append(
                            value
                        )

                    else:

                        kv[key] = [
                            kv[key],
                            value
                        ]

                else:

                    kv[key] = value

        if kv:

            item["fields"] = kv

        if item:

            result["blocks"].append(
                item
            )

    return result

# =========================
# SEARCH FUNCTION
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        # SEND MESSAGE

        await client.send_message(
            BOT_USERNAME,
            data.message
        )

        # WAIT

        await asyncio.sleep(3)

        messages = await client.get_messages(
            BOT_USERNAME,
            limit=1
        )

        if not messages:

            return {
                "status": False,
                "error": "No response"
            }

        reply = messages[0]

        # CLICK BUTTON

        try:

            await reply.click(
                text=DOWNLOAD_BUTTON
            )

        except Exception:

            try:

                await reply.click(0)

            except Exception as e:

                return {
                    "status": False,
                    "error": str(e)
                }

        # WAIT FILE

        file_message = None

        for _ in range(20):

            await asyncio.sleep(1)

            latest = await client.get_messages(
                BOT_USERNAME,
                limit=1
            )

            if (
                latest
                and latest[0].file
            ):

                file_message = latest[0]

                break

        if not file_message:

            return {
                "status": False,
                "error": "No file"
            }

        # DOWNLOAD FILE

        file_path = await client.download_media(
            file_message,
            file=DOWNLOAD_DIR
        )

        file_name = os.path.basename(
            file_path
        )

        response = {
            "status": True,
            "query": data.message,
            "file_name": file_name,
            "size": os.path.getsize(
                file_path
            )
        }

        # PARSE HTML

        if file_name.endswith(".html"):

            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                html_content = f.read()

            parsed = parse_html_universal(
                html_content
            )

            response["parsed"] = parsed

        return response

    except Exception as e:

        return {
            "status": False,
            "error": str(e)
        }

# =========================
# BROWSER SEARCH
# =========================

@app.get("/test")
async def test(q: str):

    return await search(
        Query(message=q)
)
