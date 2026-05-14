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
    key = re.sub(r'[^a-zA-Z0-9 ]', '', key)
    key = key.strip()
    words = key.split()
    return ''.join(word.capitalize() for word in words)

# =========================
# DETECT SOURCE HEADER
# =========================

def detect_source_header(line):
    """Check if line starts with emoji + name pattern"""
    if not line:
        return False
    # Check for common emojis at start
    emojis = ['💾', '🎲', '🚗', '🧹', '🥻', '🚁', '🎰', '📱', '🛏', '👕', '📞', '🏘️', '👤']
    for emoji in emojis:
        if line.startswith(emoji):
            return True
    return False

# =========================
# PARSE SINGLE SOURCE BLOCK
# =========================

def parse_source_block(lines, start_idx):
    """Parse one source block from starting index"""
    result = {
        "title": "",
        "description": "",
        "records": []
    }
    
    # First line is title
    if start_idx < len(lines):
        result["title"] = lines[start_idx].strip()
    
    current_record = {}
    in_records = False
    description_lines = []
    
    record_start_keys = ["Email", "Phone", "Telephone", "Username", "User", "FullName", "Name"]
    
    i = start_idx + 1
    while i < len(lines):
        line = lines[i].strip()
        
        # Check if this line starts a new source
        if detect_source_header(line):
            break
        
        if not line:
            i += 1
            continue
        
        # Check for key:value pattern
        if ":" in line:
            parts = line.split(":", 1)
            key = clean_key(parts[0])
            value = parts[1].strip()
            
            if not value:
                i += 1
                continue
            
            # Check if this starts a new record
            if key in record_start_keys and current_record:
                result["records"].append(current_record)
                current_record = {}
                in_records = True
            
            in_records = True
            
            # Handle duplicate keys
            if key in current_record:
                count = 2
                while f"{key}{count}" in current_record:
                    count += 1
                current_record[f"{key}{count}"] = value
            else:
                current_record[key] = value
        else:
            # Non key:value - could be description or multiline value
            if not in_records:
                description_lines.append(line)
            else:
                # Append to last field if it makes sense
                if current_record:
                    last_key = list(current_record.keys())[-1]
                    current_record[last_key] = current_record[last_key] + " " + line
        
        i += 1
    
    # Add last record
    if current_record:
        result["records"].append(current_record)
    
    result["description"] = " ".join(description_lines).strip()
    
    return result, i

# =========================
# ADVANCED GROUPED PARSER
# =========================

def parse_message(text):
    """Parse message into grouped sources"""
    result = {}
    
    if not text:
        return result
    
    lines = text.splitlines()
    i = 0
    
    source_counter = 1
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            i += 1
            continue
        
        # Check if line is a source header
        if detect_source_header(line):
            source_data, next_i = parse_source_block(lines, i)
            if source_data and source_data.get("records"):
                result[f"source{source_counter}"] = source_data
                source_counter += 1
            i = next_i
        else:
            i += 1
    
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
        # PARSE - GROUPED BY SOURCE
        # =====================
        
        parsed = parse_message(text)
        
        # =====================
        # RESPONSE
        # =====================
        
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
