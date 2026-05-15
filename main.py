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
# CLEAN FIELD NAME
# =========================

def clean_key(key):
    key = re.sub(r'[^\w\s]', '', key)
    key = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', key)
    key = key.strip()
    words = key.split()
    return ' '.join(word.capitalize() for word in words)

# =========================
# NORMALIZE FIELD NAMES
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
        "Nickname": "Nick",
        "Password": "Password",
        "Encrypted password": "EncryptedPassword",
        "Date": "Date",
        "The date of registration": "RegistrationDate",
        "Last activity": "LastActivity",
        "IP": "IP",
        "City": "City",
        "Country": "Country",
        "Name": "Name",
        "Surname": "Surname",
        "Gender": "Gender",
        "Currency": "Currency",
        "Sum": "Sum",
        "Browser": "Browser",
        "Source": "Source"
    }

    for key, value in mapping.items():
        if key.lower() in name.lower():
            return value

    return name.replace(" ", "")

# =========================
# PARSE SINGLE LINE
# =========================

def parse_line(line):
    line = line.strip()

    if not line:
        return None, None

    line = re.sub(r'<.*?>', '', line)

    pattern = r'^[^\w\s]*\s*([^:]+):\s*(.+)$'
    match = re.match(pattern, line)

    if match:
        raw_key = match.group(1).strip()
        value = match.group(2).strip()

        raw_key = re.sub(r'^[^\w]+', '', raw_key)

        field = get_field_name(raw_key)

        value = value.replace("`", "").strip()

        return field, value

    return None, None

# =========================
# CHECK DATA LINE
# =========================

def is_data_line(line):
    line = line.strip()

    if not line:
        return False

    return ":" in line

# =========================
# PARSE MESSAGE
# =========================

def parse_message(text):
    if not text:
        return {}

    # remove truncation note
    if "Some data did not fit this message" in text:
        text = text.split("Some data did not fit this message")[0]

    lines = text.splitlines()

    source_title = "Data Source"
    source_description = ""

    # =========================
    # FIND TITLE
    # =========================

    title_index = 0

    for i, line in enumerate(lines):
        line = line.strip()

        if not line:
            continue

        if not is_data_line(line):
            source_title = line
            title_index = i
            break

    # =========================
    # FIND DESCRIPTION
    # =========================

    desc_lines = []

    data_start = 0

    for i in range(title_index + 1, len(lines)):
        line = lines[i].strip()

        if not line:
            continue

        if is_data_line(line):
            data_start = i
            break

        desc_lines.append(line)

    source_description = " ".join(desc_lines).strip()

    # =========================
    # PARSE RECORDS
    # =========================

    records = []

    current_record = {}

    for i in range(data_start, len(lines)):

        line = lines[i].strip()

        if not line:
            continue

        # stop note
        if "Some data did not fit this message" in line:
            break

        field, value = parse_line(line)

        if not field:
            continue

        # =========================
        # NEW RECORD DETECTION
        # =========================

        # If Phone/Email starts again
        if field in ["Phone", "Email"] and current_record:
            if field in current_record:
                records.append(current_record)
                current_record = {}

        # =========================
        # DUPLICATE FIELD HANDLING
        # =========================

        if field in current_record:
            count = 2

            while f"{field}{count}" in current_record:
                count += 1

            current_record[f"{field}{count}"] = value

        else:
            current_record[field] = value

    # add final record
    if current_record:
        records.append(current_record)

    # remove empty
    records = [r for r in records if r]

    return {
        "source1": {
            "title": source_title,
            "description": source_description,
            "records": records
        }
    }

# =========================
# WAIT FOR MESSAGE EDIT
# =========================

async def wait_for_edited_message(message, old_text, timeout=15):
    """
    Wait until telegram edits the same message
    """

    for _ in range(timeout):

        await asyncio.sleep(1.5)

        try:
            updated = await client.get_messages(
                BOT_USERNAME,
                ids=message.id
            )

            if updated and updated.message != old_text:
                return updated

        except Exception as e:
            print("Edit wait error:", e)

    return None

# =========================
# HAS NEXT BUTTON
# =========================

def has_next_button(message):

    if not message.reply_markup:
        return False

    try:
        rows = message.reply_markup.rows

        for row in rows:
            for button in row.buttons:

                txt = button.text.strip()

                if txt in ["➡", "→", "Next", "›"]:
                    return True

    except:
        pass

    return False

# =========================
# CLICK NEXT BUTTON
# =========================

async def click_next(message):

    if not message.reply_markup:
        return None

    rows = message.reply_markup.rows

    for row in rows:
        for button in row.buttons:

            txt = button.text.strip()

            if txt in ["➡", "→", "Next", "›"]:

                old_text = message.message

                try:
                    await message.click(text=txt)

                    updated = await wait_for_edited_message(
                        message,
                        old_text,
                        timeout=20
                    )

                    return updated

                except Exception as e:
                    print("Click Error:", e)
                    return None

    return None

# =========================
# MAIN SEARCH
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

        print("Message Sent")
        print("Sent ID:", sent.id)

        target_message = None

        # =========================
        # WAIT BOT REPLY
        # =========================

        for i in range(40):

            print(f"Checking Messages Attempt {i+1}")

            await asyncio.sleep(2)

            messages = await client.get_messages(
                BOT_USERNAME,
                limit=20
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
                print(target_message.message[:300])

                break

            if target_message:
                break

        if not target_message:
            return {
                "status": False,
                "error": "Bot reply timeout"
            }

        # =========================
        # PAGINATION SCRAPER
        # =========================

        full_text = ""

        processed_pages = set()

        current_message = target_message

        max_pages = 50

        for page in range(max_pages):

            if not current_message:
                break

            current_text = current_message.message.strip()

            text_hash = hash(current_text)

            # avoid duplicate page
            if text_hash in processed_pages:
                print("Duplicate page detected")
                break

            processed_pages.add(text_hash)

            print(f"\nSCRAPING PAGE {page + 1}")

            full_text += "\n\n" + current_text

            # no next button
            if not has_next_button(current_message):
                print("No next button found")
                break

            print("NEXT BUTTON FOUND")

            next_page = await click_next(current_message)

            if not next_page:
                print("Failed loading next page")
                break

            current_message = next_page

            await asyncio.sleep(2)

        # =========================
        # PARSE FINAL DATA
        # =========================

        parsed = parse_message(full_text)

        return {
            "status": True,
            "query": data.message,
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
# TEST ENDPOINT
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))

# =========================
# ROOT
# =========================

@app.get("/")
async def root():
    return {
        "status": True,
        "message": "Telegram Multi Page Scraper Running"
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
