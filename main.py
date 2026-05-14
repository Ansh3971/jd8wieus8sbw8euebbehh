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
# CHECK IF NEW RECORD STARTS
# =========================

def is_new_record_start(line, current_record):
    """Check if line indicates start of a new record"""
    if not line:
        return False
    
    # If we have a complete record (has FullName or FatherName or Email) and see new Telephone
    if current_record and (line.startswith('📞') or line.startswith('📩')):
        # Check if this line likely starts fresh entry
        return True
    
    return False

# =========================
# PARSE RECORDS PROPERLY
# =========================

def parse_records(lines, start_idx):
    """Parse all records sequentially, splitting at proper boundaries"""
    records = []
    current_record = {}
    i = start_idx
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            # Blank line - could be record separator
            if current_record:
                records.append(current_record)
                current_record = {}
            i += 1
            continue
        
        # Check for truncation note
        if "Some data did not fit this message" in line:
            break
        
        # Check if this line starts a new record
        if is_new_record_start(line, current_record):
            # Save current record if exists
            if current_record:
                records.append(current_record)
                current_record = {}
        
        # Parse key:value with emoji
        emoji_pattern = re.compile(r'^([\U00010000-\U0010FFFF\u2600-\u27BF]+)\s*(.+?):\s*(.*)$')
        match = emoji_pattern.match(line)
        
        if match:
            emoji = match.group(1)
            key_raw = match.group(2)
            value = match.group(3).strip()
            
            if value:
                field_name = get_field_name(key_raw)
                
                # Handle duplicate fields within same record
                if field_name in current_record:
                    count = 2
                    while f"{field_name}{count}" in current_record:
                        count += 1
                    current_record[f"{field_name}{count}"] = value
                else:
                    current_record[field_name] = value
            i += 1
        else:
            # Handle telephone without colon format
            if line.startswith('📞'):
                phone_match = re.match(r'📞+\s*(\d+)', line)
                if phone_match:
                    phone = phone_match.group(1)
                    if "Phone" in current_record:
                        count = 2
                        while f"Phone{count}" in current_record:
                            count += 1
                        current_record[f"Phone{count}"] = phone
                    else:
                        current_record["Phone"] = phone
                i += 1
            elif line.startswith('📩'):
                email_match = re.match(r'📩+\s*Email:\s*(.+?)$', line, re.IGNORECASE)
                if not email_match:
                    email_match = re.match(r'📩+\s*(.+?)$', line)
                if email_match:
                    email = email_match.group(1).strip()
                    if "Email" in current_record:
                        count = 2
                        while f"Email{count}" in current_record:
                            count += 1
                        current_record[f"Email{count}"] = email
                    else:
                        current_record["Email"] = email
                i += 1
            else:
                # Multiline continuation
                if current_record and line:
                    last_key = list(current_record.keys())[-1]
                    current_record[last_key] = current_record[last_key] + " " + line
                i += 1
    
    # Append last record
    if current_record:
        records.append(current_record)
    
    return records

# =========================
# MAIN PARSER
# =========================

def parse_message(text):
    if not text:
        return {}
    
    # Remove truncation note
    if "Some data did not fit this message" in text:
        text = text.split("Some data did not fit this message")[0]
    
    lines = text.splitlines()
    
    result = {}
    
    # Find source header
    source_title = None
    source_description = ""
    data_start = 0
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and re.match(r'^[\U00010000-\U0010FFFF\u2600-\u27BF]', stripped):
            if not source_title:
                source_title = stripped
                data_start = i + 1
                break
    
    if not source_title:
        source_title = "Data Source"
        data_start = 0
    
    # Extract description (lines before first data emoji)
    description_lines = []
    for i in range(data_start, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        if re.match(r'^[📩📞🏘️🃏👤👨🗺️]', line):
            data_start = i
            break
        description_lines.append(line)
    
    source_description = " ".join(description_lines).strip()
    
    # Parse records with proper separation
    records = parse_records(lines, data_start)
    
    result["source1"] = {
        "title": source_title,
        "description": source_description,
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
