import os
import asyncio

from fastapi import FastAPI
from pydantic import BaseModel

from telethon import TelegramClient
from telethon.sessions import StringSession

from dotenv import load_dotenv

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
    title="Telegram Bot API"
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
# SIMPLE PARSER
# =========================

def parse_message(text):

    parsed = {}

    if not text:
        return parsed

    lines = text.splitlines()

    for line in lines:

        line = line.strip()

        if not line:
            continue

        if ":" in line:

            parts = line.split(":", 1)

            key = parts[0].strip()
            value = parts[1].strip()

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

    return parsed

# =========================
# MAIN SEARCH
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        print("\n========== NEW REQUEST ==========")
        print("Query:", data.message)

        # =====================
        # SEND MESSAGE
        # =====================

        sent = await client.send_message(
            BOT_USERNAME,
            data.message
        )

        print("Message Sent")
        print("Sent ID:", sent.id)

        # =====================
        # WAIT FOR BOT REPLY
        # =====================

        target_message = None

        for i in range(30):

            print(f"\nChecking Messages Attempt {i+1}")

            await asyncio.sleep(2)

            messages = await client.get_messages(
                BOT_USERNAME,
                limit=15
            )

            print("Messages Found:", len(messages))

            for msg in messages:

                print("\n----- MESSAGE -----")
                print("ID:", msg.id)
                print("OUT:", msg.out)
                print("TEXT:", msg.message)

                # SKIP YOUR OWN MESSAGE
                if msg.out:
                    print("Skipped Own Message")
                    continue

                # SKIP EMPTY
                if not msg.message:
                    print("Skipped Empty Message")
                    continue

                # ONLY NEW MESSAGE
                if msg.id <= sent.id:
                    print("Skipped Old Message")
                    continue

                # SKIP SAME QUERY
                if (
                    msg.message.strip()
                    ==
                    data.message.strip()
                ):
                    print("Skipped Same Query")
                    continue

                # FOUND
                target_message = msg

                print("\nFOUND BOT REPLY")
                print(target_message.message)

                break

            if target_message:
                break

        # =====================
        # TIMEOUT
        # =====================

        if not target_message:

            print("\nBOT REPLY TIMEOUT")

            return {
                "status": False,
                "error": "Bot reply timeout"
            }

        # =====================
        # TEXT
        # =====================

        text = target_message.message

        # =====================
        # PARSE
        # =====================

        parsed = parse_message(text)

        # =====================
        # RESPONSE
        # =====================

        return {

            "status": True,

            "query": data.message,

            "message_id": target_message.id,

            "date": str(
                target_message.date
            ),

            "text": text,

            "parsed": parsed
        }

    except Exception as e:

        print("\nERROR:")
        print(str(e))

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
# ROOT
# =========================

@app.get("/")
async def root():

    return {
        "status": True,
        "message": "API Running"
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
