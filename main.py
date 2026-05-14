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
# PARSE SINGLE PAGE
# =========================

def parse_page_text(text: str) -> List[Dict[str, Any]]:
    if not text:
        return []
    
    if "Some data did not fit this message" in text:
        text = text.split("Some data did not fit this message")[0]
    
    lines = text.splitlines()
    
    data_start_idx = 0
    source_title = None
    
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and re.match(r'^[\U00010000-\U0010FFFF\u2600-\u27BF]', stripped):
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
# GET CURRENT PAGE NUMBER
# =========================

def get_current_page(text: str):
    match = re.search(r'(\d+)/(\d+)', text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

# =========================
# CLICK NEXT BUTTON
# =========================

async def click_next_button(message):
    if not message.reply_markup:
        return None
    
    try:
        rows = message.reply_markup.rows
        for row in rows:
            for button in row.buttons:
                button_text = button.text
                if button_text == '➡' or button_text == '→' or 'next' in button_text.lower():
                    print(f"Clicking: {button_text}")
                    await message.click(text=button_text)
                    await asyncio.sleep(2)
                    updated = await client.get_messages(BOT_USERNAME, ids=message.id)
                    return updated
    except Exception as e:
        print(f"Error: {e}")
    return None

# =========================
# WAIT FOR INITIAL REPLY
# =========================

async def wait_for_reply(sent_message, timeout=30):
    sent_id = sent_message.id
    start = asyncio.get_event_loop().time()
    
    while asyncio.get_event_loop().time() - start < timeout:
        await asyncio.sleep(1)
        messages = await client.get_messages(BOT_USERNAME, limit=10)
        for msg in messages:
            if msg.out:
                continue
            if not msg.message:
                continue
            if msg.id <= sent_id:
                continue
            if msg.message.strip() == sent_message.message.strip():
                continue
            if len(msg.message) > 50 or re.search(r'[📩📞🏘️]', msg.message):
                return msg
    return None

# =========================
# MAIN SEARCH
# =========================

@app.post("/search")
async def search(data: Query):
    try:
        print("\n" + "="*50)
        print("NEW SEARCH")
        print("="*50)
        print(f"Query: {data.message}")
        
        start_time = asyncio.get_event_loop().time()
        
        # Send query
        sent = await client.send_message(BOT_USERNAME, data.message)
        print(f"Sent ID: {sent.id}")
        
        # Wait for reply
        current = await wait_for_reply(sent)
        if not current:
            return {"status": False, "error": "No reply received"}
        
        print(f"First reply in {asyncio.get_event_loop().time() - start_time:.2f}s")
        
        # Collect all records
        all_records = []
        page_num = 1
        source_title = None
        source_description = None
        max_pages = 50
        
        # Store previous page number to detect loop
        previous_page = None
        
        while current and page_num <= max_pages:
            print(f"\n--- Page {page_num} ---")
            
            # Get metadata
            if source_title is None:
                source_title, source_description = get_source_metadata(current.message)
                print(f"Source: {source_title}")
            
            # Parse records
            records = parse_page_text(current.message)
            print(f"Records: {len(records)}")
            all_records.extend(records)
            
            # Get current page numbers
            current_page, total_pages = get_current_page(current.message)
            
            if current_page and total_pages:
                print(f"Page: {current_page}/{total_pages}")
                
                # ✅ CRITICAL: If we're on the last page, break out of loop
                if current_page >= total_pages:
                    print(f"✓ REACHED LAST PAGE ({current_page}/{total_pages}) - STOPPING")
                    break
            
            # Check if we're stuck on same page
            if previous_page is not None and current_page == previous_page:
                print(f"⚠ Page not advancing ({current_page} -> {current_page}) - STOPPING")
                break
            
            previous_page = current_page
            
            # Try to click next button
            print("Clicking next...")
            next_msg = await click_next_button(current)
            
            if not next_msg:
                print("No next button found - STOPPING")
                break
            
            # Check if content changed
            if next_msg.message == current.message:
                print("Content didn't change - STOPPING")
                break
            
            # Update for next iteration
            current = next_msg
            page_num += 1
        
        # FALLBACK: If we didn't break properly but have page numbers, double-check
        final_page, final_total = get_current_page(current.message) if current else (None, None)
        if final_page and final_total and final_page >= final_total:
            print(f"✓ Last page confirmed: {final_page}/{final_total}")
        
        total_time = asyncio.get_event_loop().time() - start_time
        print(f"\n{'='*50}")
        print(f"COMPLETE: {len(all_records)} records from {page_num} pages in {total_time:.2f}s")
        print(f"{'='*50}")
        
        # Build response
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
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        return {"status": False, "error": str(e)}

# =========================
# TEST
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))

@app.get("/")
async def root():
    return {"status": True, "message": "Multi-Page Scraper API"}

# =========================
# RUN
# =========================
# uvicorn main:app --host 0.0.0.0 --port $PORT
