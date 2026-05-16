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
import concurrent.futures

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
# FIELD MAPPING (OPTIMIZED)
# =========================

FIELD_MAP = {
    "📞Telephone": "phone", "📞Phone": "phone", "📞Mobile": "phone",
    "🏘️Adres": "address", "🏘️Address": "address",
    "📩Email": "email", "📩E-mail": "email",
    "🃏Document number": "document_number", "🃏Document No": "document_number",
    "👤Full name": "full_name", "👤Name": "full_name",
    "👨The name of the father": "father_name", "👨Father name": "father_name",
    "🗺️Region": "region", "🗺️Location": "region",
    "👤Nick": "nick", "👤Nickname": "nick",
    "📖Passport number": "passport_number",
    "🔐Encrypted password": "encrypted_password",
    "🔑Password": "password",
    "📆Date": "registration_date", "📆The date of registration": "registration_date",
    "📆Last activity": "last_activity",
    "🎂Date of birth": "dob",
    "🌃City": "city", "🇺🇸Stat": "state",
    "🏤Postal code": "postal_code",
    "🎯IP": "ip", "🚻Gender": "gender",
    "👴Age": "age", "📍District": "district",
    "🔗Link": "link", "🏷️ login": "login",
    "📰Category": "category", "🗾Country": "country",
    "⬆Level": "level", "🏫Education": "education",
    "👤Surname": "surname"
}

def get_json_key(field_tag: str) -> str:
    for key, value in FIELD_MAP.items():
        if key in field_tag:
            return value
    return None

def add_to_record(record: Dict, key: str, value: str):
    if key == "address" and value.replace(" ", "").isdigit():
        return
    if key in ["phone", "email"]:
        if key not in record:
            record[key] = value
    elif key in ["phones", "addresses", "emails"]:
        record.setdefault(key, [])
        if value not in record[key]:
            record[key].append(value)
    else:
        if key not in record:
            record[key] = value

# =========================
# FAST PARSER - OPTIMIZED
# =========================

def parse_leakbase_html_fast(html_content: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    current_source = None
    records_in_current_source = []

    # Find all blocks at once
    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
        # Get source title quickly
        title_elem = block.find("div", class_="block-title")
        source = title_elem.get_text(strip=True) if title_elem else "Unknown"

        if current_source is not None and source != current_source:
            if records_in_current_source:
                all_records.append({
                    "source": current_source,
                    "records": records_in_current_source
                })
            records_in_current_source = []
        
        current_source = source

        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue

        # Get raw HTML and split quickly
        html_text = str(text_elem)
        
        # Fast split by double br
        parts = html_text.split("<br><br>")
        # Also handle variations quickly
        if len(parts) == 1:
            parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)

        for part in parts:
            part = part.strip()
            if not part or '<b>' not in part:
                continue

            # Parse only this part
            soup_part = BeautifulSoup(part, "html.parser")
            record = {}

            # Use find_all for all bold tags at once
            bold_tags = soup_part.find_all("b")
            for bold in bold_tags:
                field_tag = bold.get_text(strip=True)
                json_key = get_json_key(field_tag)
                if not json_key:
                    continue

                # Check for code tag first
                code_tag = bold.find_next_sibling("code")
                if code_tag:
                    value = code_tag.get_text(strip=True)
                    if value:
                        add_to_record(record, json_key, value)
                    continue

                # Check next sibling for text
                next_sib = bold.next_sibling
                if next_sib and isinstance(next_sib, str):
                    value = next_sib.strip()
                    # Take only up to next tag
                    if '<' in value:
                        value = value.split('<')[0].strip()
                    if value:
                        add_to_record(record, json_key, value)

            if record:
                # Convert single-item lists to simple values
                for key in ["phone", "email"]:
                    if key in record and isinstance(record[key], list) and len(record[key]) == 1:
                        record[key] = record[key][0]
                records_in_current_source.append(record)

    if current_source is not None and records_in_current_source:
        all_records.append({
            "source": current_source,
            "records": records_in_current_source
        })

    return all_records

# =========================
# FAST DOWNLOAD AND PARSE
# =========================

async def download_and_parse(reply, message):
    """Download file and parse HTML in parallel"""
    file_path = None
    
    # Click button immediately
    if reply.buttons:
        for row in reply.buttons:
            for btn in row:
                if DOWNLOAD_BUTTON.lower() in btn.text.lower():
                    await btn.click()
                    break
            if file_path:
                break
        
        # Wait for file with shorter intervals
        for _ in range(15):  # Reduced from 30
            await asyncio.sleep(0.5)  # Reduced from 2 seconds
            latest = await client.get_messages(BOT_USERNAME, limit=3)  # Reduced limit
            for msg in latest:
                if msg.file and msg.id > reply.id:
                    file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                    break
            if file_path:
                break
    
    # Check if message contains HTML
    if not file_path and reply.message:
        html_match = re.search(r'(<!DOCTYPE html>|<html>.*?</html>)', reply.message, re.DOTALL | re.IGNORECASE)
        if html_match:
            html_content = html_match.group(0)
            temp_path = os.path.join(DOWNLOAD_DIR, f"temp_{reply.id}.html")
            with open(temp_path, "w", encoding="utf-8") as f:
                f.write(html_content)
            file_path = temp_path
    
    return file_path

# =========================
# API ENDPOINTS
# =========================

@app.post("/search")
async def search(data: dict):
    try:
        start_time = asyncio.get_event_loop().time()
        message = data.get("message", "")
        if not message:
            return {"status": False, "error": "message required"}

        print(f"\n=== SEARCH: {message} ===")
        
        # Send message
        sent = await client.send_message(BOT_USERNAME, message)
        print(f"Message sent in {asyncio.get_event_loop().time() - start_time:.2f}s")

        # Wait for reply with shorter timeout
        reply = None
        for i in range(8):  # Max 8 attempts
            await asyncio.sleep(0.5)  # Check every 0.5 seconds
            messages = await client.get_messages(BOT_USERNAME, limit=5)
            for msg in messages:
                if not msg.out and msg.id > sent.id and msg.message:
                    reply = msg
                    break
            if reply:
                break
        
        if not reply:
            return {"status": False, "error": "No response from bot"}
        
        print(f"Reply received in {asyncio.get_event_loop().time() - start_time:.2f}s")

        # Download file (optimized)
        file_path = await download_and_parse(reply, message)
        
        if not file_path:
            return {"status": False, "error": "No file received"}
        
        print(f"File downloaded in {asyncio.get_event_loop().time() - start_time:.2f}s")

        # Parse HTML (fast)
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
        
        # Run parser in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            records_data = await loop.run_in_executor(pool, parse_leakbase_html_fast, html_content)
        
        # Clean up temp file
        if "temp_" in str(file_path):
            os.remove(file_path)
        
        total_time = asyncio.get_event_loop().time() - start_time
        print(f"Total time: {total_time:.2f}s | Records: {sum(len(s['records']) for s in records_data)}")
        
        return {
            "status": True,
            "query": message,
            "record_count": sum(len(s["records"]) for s in records_data),
            "data": records_data
        }

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
        <head>
            <title>Telegram LeakBase Parser API</title>
            <style>
                body { font-family: Arial, sans-serif; padding: 40px; max-width: 900px; margin: 0 auto; }
                h2 { color: #333; }
                input { width: 70%; padding: 12px; font-size: 16px; border: 1px solid #ddd; border-radius: 4px; }
                button { padding: 12px 24px; font-size: 16px; background: #007bff; color: white; border: none; border-radius: 4px; cursor: pointer; }
                button:hover { background: #0056b3; }
            </style>
        </head>
        <body>
            <h2>🔍 Telegram LeakBase Parser API</h2>
            <form action="/test" method="get">
                <input type="text" name="q" placeholder="Enter query (phone, email, or name)" style="width: 70%;">
                <button type="submit">Search</button>
            </form>
        </body>
    </html>
    """

@app.get("/health")
async def health():
    return {"status": "ok"}
