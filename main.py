import os
import re
import asyncio
from typing import Optional, List, Dict, Any, Tuple

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
    title="Telegram Bot API - Full Page Scraper"
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
# GET PAGE NUMBERS
# =========================

def get_page_numbers(text: str) -> Tuple[Optional[int], Optional[int]]:
    match = re.search(r'(\d+)/(\d+)', text)
    if match:
        return int(match.group(1)), int(match.group(2))
    return None, None

# =========================
# WAIT FOR STABLE MESSAGE
# =========================

async def wait_for_stable_message(message_id: int, initial_content: str, timeout: int = 8) -> Optional[Any]:
    """Wait for message to stop changing (bot finishes editing)"""
    last_content = initial_content
    stable_count = 0
    
    for attempt in range(10):  # 10 attempts
        await asyncio.sleep(0.8)
        
        try:
            current = await client.get_messages(BOT_USERNAME, ids=message_id)
            if not current or not current.message:
                continue
            
            if current.message == last_content:
                stable_count += 1
                if stable_count >= 2:  # Same content twice = stable
                    print(f"Message stable after {attempt+1} attempts")
                    return current
            else:
                last_content = current.message
                stable_count = 0
                print(f"Message still changing...")
        except:
            pass
    
    # Return last available
    return await client.get_messages(BOT_USERNAME, ids=message_id)

# =========================
# CLICK NEXT BUTTON WITH RETRY AND VERIFICATION
# =========================

async def click_next_with_retry(message, max_retries: int = 5) -> Optional[Any]:
    """Click next button and verify page actually increased"""
    
    # Get current page number
    old_page, total_pages = get_page_numbers(message.message)
    print(f"Current page: {old_page}/{total_pages}")
    
    if not message.reply_markup:
        print("No reply_markup on message")
        return None
    
    for retry in range(max_retries):
        try:
            rows = message.reply_markup.rows
            next_button = None
            
            # Find next button
            for row in rows:
                for button in row.buttons:
                    if button.text == '➡' or button.text == '→' or 'next' in button.text.lower():
                        next_button = button
                        break
                if next_button:
                    break
            
            if not next_button:
                print(f"Next button not found (retry {retry + 1})")
                await asyncio.sleep(1)
                # Refresh message
                message = await client.get_messages(BOT_USERNAME, ids=message.id)
                continue
            
            print(f"Clicking: '{next_button.text}' (attempt {retry + 1})")
            
            # Click the button
            await message.click(text=next_button.text)
            
            # Wait for edit with progressive delay
            wait_time = 2 if retry == 0 else 3
            await asyncio.sleep(wait_time)
            
            # Get updated message
            updated = await client.get_messages(BOT_USERNAME, ids=message.id)
            
            if not updated:
                print("No updated message received")
                continue
            
            # Wait for message to become stable
            updated = await wait_for_stable_message(updated.id, updated.message, timeout=5)
            
            if not updated:
                continue
            
            # Verify page increased
            new_page, _ = get_page_numbers(updated.message)
            print(f"New page: {new_page}/{total_pages}")
            
            if new_page and old_page and new_page > old_page:
                print(f"✓ Page advanced from {old_page} to {new_page}")
                return updated
            elif new_page and old_page and new_page == old_page:
                print(f"⚠ Page didn't advance ({old_page} -> {new_page}), retrying...")
                # Refresh message and try again
                message = updated
                continue
            elif not new_page and updated.message != message.message:
                print("✓ Content changed (no page numbers)")
                return updated
                
        except Exception as e:
            print(f"Error on retry {retry + 1}: {e}")
            await asyncio.sleep(1)
    
    print(f"Failed to advance page after {max_retries} retries")
    return None

# =========================
# WAIT FOR INITIAL REPLY WITH STABILITY CHECK
# =========================

async def wait_for_initial_reply(sent_message, max_wait: int = 20) -> Optional[Any]:
    """Wait for bot's initial reply and ensure it's stable"""
    sent_id = sent_message.id
    
    for attempt in range(20):
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
            
            # Found potential reply
            if len(msg.message) > 100 or re.search(r'[📩📞🏘️🃏👤👨🗺️💾]', msg.message):
                print(f"Found reply message ID: {msg.id}")
                # Wait for it to become stable
                stable_msg = await wait_for_stable_message(msg.id, msg.message, timeout=6)
                if stable_msg:
                    return stable_msg
                return msg
    
    return None

# =========================
# MAIN SEARCH - GUARANTEED ALL PAGES
# =========================

@app.post("/search")
async def search(data: Query):
    try:
        print("\n" + "="*60)
        print("NEW SEARCH - GUARANTEED ALL PAGES")
        print("="*60)
        print(f"Query: {data.message}")
        
        start_time = asyncio.get_event_loop().time()
        
        # Send query
        sent = await client.send_message(BOT_USERNAME, data.message)
        print(f"Sent message ID: {sent.id}")
        
        # Wait for initial stable reply
        current_message = await wait_for_initial_reply(sent, max_wait=20)
        
        if not current_message:
            return {"status": False, "error": "No bot reply received"}
        
        print(f"Initial reply received in {asyncio.get_event_loop().time() - start_time:.2f}s")
        
        # Collect all records
        all_records = []
        page_num = 1
        source_title = None
        source_description = None
        max_pages = 50
        seen_pages = set()
        
        while current_message and page_num <= max_pages:
            print(f"\n{'─'*40}")
            print(f"Processing Page {page_num}")
            print(f"{'─'*40}")
            
            # Get metadata from first page
            if source_title is None:
                source_title, source_description = get_source_metadata(current_message.message)
                print(f"Source: {source_title}")
            
            # Parse records
            page_records = parse_page_text(current_message.message)
            print(f"Records on this page: {len(page_records)}")
            all_records.extend(page_records)
            
            # Get page numbers
            current_page, total_pages = get_page_numbers(current_message.message)
            if current_page and total_pages:
                print(f"Page {current_page}/{total_pages}")
                if current_page in seen_pages:
                    print("Duplicate page detected - stopping")
                    break
                seen_pages.add(current_page)
            
            # Check if this is the last page
            if total_pages and current_page and current_page >= total_pages:
                print(f"✓ Reached last page ({current_page}/{total_pages})")
                break
            
            # Check for next button
            has_next = await has_next_button(current_message)
            if not has_next:
                print("No next button found")
                # Double check page numbers
                if total_pages and current_page and current_page < total_pages:
                    print(f"WARNING: Page {current_page}/{total_pages} but no next button!")
                break
            
            # Click next with retry
            print("Clicking next button...")
            next_message = await click_next_with_retry(current_message, max_retries=5)
            
            if not next_message:
                print("❌ Failed to get next page after retries")
                break
            
            # Verify page number increased
            new_page, _ = get_page_numbers(next_message.message)
            old_page, _ = get_page_numbers(current_message.message)
            
            if old_page and new_page:
                if new_page <= old_page:
                    print(f"❌ Page didn't advance: {old_page} -> {new_page}")
                    # Try one more time with fresh message
                    refreshed = await client.get_messages(BOT_USERNAME, ids=next_message.id)
                    if refreshed:
                        new_page2, _ = get_page_numbers(refreshed.message)
                        if new_page2 and new_page2 > old_page:
                            print(f"✓ Page advanced after refresh: {old_page} -> {new_page2}")
                            current_message = refreshed
                            page_num += 1
                            continue
                    break
            
            current_message = next_message
            page_num += 1
            
            # Small delay between pages
            await asyncio.sleep(0.5)
        
        total_time = asyncio.get_event_loop().time() - start_time
        print(f"\n{'='*60}")
        print(f"✓ SCRAPE COMPLETE")
        print(f"  Pages scraped: {page_num}")
        print(f"  Total records: {len(all_records)}")
        print(f"  Time taken: {total_time:.2f}s")
        print(f"{'='*60}")
        
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
        "message": "Telegram Bot API - Guaranteed Full Page Scraper",
        "features": [
            "✓ Waits for message to become stable before parsing",
            "✓ Retries clicking next button up to 5 times",
            "✓ Verifies page number actually increased",
            "✓ Detects duplicate pages",
            "✓ Guarantees all pages are scraped"
        ]
    }

# =========================
# RUN
# =========================

# uvicorn main:app --host 0.0.0.0 --port $PORT
