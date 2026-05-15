import os
import re
import asyncio
from typing import Optional, List, Dict, Any

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
    title="Telegram Bot API - Stable Multi Page Scraper"
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
        r'[^\w\s]',
        '',
        key
    )

    key = re.sub(
        r'[\U00010000-\U0010FFFF\u2600-\u27BF]',
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
# FIELD NAME NORMALIZER
# =========================

def get_field_name(raw_key):

    name = re.sub(
        r'[\U00010000-\U0010FFFF\u2600-\u27BF]',
        '',
        raw_key
    )

    name = name.strip()

    name = clean_key(name)

    mapping = {

        "Email": "Email",

        "Telephone": "Phone",

        "Phone": "Phone",

        "Adres": "Address",

        "Address": "Address",

        "DocumentNumber": "DocumentNumber",

        "Document": "DocumentNumber",

        "FullName": "FullName",

        "TheNameOfTheFather": "FatherName",

        "FatherName": "FatherName",

        "Region": "Region",

        "Nick": "Nick",

        "Nickname": "Nick"
    }

    for key, value in mapping.items():

        if key.lower() in name.lower():
            return value

    return name.replace(" ", "")

# =========================
# PARSE LINE
# =========================

def parse_line(line):

    line = line.strip()

    if not line:
        return None, None

    if ":" not in line:
        return None, None

    parts = line.split(":", 1)

    key_raw = parts[0].strip()

    value = parts[1].strip()

    if not value:
        return None, None

    field_name = get_field_name(
        key_raw
    )

    return field_name, value

# =========================
# PARSE PAGE
# =========================

def parse_page_text(text):

    if not text:
        return []

    lines = text.splitlines()

    records = []

    current_record = {}

    for raw_line in lines:

        line = raw_line.strip()

        if not line:
            continue

        # SKIP PAGE TEXT
        if (
            "Some data did not fit this message"
            in line
        ):
            continue

        # FIELD
        field_name, value = parse_line(
            line
        )

        if field_name and value:

            # START NEW RECORD
            if (
                field_name in [
                    "Phone",
                    "Email",
                    "FullName",
                    "Name"
                ]
                and current_record
                and (
                    "Phone" in current_record
                    or "Email" in current_record
                )
            ):

                records.append(
                    current_record
                )

                current_record = {}

            # DUPLICATES
            if field_name in current_record:

                count = 2

                while (
                    f"{field_name}{count}"
                    in current_record
                ):
                    count += 1

                current_record[
                    f"{field_name}{count}"
                ] = value

            else:

                current_record[
                    field_name
                ] = value

    # LAST RECORD
    if current_record:
        records.append(current_record)

    return records

# =========================
# SOURCE META
# =========================

def get_source_metadata(text):

    lines = text.splitlines()

    title = "Data Source"

    description = ""

    for i, line in enumerate(lines):

        line = line.strip()

        if not line:
            continue

        if (
            ":" not in line
            and len(line) < 100
        ):

            title = line

            desc = []

            for j in range(i + 1, len(lines)):

                next_line = lines[j].strip()

                if not next_line:
                    continue

                if ":" in next_line:
                    break

                desc.append(next_line)

            description = " ".join(desc)

            break

    return title, description

# =========================
# CHECK NEXT BUTTON
# =========================

async def has_next_button(message):

    if not message.reply_markup:
        return False

    try:

        rows = message.reply_markup.rows

        for row in rows:
            for button in row.buttons:

                txt = button.text

                if (
                    txt == "➡"
                    or txt == "→"
                    or "next" in txt.lower()
                ):
                    return True

    except:
        pass

    return False

# =========================
# CLICK NEXT BUTTON
# =========================

async def click_next_button(message):

    if not message.reply_markup:
        return None

    old_text = message.message or ""

    try:

        rows = message.reply_markup.rows

        for row in rows:
            for button in row.buttons:

                button_text = button.text

                if (
                    button_text == '➡'
                    or button_text == '→'
                    or 'next' in button_text.lower()
                ):

                    print(f"Clicking: {button_text}")

                    # CLICK BUTTON
                    await message.click(
                        text=button_text
                    )

                    # WAIT FOR MESSAGE EDIT
                    for _ in range(20):

                        await asyncio.sleep(1)

                        updated = await client.get_messages(
                            BOT_USERNAME,
                            ids=message.id
                        )

                        if not updated:
                            continue

                        new_text = updated.message or ""

                        if (
                            new_text.strip()
                            and new_text != old_text
                        ):

                            print("New page loaded")

                            return updated

                    print("Page update timeout")

                    return None

    except Exception as e:

        print("Button Click Error:", e)

    return None

# =========================
# SEARCH
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        print("\n========== NEW REQUEST ==========")
        print("Query:", data.message)

        # SEND MESSAGE
        sent = await client.send_message(
            BOT_USERNAME,
            data.message
        )

        print("Message Sent")

        # WAIT FOR FIRST REPLY
        target_message = None

        for i in range(30):

            print(f"Checking {i+1}")

            await asyncio.sleep(2)

            messages = await client.get_messages(
                BOT_USERNAME,
                limit=15
            )

            for msg in messages:

                if msg.out:
                    continue

                if not msg.message:
                    continue

                if msg.id <= sent.id:
                    continue

                if (
                    msg.message.strip()
                    ==
                    data.message.strip()
                ):
                    continue

                target_message = msg

                print("Bot Reply Found")

                break

            if target_message:
                break

        # TIMEOUT
        if not target_message:

            return {
                "status": False,
                "error": "Bot reply timeout"
            }

        # =========================
        # PAGINATION
        # =========================

        all_records = []

        current_message = target_message

        page_num = 1

        max_pages = 50

        processed_pages = set()

        source_title = None

        source_description = None

        while (
            current_message
            and page_num <= max_pages
        ):

            print(f"\nProcessing Page {page_num}")

            # DUPLICATE PAGE CHECK
            page_signature = (
                current_message.message[:300]
            )

            if (
                page_signature
                in processed_pages
            ):

                print("Duplicate page detected")

                break

            processed_pages.add(
                page_signature
            )

            # SOURCE META
            if source_title is None:

                source_title, source_description = (
                    get_source_metadata(
                        current_message.message
                    )
                )

            # PARSE PAGE
            page_records = parse_page_text(
                current_message.message
            )

            print(
                f"Records Found: {len(page_records)}"
            )

            all_records.extend(
                page_records
            )

            # CHECK NEXT BUTTON
            has_next = await has_next_button(
                current_message
            )

            if not has_next:

                print("No next button")

                break

            # NEXT PAGE
            next_message = await click_next_button(
                current_message
            )

            if not next_message:

                print("Failed loading next page")

                break

            current_message = next_message

            page_num += 1

            await asyncio.sleep(1)

        # =========================
        # RESPONSE
        # =========================

        return {

            "status": True,

            "query": data.message,

            "data": {

                "source1": {

                    "title": source_title,

                    "description": source_description,

                    "records": all_records
                }
            },

            "meta": {

                "pages_scraped": page_num,

                "total_records": len(
                    all_records
                )
            }
        }

    except Exception as e:

        print("\nERROR:")
        print(str(e))

        return {
            "status": False,
            "error": str(e)
        }

# =========================
# TEST
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

        "message": "Stable Multi Page Telegram Scraper API Running"
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
