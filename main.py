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
# ADD FIELD TO RECORD
# =========================

def add_field_to_record(record: Dict, field_tag: str, value: str):
    """Add field to record with proper mapping"""
    json_key = None
    
    # Phone numbers
    if "📞Telephone" in field_tag or "📞Phone" in field_tag or "📞Mobile" in field_tag:
        json_key = "phones"
    # Addresses
    elif "🏘️Adres" in field_tag or "🏘️Address" in field_tag:
        json_key = "addresses"
    # Emails
    elif "📩Email" in field_tag or "📩E-mail" in field_tag:
        json_key = "emails"
    # Document number
    elif "🃏Document number" in field_tag or "🃏Document No" in field_tag:
        json_key = "document_number"
    # Full name
    elif "👤Full name" in field_tag or "👤Name" in field_tag:
        json_key = "full_name"
    # Father name
    elif "👨The name of the father" in field_tag or "👨Father name" in field_tag:
        json_key = "father_name"
    # Region
    elif "🗺️Region" in field_tag or "🗺️Location" in field_tag:
        json_key = "region"
    # Nickname
    elif "👤Nick" in field_tag or "👤Nickname" in field_tag:
        json_key = "nick"
    # Passport number
    elif "📖Passport number" in field_tag:
        json_key = "passport_number"
    # Encrypted password
    elif "🔐Encrypted password" in field_tag:
        json_key = "encrypted_password"
    # Plain password
    elif "🔑Password" in field_tag:
        json_key = "password"
    # Dates
    elif "📆Date" in field_tag or "📆The date of registration" in field_tag:
        json_key = "registration_date"
    elif "📆Last activity" in field_tag:
        json_key = "last_activity"
    elif "🎂Date of birth" in field_tag:
        json_key = "dob"
    # Location
    elif "🌃City" in field_tag:
        json_key = "city"
    elif "🇺🇸Stat" in field_tag:
        json_key = "state"
    elif "🏤Postal code" in field_tag:
        json_key = "postal_code"
    # Network
    elif "🎯IP" in field_tag:
        json_key = "ip"
    # Demographics
    elif "🚻Gender" in field_tag:
        json_key = "gender"
    elif "👴Age" in field_tag:
        json_key = "age"
    elif "📍District" in field_tag:
        json_key = "district"
    # Other
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
        # Handle multi-value fields
        if json_key in ["phones", "addresses", "emails"]:
            if json_key not in record:
                record[json_key] = []
            # Add if not already present
            if value not in record[json_key]:
                record[json_key].append(value)
        else:
            # Only set if not already set (first occurrence wins)
            if json_key not in record:
                record[json_key] = value


def is_record_complete(record: Dict) -> bool:
    """Check if a record has enough data to be considered complete"""
    # A record is complete if it has at least one of these identifiers
    identifiers = ["full_name", "father_name", "document_number", "passport_number"]
    for identifier in identifiers:
        if identifier in record:
            return True
    # Also consider record with multiple phones and addresses as complete
    phones_count = len(record.get("phones", []))
    addresses_count = len(record.get("addresses", []))
    if phones_count >= 2 or addresses_count >= 2:
        return True
    return False


# =========================
# HTML PARSER - PROPER RECORD GROUPING
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse LeakBase HTML and extract structured records
    Groups fields that belong to the same person together
    """
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    
    # Find all block elements
    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
        # Extract source title
        source = "Unknown"
        title_elem = block.find("div", class_="block-title")
        if title_elem:
            source = title_elem.get_text(strip=True)
        
        # Get block-text content
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Get raw HTML content and split by double br tags (record separators)
        html_text = str(text_elem)
        
        # Split by <br><br> to get individual records
        # But also preserve the structure
        record_parts = re.split(r'<br>\s*<br>', html_text)
        
        for part in record_parts:
            if not part.strip():
                continue
            
            # Skip the description paragraph (long text without bold tags)
            if '<b>' not in part:
                continue
            
            # Extract all fields from this part
            current_record = {"source": source}
            
            # Pattern for fields with code tags
            pattern_code = re.compile(r'<b>(.+?)</b>\s*<code>(.*?)</code>', re.DOTALL)
            matches_code = pattern_code.findall(part)
            
            for field_tag, value in matches_code:
                field_tag = field_tag.strip()
                value = value.strip()
                if value and value not in ["None", "null", ""]:
                    add_field_to_record(current_record, field_tag, value)
            
            # Pattern for fields without code tags (plain text after bold)
            pattern_text = re.compile(r'<b>(.+?)</b>\s*([^<]+?)(?=<br|<b|$)', re.DOTALL)
            matches_text = pattern_text.findall(part)
            
            for field_tag, value in matches_text:
                field_tag = field_tag.strip()
                value = value.strip()
                if value and len(value) > 1 and value not in ["None", "null", "", ":", "-"]:
                    add_field_to_record(current_record, field_tag, value)
            
            # Only add record if it has fields besides source
            if len(current_record) > 1:
                # Clean up - convert single-item arrays to single values
                for key in ["phones", "addresses", "emails"]:
                    if key in current_record and isinstance(current_record[key], list) and len(current_record[key]) == 1:
                        current_record[key] = current_record[key][0]
                all_records.append(current_record)
    
    return all_records


# =========================
# MAIN SEARCH FUNCTION
# =========================

@app.post("/search")
async def search(data: dict):
    try:
        message = data.get("message", "")
        if not message:
            return {"status": False, "error": "message required"}
        
        print(f"\n=== SEARCH: {message} ===")

        sent_message = await client.send_message(BOT_USERNAME, message)
        print("Message sent")

        await asyncio.sleep(3)

        messages = await client.get_messages(BOT_USERNAME, limit=10)
        
        reply_message = None
        for msg in messages:
            if not msg.out and msg.id > sent_message.id:
                reply_message = msg
                break

        if not reply_message:
            return {"status": False, "error": "No response from bot"}

        print(f"Reply found: {reply_message.id}")

        file_path = None

        if reply_message.buttons:
            print("Buttons found, attempting to click...")
            for row in reply_message.buttons:
                for button in row:
                    if DOWNLOAD_BUTTON.lower() in button.text.lower():
                        print(f"Clicking: {button.text}")
                        await button.click()
                        break
                if file_path:
                    break

            for attempt in range(30):
                await asyncio.sleep(2)
                latest = await client.get_messages(BOT_USERNAME, limit=5)
                for msg in latest:
                    if msg.file and msg.id > reply_message.id:
                        file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                        print(f"Downloaded: {file_path}")
                        break
                if file_path:
                    break

        if not file_path and reply_message.message:
            html_match = re.search(r'(<!DOCTYPE html>|<html>.*?</html>)', 
                                   reply_message.message, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(0)
                temp_path = os.path.join(DOWNLOAD_DIR, f"temp_{reply_message.id}.html")
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                file_path = temp_path
                print(f"Extracted HTML from message")

        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            
            records = parse_leakbase_html(html_content)
            print(f"Parsed {len(records)} records")
            
            if file_path and "temp_" in file_path:
                try:
                    os.remove(file_path)
                except:
                    pass
            
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


# =========================
# GET SEARCH ENDPOINT
# =========================

@app.get("/test")
async def test(q: str):
    try:
        print(f"\n=== SEARCH: {q} ===")

        sent_message = await client.send_message(BOT_USERNAME, q)
        print("Message sent")

        await asyncio.sleep(3)

        messages = await client.get_messages(BOT_USERNAME, limit=10)
        
        reply_message = None
        for msg in messages:
            if not msg.out and msg.id > sent_message.id:
                reply_message = msg
                break

        if not reply_message:
            return {"status": False, "error": "No response from bot"}

        file_path = None

        if reply_message.buttons:
            print("Buttons found...")
            for row in reply_message.buttons:
                for button in row:
                    if DOWNLOAD_BUTTON.lower() in button.text.lower():
                        await button.click()
                        break
                if file_path:
                    break

            for attempt in range(30):
                await asyncio.sleep(2)
                latest = await client.get_messages(BOT_USERNAME, limit=5)
                for msg in latest:
                    if msg.file and msg.id > reply_message.id:
                        file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                        break
                if file_path:
                    break

        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            
            records = parse_leakbase_html(html_content)
            
            return {
                "status": True,
                "query": q,
                "record_count": len(records),
                "data": records
            }
        
        return {"status": False, "error": "No file received"}

    except Exception as e:
        return {"status": False, "error": str(e)}


# =========================
# HOME PAGE
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <!DOCTYPE html>
    <html>
        <head>
            <title>Telegram LeakBase Parser API</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 40px; max-width: 800px; margin: 0 auto; }
                h2 { color: #333; }
                input { width: 70%; padding: 12px; font-size: 16px; border: 1px solid #ddd; border-radius: 4px; }
                button { padding: 12px 24px; font-size: 16px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #0056b3; }
            </style>
        </head>
        <body>
            <h2>🔍 Telegram LeakBase Parser API</h2>
            <p>Enter phone number, email, or name to search in LeakBase bot</p>
            <form action="/test" method="get">
                <input type="text" name="q" placeholder="e.g., 919999988888" style="width: 70%;">
                <button type="submit">Search</button>
            </form>
        </body>
    </html>
    """


# =========================
# HEALTH CHECK
# =========================

@app.get("/health")
async def health():
    return {"status": "ok"}


# =========================
# RUN: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# =========================
