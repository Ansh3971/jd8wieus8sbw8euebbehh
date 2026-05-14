import os
import re
import asyncio
from typing import Optional, List, Dict, Any, Tuple

from fastapi import FastAPI
from pydantic import BaseModel

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.types import Message

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

def get_source_metadata(text: str) -> Tuple[str, str]:
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
# WAIT FOR FINAL MESSAGE - FIXED
# =========================

async def wait_for_final_message(sent_message: Message, timeout: int = 15) -> Optional[Message]:
    """Wait for bot's FINAL edited message, not the intermediate one"""
    sent_id = sent_message.id
    seen_messages: List[Tuple[int, str]] = []  # List of (message_id, content)
    
    for attempt in range(15):  # 15 attempts
        await asyncio.sleep(0.8)
        
        # Get messages after sent
        messages = await client.get_messages(BOT_USERNAME, limit=10)
        
        # Look for messages from bot after our sent message
        for msg in messages:
            if msg.out:
                continue
            if not msg.message:
                continue
            if msg.id <= sent_id:
                continue
            if msg.message.strip() == sent_message.message.strip():
                continue
            
            # Check if this is data message (has emojis or phone numbers)
            if re.search(r'[📩📞🏘️🃏👤👨🗺️💾]', msg.message) or len(msg.message) > 200:
                current_content = msg.message
                msg_id = msg.id
                
                # Track seen messages (keep only last 3)
                seen_messages.append((msg_id, current_content))
                if len(seen_messages) > 3:
                    seen_messages.pop(0)
                
                # Check if last 2 messages have same content (stable)
                if len(seen_messages) >= 2 and seen_messages[-1][1] == seen_messages[-2][1]:
                    print(f"Message stable - using message ID: {msg_id}")
                    # Return the actual message object, not just ID
                    return msg
                
                # Also check if content has page numbers and has settled
                if re.search(r'\d+/\d+', current_content):
                    await asyncio.sleep(1)
                    # Re-fetch same message to see if changed
                    refreshed = await client.get_messages(BOT_USERNAME, ids=msg_id)
                    if refreshed and refreshed.message == current_content:
                        print(f"Message stable (page indicator) - ID: {msg_id}")
                        return refreshed
    
    # Return the last data message found if any
    if seen_messages:
        last_msg_id = seen_messages[-1][0]
        last_msg = await client.get_messages(BOT_USERNAME, ids=last_msg_id)
        if last_msg:
            print(f"Returning last available message: {last_msg_id}")
            return last_msg
    
    return None

# =========================
# GET CURRENT PAGE NUMBER
# =========================

def get_current_page(text: str) -> Tuple[Optional[int], Optional[int]]:
    match = re.search(r'(\d+)/(\d+)', text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

# =========================
# CHECK FOR NEXT BUTTON
# =========================

async def has_next_button(message: Message) -> bool:
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
# CLICK NEXT BUTTON WITH VERIFICATION - FIXED
# =========================

async def click_next_with_verification(message: Message, current_page_num: Optional[int]) -> Optional[Message]:
    """Click next and verify page actually increased"""
    if not message.reply_markup:
        return None
    
    try:
        rows = message.reply_markup.rows
        
        for row in rows:
            for button in row.buttons:
                button_text = button.text
                
                if button_text == '➡' or button_text == '→' or 'next' in button_text.lower():
                    print(f"Clicking: '{button_text}'")
                    
                    # Store current page number
                    old_page, total = get_current_page(message.message)
                    print(f"Current page: {old_page}/{total}")
                    
                    # Click the button
                    await message.click(text=button_text)
                    
                    # Wait for edit
                    await asyncio.sleep(1.5)
                    
                    # Get updated message
                    updated = await client.get_messages(BOT_USERNAME, ids=message.id)
                    
                    if not updated:
                        print("No updated message found")
                        return None
                    
                    new_page, total = get_current_page(updated.message)
                    print(f"New page after click: {new_page}/{total}")
                    
                    # Verify page increased
                    if new_page and old_page and new_page > old_page:
                        print("✓ Page advanced successfully")
                        return updated
                    elif new_page and old_page and new_page == old_page:
                        print("⚠ Page didn't change, waiting longer...")
                        await asyncio.sleep(2)
                        # Try again
                        updated2 = await client.get_messages(BOT_USERNAME, ids=message.id)
                        if updated2:
                            new_page2, _ = get_current_page(updated2.message)
                            if new_page2 and new_page2 > old_page:
                                print("✓ Page advanced after longer wait")
                                return updated2
                    else:
                        # If no page numbers, check content change
                        if updated.message != message.message:
                            print("✓ Content changed (no page numbers)")
                            return updated
                    
                    return updated
                    
    except Exception as e:
        print(f"Error clicking next: {e}")
        import traceback
        traceback.print_exc()
    
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
        print(f"Sent message ID: {sent.id}")
        
        # Wait for FINAL message (not intermediate)
        target_message = await wait_for_final_message(sent, timeout=15)
        
        if not target_message:
            return {"status": False, "error": "No valid bot reply received"}
        
        print(f"Final message received in {asyncio.get_event_loop().time() - start_time:.2f}s")
        
        # Collect all records
        all_records = []
        current_message = target_message
        page_num = 1
        source_title = None
        source_description = None
        max_pages = 50
        seen_page_numbers = set()
        
        while current_message and page_num <= max_pages:
            print(f"\n--- Page {page_num} ---")
            
            # Get metadata
            if source_title is None:
                source_title, source_description = get_source_metadata(current_message.message)
                print(f"Source: {source_title}")
            
            # Parse records
            page_records = parse_page_text(current_message.message)
            print(f"Records on this page: {len(page_records)}")
            all_records.extend(page_records)
            
            # Get page numbers
            current_page, total_pages = get_current_page(current_message.message)
            if current_page and total_pages:
                print(f"Page {current_page}/{total_pages}")
                seen_page_numbers.add(current_page)
            
            # Check for next button
            has_next = await has_next_button(current_message)
            
            if not has_next:
                print("No next button - scraping complete")
                break
            
            if total_pages and current_page and current_page >= total_pages:
                print(f"Reached last page ({current_page}/{total_pages})")
                break
            
            # Click next with verification
            print("Clicking next...")
            next_message = await click_next_with_verification(current_message, current_page)
            
            if not next_message:
                print("Failed to get next page")
                break
            
            # Verify page changed
            new_page, _ = get_current_page(next_message.message)
            if new_page and current_page and new_page <= current_page:
                print(f"Page didn't advance ({current_page} -> {new_page}), stopping")
                break
            
            current_message = next_message
            page_num += 1
            
            await asyncio.sleep(0.3)
        
        total_time = asyncio.get_event_loop().time() - start_time
        print(f"\n{'='*50}")
        print(f"DONE: {len(all_records)} records from {page_num} pages in {total_time:.2f}s")
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
        "message": "Reliable Multi-Page Telegram Bot Scraper API",
        "fixes": [
            "wait_for_final_message() - now returns full Message object, not ID",
            "Proper type hints added (Message type)",
            "Tuple return types for page numbers",
            "All message returns now use actual message objects"
        ]
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
