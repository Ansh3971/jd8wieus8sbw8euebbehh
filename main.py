import os
import re
import asyncio
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
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
# HTML PARSER - FIXED VERSION
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse LeakBase HTML and extract structured records
    Properly splits multiple records within each block
    """
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    
    # Find all block elements
    blocks = soup.find_all("div", class_="block")
    if not blocks:
        blocks = soup.find_all("div", attrs={"id": re.compile(r'^p\d+')})
    
    for block in blocks:
        # Extract source title
        source = "Unknown"
        title_elem = block.find("div", class_="block-title")
        if not title_elem:
            title_elem = block.find("h1") or block.find("h2") or block.find("h3")
        
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            # Remove emoji but keep name
            title_text = re.sub(r'[^\w\s\.\-]', '', title_text)
            if title_text and len(title_text) < 100:
                source = title_text.strip()
        
        # Get block-text content
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Get raw HTML to preserve structure
        html_text = str(text_elem)
        
        # Split records by double br tags (record separator)
        record_htmls = re.split(r'<br>\s*<br>', html_text)
        
        for record_html in record_htmls:
            if not record_html.strip():
                continue
            
            # Skip description text (first part of block that has no fields)
            if len(record_html) < 100 and ":" not in record_html:
                continue
            
            current_record = {"source": source}
            
            # Extract all field-value pairs from this record HTML
            # Pattern: <b>📞Telephone:</b> <code>123456</code>
            field_pattern = re.compile(r'<b>(.+?)</b>\s*<code>(.*?)</code>', re.DOTALL)
            
            matches = field_pattern.findall(record_html)
            
            for field_tag, value in matches:
                field_tag = field_tag.strip()
                value = value.strip()
                
                if not value:
                    continue
                
                # Map field names
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
                elif "🏢The name of the company" in field_tag:
                    json_key = "company"
                elif "💸Sum" in field_tag:
                    json_key = "amount"
                elif "🚘Car number" in field_tag:
                    json_key = "car_number"
                elif "🔖Type" in field_tag:
                    json_key = "type"
                elif "☄Prefix" in field_tag:
                    json_key = "prefix"
                elif "👤Surname" in field_tag:
                    json_key = "surname"
                elif "🆔VK ID" in field_tag:
                    json_key = "vk_id"
                elif "📆Date:" in field_tag:
                    json_key = "date"
                elif "❤️Likes" in field_tag:
                    json_key = "likes"
                elif "💬Comment" in field_tag:
                    json_key = "comment_url"
                elif "📝Text" in field_tag:
                    json_key = "comment_text"
                
                if json_key:
                    # Handle multi-value fields
                    if json_key in ["phones", "addresses", "emails"]:
                        if json_key not in current_record:
                            current_record[json_key] = []
                        if value not in current_record[json_key]:
                            current_record[json_key].append(value)
                    else:
                        # Only set if not already set (first occurrence wins)
                        if json_key not in current_record:
                            current_record[json_key] = value
            
            # Also handle fields that might be in plain text without code tags
            # Pattern for: <b>📞Telephone:</b> value (no code tag)
            plain_field_pattern = re.compile(r'<b>(.+?)</b>\s*([^<]+)(?=<br|$)', re.DOTALL)
            plain_matches = plain_field_pattern.findall(record_html)
            
            for field_tag, value in plain_matches:
                field_tag = field_tag.strip()
                value = value.strip()
                
                if not value or len(value) < 2 or ":" in field_tag:
                    continue
                
                # Same mapping as above
                json_key = None
                if "📞Telephone" in field_tag or "📞Phone" in field_tag:
                    json_key = "phones"
                elif "🏘️Adres" in field_tag or "🏘️Address" in field_tag:
                    json_key = "addresses"
                elif "📩Email" in field_tag:
                    json_key = "emails"
                elif "🃏Document number" in field_tag:
                    json_key = "document_number"
                elif "👤Full name" in field_tag:
                    json_key = "full_name"
                elif "👨The name of the father" in field_tag:
                    json_key = "father_name"
                elif "🗺️Region" in field_tag:
                    json_key = "region"
                elif "👤Nick" in field_tag:
                    json_key = "nick"
                elif "🔐Encrypted password" in field_tag:
                    json_key = "encrypted_password"
                elif "🔑Password" in field_tag:
                    json_key = "password"
                
                if json_key:
                    if json_key in ["phones", "addresses", "emails"]:
                        if json_key not in current_record:
                            current_record[json_key] = []
                        if value not in current_record[json_key]:
                            current_record[json_key].append(value)
                    else:
                        if json_key not in current_record:
                            current_record[json_key] = value
            
            # Only add record if it has at least one meaningful field (besides source)
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
async def search(request: Request):
    try:
        body = await request.json()
        message = body.get("message", "")
        
        if not message:
            return {"status": False, "error": "message required"}
        
        print(f"\n=== SEARCH: {message} ===")

        # Send message to bot
        sent_message = await client.send_message(BOT_USERNAME, message)
        print("Message sent")

        # Wait for bot reply
        await asyncio.sleep(3)

        # Get bot reply
        messages = await client.get_messages(BOT_USERNAME, limit=10)
        
        # Find the bot's reply (not our message)
        reply_message = None
        for msg in messages:
            if not msg.out and msg.id > sent_message.id:
                reply_message = msg
                break

        if not reply_message:
            return {"status": False, "error": "No response from bot"}

        print(f"Reply found: {reply_message.id}")

        # Try to click download button
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

            # Wait for file after clicking
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

        # If no file from button, check if reply message contains HTML
        if not file_path and reply_message.message:
            html_match = re.search(r'(<!DOCTYPE html>|<html>.*?</html>)', 
                                   reply_message.message, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(0)
                temp_path = os.path.join(DOWNLOAD_DIR, f"temp_{reply_message.id}.html")
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                file_path = temp_path
                print(f"Extracted HTML from message to: {file_path}")

        # Parse the file
        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            
            records = parse_leakbase_html(html_content)
            print(f"Parsed {len(records)} records")
            
            # Clean up temp file
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
        
        # Fallback: parse text from message
        if reply_message.message:
            return {
                "status": False,
                "error": "No HTML file received",
                "raw_message_preview": reply_message.message[:500]
            }
        
        return {"status": False, "error": "Could not extract any data"}

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return {"status": False, "error": str(e)}

# =========================
# GET SEARCH ENDPOINT (for browser)
# =========================

@app.get("/search")
async def search_get(q: str):
    # Create a mock request body
    return await search(Request(scope={"type": "http"}, receive=None, send=None), 
                       message=q) if False else None

# =========================
# SIMPLE GET ENDPOINT (alternative)
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
                .result { margin-top: 20px; padding: 20px; background: #f5f5f5; border-radius: 4px; white-space: pre-wrap; word-wrap: break-word; }
                .error { color: red; }
                pre { background: #fff; padding: 10px; overflow-x: auto; font-size: 12px; }
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
