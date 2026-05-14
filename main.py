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
    title="Telegram Bot API - Fast Multi-Page Scraper"
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
    
    emoji_pattern = re.compile(r'^([\U00010000-\U0010FFFF\u2600-\u27BF]+)\s*(.+?):\s*(.*)$')
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
        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line)
        if email_match:
            return "Email", email_match.group(1)
    
    return None, None

# =========================
# PARSE SINGLE PAGE (OPTIMIZED)
# =========================

def parse_page_text(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    
    if "Some data did not fit this message" in text:
        text = text.split("Some data did not fit this message")[0]
    
    lines = text.splitlines()
    
    # Find data start quickly
    data_start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and re.match(r'^[\U00010000-\U0010FFFF\u2600-\u27BF]', stripped):
            data_start_idx = i + 1
            break
    
    # Skip description lines
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
                    current_record["Adres"] = current_record["Adres"] + " " + line
                elif len(current_record) > 0:
                    last_key = list(current_record.keys())[-1]
                    current_record[last_key] = current_record[last_key] + " " + line
        
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
        if stripped and re.match(r'^[\U00010000-\U0010FFFF\u2600-\u27BF]', stripped):
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
# CLICK NEXT BUTTON (FAST)
# =========================

async def click_next_button(message) -> Optional[Any]:
    if not message.reply_markup:
        return None
    
    try:
        rows = message.reply_markup.rows
        for row_idx, row in enumerate(rows):
            for col_idx, button in enumerate(row.buttons):
                button_text = button.text
                if button_text == '➡' or button_text == '→' or 'next' in button_text.lower():
                    await message.click(text=button_text)
                    await asyncio.sleep(0.5)  # REDUCED from 3s to 0.5s
                    updated_message = await client.get_messages(
                        BOT_USERNAME,
                        ids=message.id
                    )
                    return updated_message
    except Exception as e:
        print(f"Error clicking next button: {e}")
    
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
                if button.text == '➡' or button.text == '→' or 'next' in button.text.lower():
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
# FAST WAIT FOR INITIAL REPLY
# =========================

async def wait_for_reply(sent_message, timeout=8):
    """Faster reply detection with exponential backoff"""
    start_time = asyncio.get_event_loop().time()
    last_msg_id = sent_message.id
    
    # Check every 0.5 seconds initially, then slower
    delays = [0.5, 0.5, 0.5, 0.5, 0.5, 1, 1, 1, 2, 2]
    
    for delay in delays:
        await asyncio.sleep(delay)
        
        # Get only the last few messages
        messages = await client.get_messages(
            BOT_USERNAME,
            limit=3
        )
        
        for msg in messages:
            if msg.out:
                continue
            if not msg.message:
                continue
            if msg.id <= last_msg_id:
                continue
            if msg.message.strip() == sent_message.message.strip():
                continue
            
            return msg
        
        # Check timeout
        if asyncio.get_event_loop().time() - start_time > timeout:
            break
    
    return None

# =========================
# MAIN SEARCH WITH OPTIMIZED PAGINATION
# =========================

@app.post("/search")
async def search(data: Query):
    try:
        print("\n========== NEW REQUEST ==========")
        print("Query:", data.message)
        
        start_total = asyncio.get_event_loop().time()
        
        # Send initial query
        sent = await client.send_message(
            BOT_USERNAME,
            data.message
        )
        
        print(f"Message Sent, ID: {sent.id}")
        
        # Fast wait for reply
        target_message = await wait_for_reply(sent, timeout=10)
        
        if not target_message:
            return {
                "status": False,
                "error": "Bot reply timeout"
            }
        
        print(f"First reply received in {asyncio.get_event_loop().time() - start_total:.2f}s")
        
        # Collect all records
        all_records = []
        current_message = target_message
        page_num = 1
        source_title = None
        source_description = None
        max_pages = 50
        seen_hashes = set()
        
        while current_message and page_num <= max_pages:
            page_start = asyncio.get_event_loop().time()
            print(f"\n--- Processing Page {page_num} ---")
            
            # Hash for loop detection
            msg_hash = hash(current_message.message[:200])
            if msg_hash in seen_hashes and page_num > 1:
                print("Loop detected. Stopping.")
                break
            seen_hashes.add(msg_hash)
            
            # Get metadata from first page
            if source_title is None:
                source_title, source_description = get_source_metadata(current_message.message)
            
            # Parse records
            page_records = parse_page_text(current_message.message)
            all_records.extend(page_records)
            print(f"Page {page_num}: {len(page_records)} records ({asyncio.get_event_loop().time() - page_start:.2f}s)")
            
            # Get page info
            current_page, total_pages = get_current_page(current_message.message)
            if current_page:
                print(f"Progress: {current_page}/{total_pages}")
            
            # Check for next button
            has_next = await has_next_button(current_message)
            
            if not has_next:
                print("No next button. Done.")
                break
            
            if total_pages and current_page and current_page >= total_pages:
                print(f"Reached last page. Done.")
                break
            
            # Click next (fast)
            click_start = asyncio.get_event_loop().time()
            next_message = await click_next_button(current_message)
            print(f"Page change took {asyncio.get_event_loop().time() - click_start:.2f}s")
            
            if not next_message or next_message.message == current_message.message:
                print("No content change. Stopping.")
                break
            
            current_message = next_message
            page_num += 1
        
        total_time = asyncio.get_event_loop().time() - start_total
        print(f"\n=== COMPLETE: {len(all_records)} records from {page_num} pages in {total_time:.2f}s ===")
        
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
                "total_records": len(all_records),
                "time_seconds": round(total_time, 2)
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
    return await search(Query(message=q))

# =========================
# ROOT
# =========================

@app.get("/")
async def root():
    return {
        "status": True,
        "message": "Fast Multi-Page Telegram Bot Scraper API",
        "optimizations": [
            "Reduced sleep times (2s → 0.5s for page navigation)",
            "Exponential backoff for initial reply",
            "Limit messages fetched to 3 instead of 15",
            "Added timing metrics",
            "Faster parsing"
        ]
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
