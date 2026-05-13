import os
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
        <head>
            <title>Telegram Search API</title>
        </head>

        <body style="font-family: Arial; padding: 40px;">
            <h2>Telegram Search API</h2>

            <form action="/test" method="get">

                <input
                    type="text"
                    name="q"
                    placeholder="Enter query"
                    style="width:300px;height:40px;padding:10px;"
                >

                <button
                    type="submit"
                    style="height:40px;"
                >
                    Search
                </button>

            </form>
        </body>
    </html>
    """

# =========================
# MAIN SEARCH FUNCTION
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        # SEND MESSAGE
        await client.send_message(
            BOT_USERNAME,
            data.message
        )

        # WAIT BOT RESPONSE
        await asyncio.sleep(3)

        messages = await client.get_messages(
            BOT_USERNAME,
            limit=1
        )

        if not messages:
            return {
                "status": False,
                "error": "No response from bot"
            }

        reply_message = messages[0]

        # CLICK DOWNLOAD BUTTON
        try:
            await reply_message.click(
                text=DOWNLOAD_BUTTON
            )

        except Exception:

            try:
                await reply_message.click(0)

            except Exception as e:

                return {
                    "status": False,
                    "error": f"Button click failed: {str(e)}"
                }

        # WAIT FOR FILE
        file_message = None

        for _ in range(15):

            await asyncio.sleep(1)

            latest = await client.get_messages(
                BOT_USERNAME,
                limit=1
            )

            if latest and latest[0].file:
                file_message = latest[0]
                break

        if not file_message:
            return {
                "status": False,
                "error": "No file received"
            }

        # DOWNLOAD FILE
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

        # =========================
        # READ HTML FILE
        # =========================

        if file_name.endswith(".html"):

            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                html_content = f.read()

            soup = BeautifulSoup(
                html_content,
                "html.parser"
            )

            # ALL BLOCKS
            blocks = soup.find_all(
                "div",
                class_="block"
            )

            clean_results = []

            for block in blocks:

                # SOURCE NAME
                title_tag = block.find(
                    "div",
                    class_="block-title"
                )

                source_name = (
                    title_tag.get_text(strip=True)
                    if title_tag else "Unknown"
                )

                # BLOCK TEXT
                text_div = block.find(
                    "div",
                    class_="block-text"
                )

                if not text_div:
                    continue

                # FIND ALL LABELS
                labels = text_div.find_all("b")

                parsed = {}

                for label in labels:

                    # CLEAN KEY
                    key = label.get_text(
                        strip=True
                    ).replace(":", "")

                    key = (
                        key.replace("📞", "")
                           .replace("📩", "")
                           .replace("👤", "")
                           .replace("🏘️", "")
                           .replace("👨", "")
                           .replace("🗺️", "")
                           .replace("🎯", "")
                           .replace("📆", "")
                           .replace("🃏", "")
                           .replace("🌃", "")
                           .replace("🔑", "")
                           .replace("🔐", "")
                           .replace("💶", "")
                           .replace("💸", "")
                           .replace("🚻", "")
                           .replace("🌐", "")
                           .replace("🔎", "")
                           .replace("🏢", "")
                           .replace("🗾", "")
                           .strip()
                    )

                    value = ""

                    # NEXT VALUE
                    next_node = label.next_sibling

                    if next_node:
                        value = str(next_node).strip()

                    # CLEAN VALUE
                    value = (
                        value.replace("<br/>", "")
                             .replace("<br>", "")
                             .replace("\n", " ")
                             .strip()
                    )

                    # MULTIPLE VALUES SUPPORT
                    if key in parsed:

                        if isinstance(parsed[key], list):
                            parsed[key].append(value)

                        else:
                            parsed[key] = [
                                parsed[key],
                                value
                            ]

                    else:
                        parsed[key] = value

                clean_results.append({
                    "source": source_name,
                    "data": parsed
                })

            # FINAL JSON
            response["results"] = clean_results

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
