import os
import re
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
# CLEAN KEY
# =========================

def clean_key(key):

    key = re.sub(
        r'[^a-zA-Z0-9 ]',
        '',
        key
    )

    key = key.strip()

    words = key.split()

    return ''.join(
        word.capitalize()
        for word in words
    )

# =========================
# ADVANCED GROUPED PARSER
# =========================

def parse_message(text):

    result = {
        "raw": text,
        "records": []
    }

    if not text:
        return result

    lines = text.splitlines()

    current = {}

    record_start_keys = [
        "Email",
        "Phone",
        "Telephone",
        "Username",
        "User",
        "FullName",
        "Name"
    ]

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            continue

        # =====================
        # KEY : VALUE
        # =====================

        if ":" in line:

            parts = line.split(
                ":",
                1
            )

            key = clean_key(
                parts[0]
            )

            value = parts[1].strip()

            if not value:
                continue

            # =====================
            # NEW RECORD
            # =====================

            if (
                key in record_start_keys
                and current
            ):

                result["records"].append(
                    current
                )

                current = {}

            # =====================
            # DUPLICATE KEYS
            # =====================

            if key in current:

                count = 2

                while (
                    f"{key}{count}"
                    in current
                ):
                    count += 1

                current[
                    f"{key}{count}"
                ] = value

            else:

                current[key] = value

        else:

            # =====================
            # DESCRIPTION TEXT
            # =====================

            if "_description" not in current:

                current["_description"] = []

            current["_description"].append(
                line
            )

    # =====================
    # LAST RECORD
    # =====================

    if current:

        result["records"].append(
            current
        )

    # =====================
    # TOTAL
    # =====================

    result["total_records"] = len(
        result["records"]
    )

    return result

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

            for msg in messages:

                # SKIP OWN MESSAGE
                if msg.out:
                    continue

                # SKIP EMPTY
                if not msg.message:
                    continue

                # ONLY NEW MESSAGE
                if msg.id <= sent.id:
                    continue

                # SKIP SAME QUERY
                if (
                    msg.message.strip()
                    ==
                    data.message.strip()
                ):
                    continue

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

        parsed = parse_message(
            text
        )

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

            "data": parsed
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
