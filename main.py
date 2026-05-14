import os
import re
import asyncio
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional

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

# Stats tracking (simple in-memory for demo)
KEY = os.getenv("API_KEY", "9a3ec87b4897728aa4f00d0325ed353f")
LABEL = os.getenv("KEY_LABEL", "maze_kroo")
TOTAL_LIMIT = int(os.getenv("TOTAL_LIMIT", 1000))
DAILY_LIMIT = int(os.getenv("DAILY_LIMIT", 50))
DEVELOPER = os.getenv("DEVELOPER", "@Cyb3rB4nn3r")

# In-memory usage tracking (replace with Redis/DB in production)
usage_stats = {
    "total_used": 0,
    "today_used": 0,
    "last_reset_date": datetime.now().date().isoformat()
}

# =========================
# FASTAPI
# =========================

app = FastAPI(
    title="Telegram Bot API - Multi-Source Aggregator"
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

def clean_key(key: str) -> str:
    key = re.sub(r'[^a-zA-Z0-9 ]', '', key)
    key = key.strip()
    words = key.split()
    return ''.join(word.capitalize() for word in words)

# =========================
# DETECT SOURCE HEADER
# =========================

# Pattern for source headers: emoji + name (e.g., "💾HiTeckGroop.in", "🎲1Win")
SOURCE_HEADER_PATTERN = re.compile(r'^([\U00010000-\U0010FFFF\u2600-\u27BF\u2B50\u1F300-\u1F6FF\u1F900-\u1F9FF])([A-Za-z0-9\.\s]+)$')

def detect_source_header(line: str) -> Optional[tuple]:
    """Return (emoji, title) if line is a source header, else None"""
    if not line:
        return None
    
    # Common source indicators
    if any(emoji in line[:5] for emoji in ['💾', '🎲', '🚗', '🧹', '🥻', '🚁', '🎰', '📱', '🛏', '👕', '📞', '🏘️', '👤']):
        # Try to extract emoji and title
        emoji_match = re.match(r'^([^\w\s]+)', line)
        if emoji_match:
            emoji = emoji_match.group(1)
            title = line[len(emoji):].strip()
            if title:
                return (emoji, title)
    return None

# =========================
# PARSE SINGLE SOURCE
# =========================

def parse_source_block(block_text: str) -> Dict[str, Any]:
    """Parse one source block into {title, description, records}"""
    lines = block_text.strip().splitlines()
    
    if not lines:
        return None
    
    # First line is title (with emoji)
    first_line = lines[0].strip()
    header = detect_source_header(first_line)
    if header:
        emoji, title = header
        title = f"{emoji}{title}"
    else:
        title = first_line
    
    # Find description (lines until first record starts)
    description_lines = []
    records = []
    current_record = {}
    in_records = False
    
    # Record start indicators
    record_keys = ["Email", "Phone", "Telephone", "Username", "User", "FullName", "Name", "Adres", "Address"]
    
    for i in range(1, len(lines)):
        line = lines[i].strip()
        if not line:
            continue
        
        # Check if line has key:value format
        if ":" in line:
            parts = line.split(":", 1)
            key_raw = parts[0].strip()
            value = parts[1].strip() if len(parts) > 1 else ""
            
            key = clean_key(key_raw)
            
            # If we hit a record-start key and have existing record, save it
            if any(rk.lower() in key.lower() for rk in record_keys) and current_record and not in_records:
                records.append(current_record)
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
            # Non key:value line
            if not in_records and not any(rk.lower() in line.lower() for rk in record_keys):
                # Part of description
                description_lines.append(line)
            else:
                # Could be part of record (like address lines without colon)
                if current_record and "Adres" in current_record:
                    current_record["Adres"] = current_record["Adres"] + " " + line
                elif current_record:
                    current_record["_extra"] = current_record.get("_extra", "") + " " + line
    
    # Add last record
    if current_record:
        records.append(current_record)
    
    description = " ".join(description_lines).strip() if description_lines else "No description"
    
    return {
        "title": title,
        "description": description,
        "records": records
    }

# =========================
# SPLIT TEXT INTO SOURCES
# =========================

def split_into_sources(full_text: str) -> List[str]:
    """Split full bot response into source blocks based on emoji headers"""
    if not full_text:
        return []
    
    lines = full_text.splitlines()
    source_blocks = []
    current_block_lines = []
    
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        
        # Check if this line is a new source header
        if detect_source_header(stripped):
            # Save previous block if exists
            if current_block_lines:
                source_blocks.append("\n".join(current_block_lines))
                current_block_lines = []
            current_block_lines.append(stripped)
        else:
            current_block_lines.append(stripped)
    
    # Add last block
    if current_block_lines:
        source_blocks.append("\n".join(current_block_lines))
    
    return source_blocks

# =========================
# UPDATE USAGE STATS
# =========================

def update_usage_stats() -> Dict[str, Any]:
    global usage_stats
    
    today = datetime.now().date().isoformat()
    
    # Reset daily counter if new day
    if usage_stats["last_reset_date"] != today:
        usage_stats["today_used"] = 0
        usage_stats["last_reset_date"] = today
    
    usage_stats["total_used"] += 1
    usage_stats["today_used"] += 1
    
    expires_at = datetime.now() + timedelta(days=12.45)  # Example expiry
    hours_remaining = 12.45 * 24
    
    return {
        "key": KEY,
        "label": LABEL,
        "total_used": usage_stats["total_used"],
        "total_limit": TOTAL_LIMIT,
        "requests_remaining": TOTAL_LIMIT - usage_stats["total_used"],
        "used_today": usage_stats["today_used"],
        "daily_limit": DAILY_LIMIT,
        "daily_remaining": DAILY_LIMIT - usage_stats["today_used"],
        "expires_at": expires_at.strftime("%Y-%m-%d %H:%M:%S UTC"),
        "days_remaining": 12.45,
        "hours_remaining": hours_remaining
    }

# =========================
# MAIN SEARCH
# =========================

@app.post("/search")
async def search(data: Query) -> Dict[str, Any]:
    try:
        print("\n========== NEW REQUEST ==========")
        print("Query:", data.message)
        
        # Update usage stats
        stats = update_usage_stats()
        
        # Check limits
        if stats["total_used"] > TOTAL_LIMIT:
            return {
                "status": False,
                "error": "Total request limit exceeded"
            }
        
        if stats["daily_used"] > DAILY_LIMIT:
            return {
                "status": False,
                "error": "Daily request limit exceeded"
            }
        
        # =====================
        # SEND MESSAGE TO BOT
        # =====================
        
        sent = await client.send_message(
            BOT_USERNAME,
            data.message
        )
        
        print("Message Sent, ID:", sent.id)
        
        # =====================
        # WAIT FOR BOT REPLY
        # =====================
        
        target_message = None
        
        for i in range(30):
            print(f"Checking Messages Attempt {i+1}")
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
                print(msg.message[:200] + "...")
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
        # PARSE MULTI-SOURCE
        # =====================
        
        full_text = target_message.message
        
        # Split into source blocks
        source_blocks = split_into_sources(full_text)
        
        sources = {}
        source_index = 1
        
        for block in source_blocks:
            parsed_source = parse_source_block(block)
            if parsed_source and parsed_source.get("records"):
                sources[f"source{source_index}"] = parsed_source
                source_index += 1
        
        # =====================
        # BUILD FINAL RESPONSE
        # =====================
        
        response = {
            "status": True,
            "query": data.message,
            "data": sources,
            "key_stats": stats,
            "developer": DEVELOPER,
            "timestamp": datetime.now().isoformat() + "Z"
        }
        
        return response
        
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
        "message": "Multi-Source Telegram Bot API Running",
        "developer": DEVELOPER
    }

# =========================
# RUN
# =========================
# uvicorn main:app --host 0.0.0.0 --port 8000 --reload
