import os
import re
import asyncio

from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from telethon import TelegramClient
from telethon.sessions import StringSession

# =========================
# LOAD ENV
# =========================

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BOT_USERNAME = os.getenv("BOT_USERNAME")

# =========================
# FASTAPI
# =========================

app = FastAPI(
    title="Telegram Bot JSON API"
)

# =========================
# TELEGRAM CLIENT
# =========================

client = TelegramClient(
    StringSession(SESSION),
    API_ID,
    API_HASH
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

    print("Telegram Client Connected")

# =========================
# SHUTDOWN
# =========================

@app.on_event("shutdown")
async def shutdown():

    await client.disconnect()

# =========================
# TEXT CLEANER
# =========================

def clean_text(text):

    if not text:
        return ""

    return (
        str(text)
        .replace("\n", " ")
        .replace("\t", " ")
        .replace("\r", " ")
        .strip()
    )

# =========================
# GENERIC MESSAGE PARSER
# =========================

def parse_message(text):

    result = {
        "raw": text,
        "parsed": {}
    }

    if not text:
        return result

    lines = text.splitlines()

    parsed = {}

    for line in lines:

        line = clean_text(line)

        if not line:
            continue

        # key: value
        if ":" in line:

            parts = line.split(":", 1)

            key = clean_text(parts[0])
            value = clean_text(parts[1])

            if not key or not value:
                continue

            # MULTIPLE VALUES
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

    # DEDUPE
    for k, v in parsed.items():

        if isinstance(v, list):

            unique = []

            for item in v:
                if item not in unique:
                    unique.append(item)

            parsed[k] = unique

    result["parsed"] = parsed

    # EXTRACT URLS
    urls = re.findall(
        r'https?://\\S+',
        text
    )

    if urls:
        result["urls"] = urls

    # EXTRACT EMAILS
    emails = re.findall(
        r'[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,}',
        text
    )

    if emails:
        result["emails"] = list(set(emails))

    return result

# =========================
# MAIN SEARCH
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        # SEND MESSAGE TO BOT
        await client.send_message(
            BOT_USERNAME,
            data.message
        )

        # WAIT RESPONSE
        await asyncio.sleep(3)

        # GET LATEST MESSAGE
        messages = await client.get_messages(
            BOT_USERNAME,
            limit=5
        )

        if not messages:

            return {
                "status": False,
                "error": "No response from bot"
            }

        target_message = None

        for msg in messages:

            if msg.message:
                target_message = msg
                break

        if not target_message:

            return {
                "status": False,
                "error": "No text message found"
            }

        text = target_message.message

        parsed = parse_message(text)

        return {
            "status": True,
            "query": data.message,
            "message_id": target_message.id,
            "date": str(target_message.date),
            "text": text,
            "data": parsed
        }

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

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
