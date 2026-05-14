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
    title="Telegram Bot API - Reliable Multi-Page Scraper"
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
    
    # Find data start
    data_start_idx = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped and re.match(r'^[\U00010000-\U0010FFFF\u2600-\u27BF]', stripped):
            data_start_idx = i + 1
            break
    
    # Skip description
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
# GET PAGE NUMBERS
# =========================

def get_page_numbers(text: str) -> tuple:
    patterns = [
        r'(\d+)\s*/\s*(\d+)',
        r'Page\s*(\d+)\s*/\s*(\d+)',
        r'(\d+)\s*of\s*(\d+)',
        r'ページ\s*(\d+)\s*/\s*(\d+)',
        r'(\d+)\s*-\s*(\d+)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return int(match.group(1)), int(match.group(2))
    
    return None, None

# =========================
# FIND NEXT BUTTON
# =========================

async def find_next_button(message):
    if not message.reply_markup:
        return None
    
    next_texts = ['➡', '→', '›', '»', 'Next', 'next', 'NEXT', '>', '>>']
    
    try:
        rows = message.reply_markup.rows
        for row_idx, row in enumerate(rows):
            for col_idx, button in enumerate(row.buttons):
                button_text = button.text.strip()
                for next_text in next_texts:
                    if next_text in button_text or button_text == next_text:
                        return button, row_idx, col_idx
    except Exception as e:
        print(f"Error finding next button: {e}")
    
    return None

# =========================
# CLICK NEXT BUTTON
# =========================

async def click_next_button(message, retries=3):
    if not message.reply_markup:
        print("No reply_markup on message")
        return None
    
    for attempt in range(retries):
        try:
            next_button_info = await find_next_button(message)
            if not next_button_info:
                print(f"Next button not found (attempt {attempt + 1})")
                await asyncio.sleep(0.3)
                continue
            
            button, row_idx, col_idx = next_button_info
            button_text = button.text
            print(f"Found next button: '{button_text}'")
            
            old_content = message.message
            
            await message.click(text=button_text)
            await asyncio.sleep(0.8)
            
            updated_message = await client.get_messages(
                BOT_USERNAME,
                ids=message.id
            )
            
            if updated_message and updated_message.message != old_content:
                print(f"Page changed successfully")
                return updated_message
            else:
                print(f"Content didn't change (attempt {attempt + 1})")
                await asyncio.sleep(0.5)
                
        except Exception as e:
            print(f"Error clicking next button (attempt {attempt + 1}): {e}")
            await asyncio.sleep(0.5)
    
    return None

# =========================
# CHECK FOR NEXT BUTTON
# =========================

async def has_next_button(message) -> bool:
    next_button = await find_next_button(message)
    return next_button is not None

# =========================
# WAIT FOR REPLY - FIXED TO GET CORRECT MESSAGE
# =========================

async def wait_for_reply(sent_message, query_text, timeout=15):
    """Wait for bot reply - only return message that is a response to our query"""
    start_time = asyncio.get_event_loop().time()
    sent_id = sent_message.id
    sent_text = sent_message.message.strip()
    
    print(f"Waiting for reply to message ID: {sent_id}")
    print(f"Query text: {sent_text}")
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        await asyncio.sleep(0.8)
        
        # Get recent messages
        messages = await client.get_messages(
            BOT_USERNAME,
            limit=10
        )
        
        for msg in messages:
            # Skip our own messages
            if msg.out:
                continue
            
            # Skip empty messages
            if not msg.message:
                continue
            
            # Must be newer than our sent message
            if msg.id <= sent_id:
                continue
            
            # Skip if it's just repeating our query
            if msg.message.strip() == sent_text:
                continue
            
            # Check if this message contains data (has emojis or is long)
            has_data_emojis = re.search(r'[📩📞🏘️🃏👤👨🗺️💾🎲🚗🧹🥻🚁🎰📱🛏]', msg.message)
            is_long = len(msg.message) > 100
            
            if has_data_emojis or is_long:
                print(f"Found valid reply message ID: {msg.id}")
                print(f"Reply preview: {msg.message[:150]}...")
                return msg
        
        # Also check if the sent message itself was edited (bot might edit it directly)
        try:
            current_sent = await client.get_messages(BOT_USERNAME, ids=sent_id)
            if current_sent and current_sent.message != sent_text:
                if len(current_sent.message) > 100:
                    print(f"Sent message was edited with reply data (ID: {sent_id})")
                    return current_sent
        except:
            pass
    
    print("Timeout waiting for reply")
    return None

# =========================
# MAIN SEARCH WITH RELIABLE MESSAGE SELECTION
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
        
        # Wait for correct reply
        target_message = await wait_for_reply(sent, data.message, timeout=15)
        
        if not target_message:
            return {
                "status": False,
                "error": "Bot reply timeout - no valid response received"
            }
        
        print(f"First reply received in {asyncio.get_event_loop().time() - start_total:.2f}s")
        
        # Collect all records
        all_records = []
        current_message = target_message
        page_num = 1
        source_title = None
        source_description = None
        max_pages = 50
        previous_contents = set()
        stuck_count = 0
        max_stuck = 3
        
        while current_message and page_num <= max_pages:
            page_start = asyncio.get_event_loop().time()
            print(f"\n--- Processing Page {page_num} ---")
            
            # Check for content loop
            content_hash = hash(current_message.message[:500])
            if content_hash in previous_contents and page_num > 1:
                print("Content loop detected - same page content repeated")
                break
            previous_contents.add(content_hash)
            
            # Get metadata from first page
            if source_title is None:
                source_title, source_description = get_source_metadata(current_message.message)
            
            # Parse records
            page_records = parse_page_text(current_message.message)
            new_records_count = len(page_records)
            all_records.extend(page_records)
            
            # Get page numbers
            current_page, total_pages = get_page_numbers(current_message.message)
            
            if current_page and total_pages:
                print(f"Page {current_page}/{total_pages} - {new_records_count} records ({asyncio.get_event_loop().time() - page_start:.2f}s)")
            else:
                print(f"Page {page_num} - {new_records_count} records ({asyncio.get_event_loop().time() - page_start:.2f}s)")
            
            # Check if we should stop
            has_next = await has_next_button(current_message)
            
            if not has_next:
                print("No next button found. Scraping complete.")
                break
            
            # Stop if we've reached total pages
            if total_pages and current_page and current_page >= total_pages:
                print(f"Reached last page ({current_page}/{total_pages}). Complete.")
                break
            
            # Click next button
            print("Clicking next button...")
            next_message = await click_next_button(current_message)
            
            if not next_message:
                print("Failed to get next page")
                stuck_count += 1
                if stuck_count >= max_stuck:
                    print("Max retries reached. Stopping.")
                    break
                continue
            else:
                stuck_count = 0
            
            # Verify page actually changed
            if next_message.message == current_message.message:
                print("Message content unchanged after click. May be last page.")
                new_page, _ = get_page_numbers(next_message.message)
                old_page, _ = get_page_numbers(current_message.message)
                if new_page and old_page and new_page == old_page:
                    print("Page number didn't change. Stopping.")
                    break
                elif not new_page:
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
        "message": "Reliable Multi-Page Telegram Bot Scraper API",
        "features": [
            "Correct message selection based on sent message ID",
            "Only returns messages newer than user query",
            "Filters out echo/repeat messages",
            "Checks for data emojis to validate bot reply",
            "Also checks if sent message was edited by bot"
        ]
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
