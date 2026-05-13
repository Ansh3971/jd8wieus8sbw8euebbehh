import os
import asyncio
from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel
from telethon import TelegramClient
from telethon.sessions import StringSession
from bs4 import BeautifulSoup

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BOT_USERNAME = os.getenv("BOT_USERNAME")
DOWNLOAD_BUTTON = os.getenv("DOWNLOAD_BUTTON", "Download")

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


@app.on_event("startup")
async def startup():
    await client.start()
    print("Telegram client started")


@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()


@app.get("/")
async def home():
    return {
        "status": True,
        "message": "Telegram Download API Running"
    }


@app.post("/search")
async def search(data: Query)
@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))    
    try:
        # Send message to bot
        sent_message = await client.send_message(
            BOT_USERNAME,
            data.message
        )

        # Wait for bot response
        await asyncio.sleep(3)

        bot_messages = await client.get_messages(
            BOT_USERNAME,
            limit=1
        )

        if not bot_messages:
            return {
                "status": False,
                "error": "No response from bot"
            }

        reply_message = bot_messages[0]

        # Click download button
        try:
            await reply_message.click(text=DOWNLOAD_BUTTON)
        except Exception:
            try:
                await reply_message.click(0)
            except Exception as e:
                return {
                    "status": False,
                    "error": f"Button click failed: {str(e)}"
                }

        # Wait for file
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

        # Download file
        file_path = await client.download_media(
            file_message,
            file=DOWNLOAD_DIR
        )

        file_name = os.path.basename(file_path)

        response_data = {
            "status": True,
            "query": data.message,
            "file_name": file_name,
            "path": file_path,
            "size": os.path.getsize(file_path)
        }

        # Read HTML if html file
        if file_name.endswith(".html"):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()

            soup = BeautifulSoup(html_content, "html.parser")

            response_data["title"] = soup.title.string if soup.title else None
            response_data["html_preview"] = html_content[:2000]

        return response_data

    except Exception as e:
        return {
            "status": False,
            "error": str(e)
        }
