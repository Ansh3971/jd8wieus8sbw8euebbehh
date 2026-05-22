import os
import re
import asyncio
import time
import random
from datetime import datetime, timezone, timedelta

from fastapi import FastAPI
from fastapi.responses import JSONResponse
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
    key = re.sub(r'[^\w\s]', '', key)
    key = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', key)
    key = key.strip()
    words = key.split()
    return ' '.join(word.capitalize() for word in words)

# =========================
# GET FIELD NAME (SPELLING & SWAP FIXED)
# =========================

def get_field_name(raw_key):
    name = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', raw_key)
    name = name.strip()
    name = clean_key(name)
    
    mapping = {
        "Email": "Email",
        "Telephone": "Phone",
        "Phone": "Phone",
        "Adres": "Address",        # Fixed Spelling
        "Address": "Address",
        "Document number": "DocumentNumber",
        "Document": "DocumentNumber",
        "Full name": "FatherName",       # Exchanged
        "Fullname": "FatherName",        # Exchanged
        "The name of the father": "FullName", # Exchanged
        "Father name": "FullName",            # Exchanged
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
# MAIN PARSER (CLEAN LIST ONLY)
# =========================

def parse_message(text):
    if not text:
        return []

    # Remove truncation message
    if "Some data did not fit this message" in text:
        text = text.split("Some data did not fit this message")[0]

    lines = text.splitlines()

    # Skip title + description automatically
    data_start_idx = 0

    for i, line in enumerate(lines):
        line = line.strip()
        if re.match(r'^[📩📞🏘️🃏👤👨🗺️]', line):
            data_start_idx = i
            break

    records = []
    current_record = {}

    i = data_start_idx

    while i < len(lines):
        line = lines[i].strip()

        # Empty line = new record
        if not line:
            if current_record:
                records.append(current_record)
                current_record = {}
            i += 1
            continue

        # Stop on truncation note
        if "Some data did not fit this message" in line:
            break

        field_name, value = parse_line(line)

        if field_name and value:
            # Duplicate fields logic (Phone2, Address2 etc)
            if field_name in current_record:
                count = 2
                while f"{field_name}{count}" in current_record:
                    count += 1
                current_record[f"{field_name}{count}"] = value
            else:
                current_record[field_name] = value

        else:
            # Multiline support
            if current_record and line:
                if "Address" in current_record:
                    current_record["Address"] += " " + line
                else:
                    last_key = list(current_record.keys())[-1]
                    current_record[last_key] += " " + line

        i += 1

    # Last record
    if current_record:
        records.append(current_record)

    # Remove empty records
    records = [r for r in records if r]

    # Return clean list directly (No "source1")
    return records

# =========================
# DYNAMIC WATERMARK
# =========================

def get_dynamic_watermark():
    keys = ["developer", "powered_by", "api_author", "system_dev", "licensed_to", "created_by"]
    values = ["@ProPortalx", "API by @ProPortalx", "Dev: @ProPortalx", "ProPortalx"]
    return random.choice(keys), random.choice(values)

# =========================
# MAIN SEARCH
# =========================

@app.post("/search")
async def search(data: Query):
    start_time = time.time()

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

        for i in range(30):
            print(f"\nChecking Messages Attempt {i+1}")
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
                if msg.message.strip() == data.message.strip():
                    continue

                target_message = msg
                print("\nFOUND BOT REPLY")
                print(target_message.message[:200] + "...")
                break

            if target_message:
                break

        if not target_message:
            return JSONResponse(content={
                "status": False,
                "error": "Bot reply timeout",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "response_time": round(time.time() - start_time, 2)
            })

        text = target_message.message

        # Parse Data directly into a flat list
        parsed_records = parse_message(text)
        
        # Inject hidden watermark inside the first record array (Anti-Proxy Layer 2)
        if parsed_records:
            parsed_records[0]["_api_by"] = "@ProPortalx"
        
        # Calculate process time & IST timestamp
        process_time = round(time.time() - start_time, 2)
        ist = timezone(timedelta(hours=5, minutes=30))
        indian_time = datetime.now(ist).strftime("%Y-%m-%dT%H:%M:%S.%f%z")
        indian_time = indian_time[:-2] + ":" + indian_time[-2:]

        # Get Dynamic Keys (Anti-Proxy Layer 1)
        wm_key, wm_value = get_dynamic_watermark()

        # Build Response Content
        content = {
            "status": True,
            "query": data.message,
            "record_count": len(parsed_records),
            "timestamp": indian_time,
            "response_time": process_time,
            "data": parsed_records
        }
        
        # Inject Dynamic Root Watermark
        content[wm_key] = wm_value

        # Return with X-Developed-By Header (Anti-Proxy Layer 3)
        return JSONResponse(
            content=content,
            headers={"X-Developed-By": "@ProPortalx"}
        )

    except Exception as e:
        print("\nERROR:")
        print(str(e))
        return JSONResponse(content={
            "status": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "response_time": round(time.time() - start_time, 2)
        })

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
        "message": "API Running",
        "developer": "@ProPortalx",
        "timestamp": datetime.now(timezone.utc).isoformat()
    }

# =========================
# RUN
# =========================
# uvicorn main:app --host 0.0.0.0 --port $PORT
