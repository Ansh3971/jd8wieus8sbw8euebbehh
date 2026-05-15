import os
import re
import asyncio
from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from bs4 import BeautifulSoup

# =========================
# LOAD ENV
# =========================

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BOT_USERNAME = os.getenv("BOT_USERNAME")
DOWNLOAD_BUTTON = os.getenv("DOWNLOAD_BUTTON", "Download")

# =========================
# FASTAPI
# =========================

app = FastAPI(title="Telegram LeakBase Parser API")

# =========================
# TELEGRAM CLIENT
# =========================

client = TelegramClient(
    StringSession(SESSION),
    API_ID,
    API_HASH
)

# =========================
# DOWNLOAD FOLDER
# =========================

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# STARTUP & SHUTDOWN
# =========================

@app.on_event("startup")
async def startup():
    await client.start()
    print("Telegram Client Started")

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()

# =========================
# FIELD MAPPING
# =========================

def add_field_to_record(record: Dict, field_tag: str, value: str):
    """Add field to record with proper mapping"""
    json_key = None
    
    if "📞Telephone" in field_tag or "📞Phone" in field_tag or "📞Mobile" in field_tag:
        json_key = "phones"
    elif "🏘️Adres" in field_tag or "🏘️Address" in field_tag:
        json_key = "addresses"
    elif "📩Email" in field_tag or "📩E-mail" in field_tag:
        json_key = "emails"
    elif "🃏Document number" in field_tag or "🃏Document No" in field_tag:
        json_key = "document_number"
    elif "👤Full name" in field_tag or "👤Name" in field_tag:
        json_key = "full_name"
    elif "👨The name of the father" in field_tag or "👨Father name" in field_tag:
        json_key = "father_name"
    elif "🗺️Region" in field_tag or "🗺️Location" in field_tag:
        json_key = "region"
    elif "👤Nick" in field_tag or "👤Nickname" in field_tag:
        json_key = "nick"
    elif "📖Passport number" in field_tag:
        json_key = "passport_number"
    elif "🔐Encrypted password" in field_tag:
        json_key = "encrypted_password"
    elif "🔑Password" in field_tag:
        json_key = "password"
    elif "📆Date" in field_tag or "📆The date of registration" in field_tag:
        json_key = "registration_date"
    elif "📆Last activity" in field_tag:
        json_key = "last_activity"
    elif "🎂Date of birth" in field_tag:
        json_key = "dob"
    elif "🌃City" in field_tag:
        json_key = "city"
    elif "🇺🇸Stat" in field_tag:
        json_key = "state"
    elif "🏤Postal code" in field_tag:
        json_key = "postal_code"
    elif "🎯IP" in field_tag:
        json_key = "ip"
    elif "🚻Gender" in field_tag:
        json_key = "gender"
    elif "👴Age" in field_tag:
        json_key = "age"
    elif "📍District" in field_tag:
        json_key = "district"
    elif "🔗Link" in field_tag:
        json_key = "link"
    elif "🏷️ login" in field_tag:
        json_key = "login"
    elif "📰Category" in field_tag:
        json_key = "category"
    elif "🗾Country" in field_tag:
        json_key = "country"
    elif "⬆Level" in field_tag:
        json_key = "level"
    elif "🏫Education" in field_tag:
        json_key = "education"
    elif "👤Surname" in field_tag:
        json_key = "surname"
    
    if json_key:
        if json_key in ["phones", "addresses", "emails"]:
            if json_key not in record:
                record[json_key] = []
            if value not in record[json_key]:
                record[json_key].append(value)
        else:
            if json_key not in record:
                record[json_key] = value

# =========================
# MAIN PARSER - LINE BY LINE WITH STATE
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    
    blocks = soup.find_all("div", class_="block")
    for block in blocks:
        # Get source title
        source = "Unknown"
        title_elem = block.find("div", class_="block-title")
        if title_elem:
            source = title_elem.get_text(strip=True)
        
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Get plain text lines to preserve order
        lines = text_elem.get_text(separator="\n", strip=True).split("\n")
        
        current_record = None
        # We will accumulate fields and decide when to finalize a record
        # A new record starts when we see a field that typically starts a person's data
        # and the current record already has a name or father or document number.
        # We'll keep a temporary dict for the current record.
        temp_record = {}
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Skip the description paragraph (long text without colons or field indicators)
            if len(line) > 200 and ':' not in line and not any(emoji in line for emoji in ['📞', '🏘️', '📩', '🃏', '👤', '👨', '🗺️']):
                continue
            
            # Try to extract field and value
            field_tag = None
            value = None
            
            # Pattern 1: bold tags with code (but in plain text, we have to parse from the line as it appears in text)
            # Since we have plain text, we look for known emoji prefixes
            for emoji in FIELD_MAPPING:
                if line.startswith(emoji):
                    # Split at first colon
                    if ':' in line:
                        parts = line.split(':', 1)
                        field_tag = parts[0].strip()
                        value = parts[1].strip()
                    else:
                        field_tag = emoji
                        value = line[len(emoji):].strip()
                    break
            
            if field_tag and value:
                # Add to temp_record
                add_field_to_record(temp_record, field_tag, value)
                
                # Check if this record is complete (has name/father/document)
                # If complete and we see another field that typically starts a new record (like a new phone), we finalize
                # But simpler: After adding, if the record has a name or father or document, and the next line starts a new record, we finalize.
                # We'll finalize later when we detect a new record start.
            else:
                # Possibly multi-line address continuation? We'll ignore.
                pass
            
            # Check if we should finalize the current record: when we encounter a line that starts a new record
            # and current record already has fields. A new record start is indicated by a line that starts with a phone, email, or address,
            # but only if the current record already has some fields (to avoid finalizing empty record).
            # However, without looking ahead, we can finalize at the end of the block.
        
        # At the end of the block, finalize the last record
        if temp_record and len(temp_record) > 1:
            # Clean up single-item arrays
            for key in ["phones", "addresses", "emails"]:
                if key in temp_record and isinstance(temp_record[key], list) and len(temp_record[key]) == 1:
                    temp_record[key] = temp_record[key][0]
            temp_record["source"] = source
            all_records.append(temp_record)
    
    # If the above didn't work (no records), fall back to splitting by double br
    if not all_records:
        # Fallback method: split by <br><br> in raw HTML
        for block in blocks:
            source = "Unknown"
            title_elem = block.find("div", class_="block-title")
            if title_elem:
                source = title_elem.get_text(strip=True)
            
            text_elem = block.find("div", class_="block-text")
            if not text_elem:
                continue
            
            html_text = str(text_elem)
            # Split by double br (with optional spaces and slashes)
            parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)
            
            for part in parts:
                part = part.strip()
                if not part or '<b>' not in part:
                    continue
                if len(part) < 50 and ':' not in part:
                    continue
                record = {"source": source}
                # Extract fields from this part
                pattern_code = re.compile(r'<b>(.+?)</b>\s*<code>(.*?)</code>', re.DOTALL)
                for field_tag, value in pattern_code.findall(part):
                    add_field_to_record(record, field_tag.strip(), value.strip())
                pattern_text = re.compile(r'<b>(.+?)</b>\s*([^<]+?)(?=<br|<b|$)', re.DOTALL)
                for field_tag, value in pattern_text.findall(part):
                    add_field_to_record(record, field_tag.strip(), value.strip())
                if len(record) > 1:
                    for key in ["phones", "addresses", "emails"]:
                        if key in record and isinstance(record[key], list) and len(record[key]) == 1:
                            record[key] = record[key][0]
                    all_records.append(record)
    
    return all_records

# =========================
# API ENDPOINTS
# =========================

@app.post("/search")
async def search(data: dict):
    try:
        message = data.get("message", "")
        if not message:
            return {"status": False, "error": "message required"}
        
        print(f"\n=== SEARCH: {message} ===")
        sent = await client.send_message(BOT_USERNAME, message)
        await asyncio.sleep(3)
        
        messages = await client.get_messages(BOT_USERNAME, limit=10)
        reply = None
        for msg in messages:
            if not msg.out and msg.id > sent.id:
                reply = msg
                break
        if not reply:
            return {"status": False, "error": "No response from bot"}
        
        file_path = None
        
        if reply.buttons:
            for row in reply.buttons:
                for btn in row:
                    if DOWNLOAD_BUTTON.lower() in btn.text.lower():
                        await btn.click()
                        break
                if file_path:
                    break
            for _ in range(30):
                await asyncio.sleep(2)
                latest = await client.get_messages(BOT_USERNAME, limit=5)
                for msg in latest:
                    if msg.file and msg.id > reply.id:
                        file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                        break
                if file_path:
                    break
        
        if not file_path and reply.message:
            html_match = re.search(r'(<!DOCTYPE html>|<html>.*?</html>)', reply.message, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(0)
                temp_path = os.path.join(DOWNLOAD_DIR, f"temp_{reply.id}.html")
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                file_path = temp_path
        
        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            records = parse_leakbase_html(html_content)
            if "temp_" in file_path:
                os.remove(file_path)
            return {
                "status": True,
                "query": message,
                "record_count": len(records),
                "data": records
            }
        
        return {"status": False, "error": "No file received"}
    
    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": False, "error": str(e)}

@app.get("/test")
async def test(q: str):
    return await search({"message": q})

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
        <head><title>Telegram LeakBase Parser API</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h2>🔍 Telegram LeakBase Parser API</h2>
            <form action="/test" method="get">
                <input type="text" name="q" placeholder="Enter query" style="width:300px; padding:10px;">
                <button type="submit">Search</button>
            </form>
        </body>
    </html>
    """

@app.get("/health")
async def health():
    return {"status": "ok"}

# =========================
# RUN: uvicorn main:app --host 0.0.0.0 --port 8000
# =========================
