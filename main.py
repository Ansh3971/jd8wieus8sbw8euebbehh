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
    title="Telegram Bot API - Multi-Page Scraper"
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
    key = re.sub(r'[^\w\s]', '', key)
    key = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', key)
    key = key.strip()
    words = key.split()
    return ' '.join(word.capitalize() for word in words)

# =========================
# GET FIELD NAME
# =========================

def get_field_name(raw_key):
    name = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', raw_key)
    name = name.strip()
    name = clean_key(name)

    mapping = {
        "Email": "Email",
        "Telephone": "Phone",
        "Phone": "Phone",
        "Adres": "Adres",
        "Address": "Adres",
        "Document number": "DocumentNumber",
        "Document": "DocumentNumber",
        "Full name": "FullName",
        "Fullname": "FullName",
        "The name of the father": "FatherName",
        "Father name": "FatherName",
        "Region": "Region",
        "Nick": "Nick",
        "Nickname": "Nick"
    }

    for key, value in mapping.items():
        if key.lower() in name.lower():
            return value

    return name.replace(" ", "")

# =========================
# PARSE VALUE FROM LINE
# =========================

def parse_line(line):
    line = line.strip()

    if not line:
        return None, None

    emoji_pattern = re.compile(
        r'^([\U00010000-\U0010FFFF\u2600-\u27BF]+)\s*(.+?):\s*(.*)$'
    )

    match = emoji_pattern.match(line)

    if match:
        key_raw = match.group(2)
        value = match.group(3).strip()

        field_name = get_field_name(key_raw)

        return field_name, value

    if line.startswith('📞'):
        phone_match = re.search(r'(\d+)', line)

        if phone_match:
            return "Phone", phone_match.group(1)

    if line.startswith('📩'):
        email_match = re.search(
            r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})',
            line
        )

        if email_match:
            return "Email", email_match.group(1)

    return None, None

# =========================
# PARSE SINGLE PAGE
# =========================

def parse_page_text(text: str) -> List[Dict[str, Any]]:

    if not text:
        return []

    if "Some data did not fit this message" in text:
        text = text.split(
            "Some data did not fit this message"
        )[0]

    lines = text.splitlines()

    data_start_idx = 0
    source_title = None

    for i, line in enumerate(lines):

        stripped = line.strip()

        if (
            stripped
            and re.match(
                r'^[\U00010000-\U0010FFFF\u2600-\u27BF]',
                stripped
            )
        ):
            if not source_title:
                source_title = stripped
                data_start_idx = i + 1
                break

    if not source_title:
        data_start_idx = 0

    for i in range(data_start_idx, len(lines)):

        line = lines[i].strip()

        if not line:
            continue

        if re.match(r'^[📩📞🏘️🃏👤👨🗺️]', line):
            data_start_idx = i
            break

    records = []
    current_record = {}

    i = data_start_idx

    while i < len(lines):

        line = lines[i].strip()

        if not line:

            if current_record:
                records.append(current_record)
                current_record = {}

            i += 1
            continue

        if "Some data did not fit this message" in line:
            break

        field_name, value = parse_line(line)

        if field_name and value:

            if field_name in ["Phone", "Email"] and field_name in current_record:
                records.append(current_record)
                current_record = {}

            if field_name in current_record:

                count = 2

                while f"{field_name}{count}" in current_record:
                    count += 1

                current_record[f"{field_name}{count}"] = value

            else:
                current_record[field_name] = value

        else:

            if current_record and line:

                if "Adres" in current_record:
                    current_record["Adres"] = (
                        current_record["Adres"] + " " + line
                    )

                elif len(current_record) > 0:

                    last_key = list(current_record.keys())[-1]

                    current_record[last_key] = (
                        current_record[last_key] + " " + line
                    )

        i += 1

    if current_record:
        records.append(current_record)

    return [r for r in records if r]

# =========================
# GET SOURCE TITLE AND DESCRIPTION
# =========================

def get_source_metadata(text: str) -> tuple:

    lines = text.splitlines()

    source_title = "Data Source"
    description = ""

    for i, line in enumerate(lines):

        stripped = line.strip()

        if (
            stripped
            and re.match(
                r'^[\U00010000-\U0010FFFF\u2600-\u27BF]',
                stripped
            )
        ):

            source_title = stripped

            desc_lines = []

            for j in range(i + 1, len(lines)):

                next_line = lines[j].strip()

                if not next_line:
                    continue

                if re.match(r'^[📩📞🏘️🃏👤👨🗺️]', next_line):
                    break

                desc_lines.append(next_line)

            description = " ".join(desc_lines)

            break

    return source_title, description

# =========================
# CLICK NEXT BUTTON - IMPROVED
# =========================

async def click_next_button(message) -> Optional[Any]:

    if not message.reply_markup:
        print("No reply_markup on message")
        return None

    try:

        rows = message.reply_markup.rows

        for row in rows:
            for button in row.buttons:

                button_text = button.text.strip()

                print(f"Found button: '{button_text}'")

                if (
                    button_text == "➡"
                    or button_text == "→"
                    or button_text == "›"
                    or "next" in button_text.lower()
                ):

                    old_text = message.message

                    print(f"Clicking button: {button_text}")

                    await message.click(text=button_text)

                    # WAIT FOR EDIT
                    for attempt in range(20):

                        await asyncio.sleep(1.5)

                        try:

                            updated_message = await client.get_messages(
                                BOT_USERNAME,
                                ids=message.id
                            )

                            if (
                                updated_message
                                and updated_message.message
                                and updated_message.message != old_text
                            ):

                                print(
                                    f"Message updated after {attempt + 1} checks"
                                )

                                return updated_message

                        except Exception as e:
                            print(f"Edit check error: {e}")

                    print("Message never updated")
                    return None

    except Exception as e:

        print(f"Error clicking next button: {e}")

        import traceback
        traceback.print_exc()

    return None

# =========================
# CHECK FOR NEXT BUTTON
# =========================

async def has_next_button(message) -> bool:

    if not message.reply_markup:
        return False

    try:

        rows = message.reply_markup.rows

        for row in rows:
            for button in row.buttons:

                txt = button.text.strip()

                if (
                    txt == "➡"
                    or txt == "→"
                    or txt == "›"
                    or "next" in txt.lower()
                ):
                    return True

    except:
        pass

    return False

# =========================
# GET CURRENT PAGE NUMBER
# =========================

def get_current_page(text: str) -> Optional[int]:

    match = re.search(r'(\d+)/(\d+)', text)

    if match:
        return int(match.group(1)), int(match.group(2))

    return None, None

# =========================
# MAIN SEARCH WITH PAGINATION
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        print("\n========== NEW REQUEST ==========")
        print("Query:", data.message)

        sent = await client.send_message(
            BOT_USERNAME,
            data.message
        )

        print("Message Sent, ID:", sent.id)

        target_message = None

        # WAIT FOR BOT REPLY
        for i in range(30):

            print(f"Checking Messages Attempt {i+1}")

            await asyncio.sleep(2)

            messages = await client.get_messages(
                BOT_USERNAME,
                limit=30
            )

            for msg in messages:

                if msg.out:
                    continue

                if not msg.message:
                    continue

                if msg.id <= sent.id:
                    continue

                if msg.message.strip() == data.message.strip():
                    continue

                target_message = msg

                print("\nFOUND BOT REPLY")
                print(msg.message[:200] + "...")

                break

            if target_message:
                break

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

        source_title = None
        source_description = None

        max_pages = 50

        seen_messages = set()

        while current_message and page_num <= max_pages:

            print(f"\n--- Processing Page {page_num} ---")

            # FIXED HASH
            msg_hash = hash(current_message.message)

            if msg_hash in seen_messages and page_num > 1:
                print("Detected duplicate page")
                break

            seen_messages.add(msg_hash)

            if source_title is None:

                source_title, source_description = get_source_metadata(
                    current_message.message
                )

                print(f"Source Title: {source_title}")

            # PARSE PAGE
            page_records = parse_page_text(
                current_message.message
            )

            print(
                f"Found {len(page_records)} records on page {page_num}"
            )

            print(
                f"Current Total Records: "
                f"{len(all_records) + len(page_records)}"
            )

            all_records.extend(page_records)

            current_page, total_pages = get_current_page(
                current_message.message
            )

            if current_page:
                print(f"Page {current_page}/{total_pages}")

            has_next = await has_next_button(current_message)

            if not has_next:
                print("No next page button found. Done.")
                break

            if (
                total_pages
                and current_page
                and current_page >= total_pages
            ):
                print(
                    f"Reached last page "
                    f"({current_page}/{total_pages}). Done."
                )
                break

            print("Clicking next page button...")

            old_message_text = current_message.message.strip()

            next_message = await click_next_button(current_message)

            if not next_message:
                print("Failed to get next page. Stopping.")
                break

            # RETRY FIX
            if (
                next_message.message.strip()
                == old_message_text
            ):

                print("Same page received again. Retrying...")

                retry_next = await click_next_button(
                    current_message
                )

                if (
                    not retry_next
                    or retry_next.message.strip()
                    == old_message_text
                ):
                    print(
                        "Still same page after retry. Stopping."
                    )
                    break

                next_message = retry_next

            current_message = next_message

            page_num += 1

            # FIXED DELAY
            await asyncio.sleep(2.5)

        print(
            f"\n=== TOTAL: "
            f"{len(all_records)} records collected "
            f"from {page_num} pages ==="
        )

        result = {
            "source1": {
                "title": source_title or "Data Source",
                "description": source_description or "",
                "records": all_records
            }
        }

        return {
            "status": True,
            "query": data.message,
            "data": result,
            "meta": {
                "pages_scraped": page_num,
                "total_records": len(all_records)
            }
        }

    except Exception as e:

        print("\nERROR:")
        print(str(e))

        import traceback
        traceback.print_exc()

        return {
            "status": False,
            "error": str(e)
        }

# =========================
# TEST ENDPOINT
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
        "message": "Multi-Page Telegram Bot Scraper API Running",
        "features": [
            "Automatic pagination detection",
            "Auto-click next page button",
            "Handles message editing",
            "Merges all pages",
            "Retry on same page",
            "Loop detection safety"
        ]
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
