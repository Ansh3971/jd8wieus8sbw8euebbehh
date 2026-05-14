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
# ADVANCED GROUPED PARSER
# =========================

def parse_message(text):

    if not text:

        return {
            "raw": "",
            "records": []
        }

    # CLEAN TEXT
    text = (
        str(text)
        .replace("\r", "")
        .strip()
    )

    lines = text.splitlines()

    records = []

    current = {}

    for line in lines:

        line = line.strip()

        # SKIP EMPTY
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

            key = (
                parts[0]
                .strip()
            )

            value = (
                parts[1]
                .strip()
            )

            # SKIP EMPTY VALUE
            if not value:
                continue

            # REMOVE EMOJIS
            for sym in [
                "📞",
                "📩",
                "👤",
                "🏘️",
                "👨",
                "🗺️",
                "🎯",
                "📆",
                "🃏",
                "🌃",
                "🔑",
                "🔐",
                "💶",
                "💸",
                "🚻",
                "🌐",
                "🔎",
                "🏢",
                "🗾"
            ]:

                key = key.replace(
                    sym,
                    ""
                )

            key = key.strip()

            lower = key.lower()

            # =====================
            # NEW RECORD DETECTION
            # =====================

            if (
                lower in [
                    "email",
                    "mail",
                    "telephone",
                    "phone",
                    "mobile",
                    "username",
                    "user",
                    "full name",
                    "name"
                ]
                and current
            ):

                records.append(
                    current
                )

                current = {}

            # =====================
            # MULTIPLE VALUES
            # =====================

            if key in current:

                if isinstance(
                    current[key],
                    list
                ):

                    if value not in current[key]:

                        current[key].append(
                            value
                        )

                else:

                    if current[key] != value:

                        current[key] = [
                            current[key],
                            value
                        ]

            else:

                current[key] = value

        else:

            # =====================
            # RAW TEXT
            # =====================

            if "_text" not in current:

                current["_text"] = []

            current["_text"].append(
                line
            )

    # =====================
    # LAST RECORD
    # =====================

    if current:

        records.append(current)

    # =====================
    # CLEAN RECORDS
    # =====================

    cleaned = []

    for rec in records:

        clean_rec = {}

        for k, v in rec.items():

            if not v:
                continue

            clean_rec[k] = v

        if clean_rec:

            cleaned.append(
                clean_rec
            )

    return {

        "raw": text,

        "total_records": len(
            cleaned
        ),

        "records": cleaned
    }

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
        # GET TEXT
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
