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
# CLICK NEXT BUTTON - DUAL DETECTION
# =========================

async def click_next_button(message, current_page_num, timeout=5):
    """Click next button and return updated message (either edited same ID or new message)"""
    if not message.reply_markup:
        print("No reply_markup on message")
        return None
    
    next_button_info = await find_next_button(message)
    if not next_button_info:
        print("Next button not found")
        return None
    
    button, row_idx, col_idx = next_button_info
    button_text = button.text
    print(f"Clicking next button: '{button_text}'")
    
    # Store current page number for comparison
    old_page, total_pages = get_page_numbers(message.message)
    print(f"Current page: {old_page}/{total_pages}")
    
    # Click the button
    await message.click(text=button_text)
    
    # Wait for bot to respond (increase to 1.5 seconds)
    await asyncio.sleep(1.5)
    
    # FIRST CHECK: Did the original message get edited?
    try:
        edited_message = await client.get_messages(BOT_USERNAME, ids=message.id)
        if edited_message and edited_message.message != message.message:
            print("Message was edited (same ID)")
            new_page, _ = get_page_numbers(edited_message.message)
            print(f"New page after edit: {new_page}/{total_pages}")
            return edited_message
    except Exception as e:
        print(f"Error checking edited message: {e}")
    
    # SECOND CHECK: Did the bot send a new message?
    try:
        # Get messages after the click
        messages = await client.get_messages(BOT_USERNAME, limit=5)
        for msg in messages:
            if msg.out:
                continue
            if not msg.message:
                continue
            if msg.id <= message.id:
                continue
            
            # Check if this message contains data for same query
            has_data_emojis = re.search(r'[📩📞🏘️🃏👤👨🗺️💾🎲🚗]', msg.message)
            if has_data_emojis or len(msg.message) > 200:
                print(f"Found new message (ID: {msg.id})")
                new_page, _ = get_page_numbers(msg.message)
                print(f"New page: {new_page}/{total_pages}")
                return msg
    except Exception as e:
        print(f"Error checking new messages: {e}")
    
    # THIRD CHECK: Wait longer and try again for edit
    await asyncio.sleep(2)
    try:
        edited_message = await client.get_messages(BOT_USERNAME, ids=message.id)
        if edited_message and edited_message.message != message.message:
            print("Message was edited after longer wait")
            return edited_message
    except:
        pass
    
    print("No updated message found")
    return None

# =========================
# CHECK FOR NEXT BUTTON
# =========================

async def has_next_button(message) -> bool:
    next_button = await find_next_button(message)
    return next_button is not None

# =========================
# WAIT FOR REPLY
# =========================

async def wait_for_reply(sent_message, query_text, timeout=15):
    """Wait for bot reply to our query"""
    start_time = asyncio.get_event_loop().time()
    sent_id = sent_message.id
    sent_text = sent_message.message.strip()
    
    print(f"Waiting for reply to message ID: {sent_id}")
    
    while asyncio.get_event_loop().time() - start_time < timeout:
        await asyncio.sleep(1)
        
        messages = await client.get_messages(BOT_USERNAME, limit=10)
        
        for msg in messages:
            if msg.out:
                continue
            if not msg.message:
                continue
            if msg.id <= sent_id:
                continue
            if msg.message.strip() == sent_text:
                continue
            
            # Check if this is a valid data reply
            has_data_emojis = re.search(r'[📩📞🏘️🃏👤👨🗺️💾🎲🚗🧹🥻🚁🎰📱🛏]', msg.message)
            has_phone = re.search(r'91\d{10}', msg.message)
            
            if has_data_emojis or has_phone or len(msg.message) > 200:
                print(f"Found valid reply message ID: {msg.id}")
                return msg
        
        # Check if sent message was edited
        try:
            current_sent = await client.get_messages(BOT_USERNAME, ids=sent_id)
            if current_sent and current_sent.message != sent_text:
                if len(current_sent.message) > 100:
                    print(f"Sent message was edited with reply (ID: {sent_id})")
                    return current_sent
        except:
            pass
    
    return None

# =========================
# MAIN SEARCH
# =========================

@app.post("/search")
async def search(data: Query):
    try:
        print("\n" + "="*50)
        print("NEW SEARCH REQUEST")
        print("="*50)
        print(f"Query: {data.message}")
        
        start_total = asyncio.get_event_loop().time()
        
        # Send initial query
        sent = await client.send_message(BOT_USERNAME, data.message)
        print(f"Sent message ID: {sent.id}")
        
        # Wait for first reply
        target_message = await wait_for_reply(sent, data.message, timeout=15)
        
        if not target_message:
            return {"status": False, "error": "Bot reply timeout"}
        
        print(f"First reply received in {asyncio.get_event_loop().time() - start_total:.2f}s")
        
        # Collect all records
        all_records = []
        current_message = target_message
        page_num = 1
        source_title = None
        source_description = None
        max_pages = 50
        seen_page_numbers = set()  # Track page numbers we've seen
        max_retries_per_page = 2
        
        while current_message and page_num <= max_pages:
            print(f"\n--- Processing Page {page_num} ---")
            
            # Get metadata from first page
            if source_title is None:
                source_title, source_description = get_source_metadata(current_message.message)
                print(f"Source: {source_title}")
            
            # Parse records
            page_records = parse_page_text(current_message.message)
            print(f"Found {len(page_records)} records on this page")
            all_records.extend(page_records)
            
            # Get page numbers
            current_page, total_pages = get_page_numbers(current_message.message)
            if current_page and total_pages:
                print(f"Page {current_page}/{total_pages}")
                seen_page_numbers.add(current_page)
            else:
                print("No page indicator found")
            
            # Check for next button
            has_next = await has_next_button(current_message)
            
            if not has_next:
                print("No next button found - scraping complete")
                break
            
            # If we know total pages and we've reached it
            if total_pages and current_page and current_page >= total_pages:
                print(f"Reached last page ({current_page}/{total_pages})")
                break
            
            # Click next button with retry
            retry_count = 0
            next_message = None
            
            while retry_count < max_retries_per_page and not next_message:
                print(f"Clicking next button (attempt {retry_count + 1})...")
                next_message = await click_next_button(current_message, current_page)
                
                if not next_message:
                    print(f"Failed to get next page, retrying...")
                    retry_count += 1
                    await asyncio.sleep(1)
            
            if not next_message:
                print("Could not fetch next page after retries - stopping")
                break
            
            # Verify we actually moved to a new page
            new_page, _ = get_page_numbers(next_message.message)
            old_page, _ = get_page_numbers(current_message.message)
            
            if new_page and old_page and new_page <= old_page:
                print(f"WARNING: Page didn't advance ({old_page} -> {new_page})")
                # Try one more time with longer wait
                await asyncio.sleep(2)
                next_message = await click_next_button(current_message, current_page)
                if next_message:
                    new_page, _ = get_page_numbers(next_message.message)
                    if new_page and new_page <= old_page:
                        print("Page still not advancing - stopping")
                        break
            elif new_page:
                print(f"Advanced to page {new_page}")
            
            current_message = next_message
            page_num += 1
        
        total_time = asyncio.get_event_loop().time() - start_total
        print(f"\n{'='*50}")
        print(f"COMPLETE: {len(all_records)} records from {page_num} pages")
        print(f"Time taken: {total_time:.2f} seconds")
        print(f"{'='*50}")
        
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
        "message": "Reliable Multi-Page Telegram Bot Scraper API - Fixed Pagination"
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
