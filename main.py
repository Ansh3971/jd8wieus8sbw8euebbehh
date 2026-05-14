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
    # Remove emojis and special chars, keep letters and spaces
    key = re.sub(r'[^\w\s]', '', key)
    key = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', key)
    key = key.strip()
    words = key.split()
    return ' '.join(word.capitalize() for word in words)

# =========================
# EXTRACT EMOJI NAME
# =========================

def get_field_name(raw_key):
    """Convert 📩Email -> Email, 👤Full name -> FullName, etc."""
    # Remove emojis
    name = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', raw_key)
    name = name.strip()
    name = clean_key(name)
    
    # Map common variations
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
# PARSE RECORD BLOCK
# =========================

def parse_record_block(lines, start_idx):
    """Parse one complete record starting at start_idx"""
    record = {}
    i = start_idx
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Stop if we hit a blank line followed by another Telephone (start of new record)
        if i > start_idx and line.startswith('📞') and not record:
            break
        
        # Check for key:value pattern with emoji
        emoji_pattern = re.compile(r'^([\U00010000-\U0010FFFF\u2600-\u27BF]+)\s*(.+?):\s*(.*)$')
        match = emoji_pattern.match(line)
        
        if match:
            emoji = match.group(1)
            key_raw = match.group(2)
            value = match.group(3).strip()
            
            if value:
                field_name = get_field_name(key_raw)
                
                # Handle duplicate fields
                if field_name in record:
                    count = 2
                    while f"{field_name}{count}" in record:
                        count += 1
                    record[f"{field_name}{count}"] = value
                else:
                    record[field_name] = value
            i += 1
        else:
            # Check if line starts with telephone without colon format
            if line.startswith('📞'):
                # Extract number after emoji
                phone_match = re.match(r'📞+\s*(\d+)', line)
                if phone_match:
                    phone = phone_match.group(1)
                    if "Phone" in record:
                        count = 2
                        while f"Phone{count}" in record:
                            count += 1
                        record[f"Phone{count}"] = phone
                    else:
                        record["Phone"] = phone
                i += 1
            else:
                # Maybe multiline value for last field
                if record and line:
                    last_key = list(record.keys())[-1]
                    record[last_key] = record[last_key] + " " + line
                i += 1
    
    return record, i

# =========================
# MAIN PARSER
# =========================

def parse_message(text):
    """Parse bot reply into source with records"""
    
    if not text:
        return {}
    
    # Check if message contains "Some data did not fit this message"
    truncation_note = "Some data did not fit this message"
    if truncation_note in text:
        text = text.split(truncation_note)[0]
    
    lines = text.splitlines()
    
    result = {}
    
    # Find source header (first line with emoji like 💾)
    source_title = None
    source_description_lines = []
    start_line = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and re.match(r'^[\U00010000-\U0010FFFF\u2600-\u27BF]', stripped):
            # This could be source title
            if not source_title:
                source_title = stripped
                start_line = i + 1
                break
    
    if not source_title:
        # No source header found, treat whole text as source1
        source_title = "Data Source"
        start_line = 0
    
    # Extract description (lines after title until first data line)
    description_lines = []
    data_start = start_line
    
    for i in range(start_line, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        # If line starts with data emoji, description ends
        if re.match(r'^[📩📞🏘️🃏👤👨🗺️]', line):
            data_start = i
            break
        description_lines.append(line)
    
    description = " ".join(description_lines).strip()
    
    # Parse records
    records = []
    i = data_start
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Look for start of a record (Telephone or Email)
        if line.startswith('📞') or line.startswith('📩'):
            record, next_i = parse_record_block(lines, i)
            if record:
                records.append(record)
            i = next_i
        else:
            i += 1
    
    # Build final result
    result["source1"] = {
        "title": source_title,
        "description": description,
        "records": records
    }
    
    return result

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
            return {
                "status": False,
                "error": "Bot reply timeout"
            }
        
        text = target_message.message
        parsed = parse_message(text)
        
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
