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

    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
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

        html_text = str(text_elem)
        
        parts = html_text.split("<br><br>")
        if len(parts) == 1:
            parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)

        for part in parts:
            part = part.strip()
            if not part or '<b>' not in part:
                continue

            soup_part = BeautifulSoup(part, "html.parser")
            record = {}

            bold_tags = soup_part.find_all("b")
            for bold in bold_tags:
                field_tag = bold.get_text(strip=True)
                json_key = get_json_key(field_tag)
                if not json_key:
                    continue

                code_tag = bold.find_next_sibling("code")
                if code_tag:
                    value = code_tag.get_text(strip=True)
                    if value:
                        add_to_record(record, json_key, value)
                    continue

                next_sib = bold.next_sibling
                if next_sib and isinstance(next_sib, str):
                    value = next_sib.strip()
                    if '<' in value:
                        value = value.split('<')[0].strip()
                    if value:
                        add_to_record(record, json_key, value)

            if record:
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
# DOWNLOAD WITH CONTINUOUS LOOP (CLICK EVERY TIME)
# =========================

async def download_file_with_loop(reply, sent_message_id):
    """Keep clicking download button and checking for file until found"""
    file_path = None
    
    # Maximum attempts - will keep trying until file is found
    max_attempts = 60  # 60 seconds max wait
    
    for attempt in range(max_attempts):
        print(f"Attempt {attempt + 1}: Checking for file...")
        
        # Try to click download button every time (in case first click didn't work)
        if reply.buttons:
            for row in reply.buttons:
                for btn in row:
                    if DOWNLOAD_BUTTON.lower() in btn.text.lower():
                        try:
                            await btn.click()
                            print(f"Button clicked on attempt {attempt + 1}")
                        except Exception as e:
                            print(f"Click failed: {e}")
                        break
                if file_path:
                    break
        
        # Check for file
        try:
            latest = await client.get_messages(BOT_USERNAME, limit=5)
            
            for msg in latest:
                # Check if this is a new file message
                if msg.file and msg.id > sent_message_id:
                    file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                    print(f"File found and downloaded: {file_path}")
                    return file_path
        except Exception as e:
            print(f"Error checking messages: {e}")
        
        # Wait before next attempt
        await asyncio.sleep(1)
    
    return None

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
        sent_message_id = sent.id
        print(f"Message sent (ID: {sent_message_id})")

        # Wait for bot reply
        reply = None
        for attempt in range(15):
            await asyncio.sleep(1)
            messages = await client.get_messages(BOT_USERNAME, limit=5)
            for msg in messages:
                if not msg.out and msg.id > sent_message_id and msg.message:
                    reply = msg
                    print(f"Reply found (ID: {reply.id})")
                    break
            if reply:
                break
        
        if not reply:
            return {"status": False, "error": "No response from bot"}
        
        print(f"Reply received in {asyncio.get_event_loop().time() - start_time:.2f}s")

        # Download file with continuous loop - clicks button repeatedly
        file_path = await download_file_with_loop(reply, sent_message_id)
        
        if not file_path:
            return {"status": False, "error": "No file received after multiple attempts"}
        
        print(f"File downloaded in {asyncio.get_event_loop().time() - start_time:.2f}s")

        # Parse HTML
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
        
        # Run parser in thread pool
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            records_data = await loop.run_in_executor(pool, parse_leakbase_html_fast, html_content)
        
        # Clean up temp file if needed
        if "temp_" in str(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        total_time = asyncio.get_event_loop().time() - start_time
        total_records = sum(len(s["records"]) for s in records_data)
        print(f"Total time: {total_time:.2f}s | Records: {total_records}")
        
        return {
            "status": True,
            "query": message,
            "record_count": total_records,
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
