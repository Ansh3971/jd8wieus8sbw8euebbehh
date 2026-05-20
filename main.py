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

API_ID = int(os.getenv("API_ID", 12345))
API_HASH = os.getenv("API_HASH", "your_api_hash")
SESSION = os.getenv("SESSION", "your_session_string")
BOT_USERNAME = os.getenv("BOT_USERNAME", "your_bot")
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
# FIELD MAPPING (OPTIMIZED WITH DICT)
# =========================

FIELD_MAP = {
    "📞Telephone": "telephone", "📞Phone": "telephone", "📞Mobile": "telephone",
    "🏘️Adres": "adres", "🏘️Address": "adres",
    "📩Email": "email", "📩E-mail": "email",
    "🃏Document number": "document_number", "🃏Document No": "document_number",
    "👤Full name": "full_name", "👤Name": "full_name",
    "👨The name of the father": "the_name_of_the_father", "👨Father name": "the_name_of_the_father",
    "🗺️Region": "region", "🗺️Location": "region", "🗺️ Region": "region",
    "👤Nick": "nick", "👤Nickname": "nick",
    "📖Passport number": "passport_number",
    "🔐Encrypted password": "encrypted_password",
    "🔑Password": "password",
    "📆Date": "the_date_of_registration", "📆The date of registration": "the_date_of_registration",
    "📆Last activity": "last_activity",
    "🎂Date of birth": "dob",
    "🌃City": "city", "🇺🇸Stat": "state",
    "🏤Postal code": "postal_code",
    "🎯IP": "ip", "🚻Gender": "gender",
    "👴Age": "age", "📍District": "district",
    "🔗Link": "link", "🏷️ login": "login",
    "📰Category": "category", "🗾Country": "country",
    "⬆Level": "level", "🏫Education": "education",
    "👤Surname": "surname", "💶Currency": "currency",
    "💸Sum": "sum"
}

def get_json_key(field_tag: str) -> str:
    for key, value in FIELD_MAP.items():
        if key in field_tag:
            return value
    return None

def add_to_record(record: Dict, key: str, value: str):
    if key in ["adres", "address"] and value.replace(" ", "").isdigit():
        return
    if key in ["telephone", "phone", "email"]:
        if key not in record:
            record[key] = value
    elif key in ["phones", "addresses", "emails", "telephones"]:
        record.setdefault(key, [])
        if value not in record[key]:
            record[key].append(value)
    else:
        if key not in record:
            record[key] = value

# =========================
# FAST PARSER - OPTIMIZED
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_content, "lxml")
    all_records = []
    
    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
        # Get source title
        title_elem = block.find("div", class_="block-title")
        source = title_elem.get_text(strip=True) if title_elem else "Unknown"
        
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Fast split using regex
        html_text = str(text_elem)
        parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)
        
        for part in parts:
            part = part.strip()
            if not part or '<b>' not in part:
                continue
            
            # Skip description
            if len(part) > 300 and '📞' not in part and '📩' not in part:
                continue
            
            record = {}
            
            # Fast extraction using regex instead of BeautifulSoup for each part
            # Pattern 1: <b>FIELD</b> <code>VALUE</code>
            pattern1 = re.compile(r'<b>(.+?)</b>\s*<code>(.*?)</code>', re.DOTALL)
            matches1 = pattern1.findall(part)
            
            for field_raw, value in matches1:
                json_key = get_json_key(field_raw)
                if json_key:
                    value_clean = re.sub(r'<[^>]+>', '', value).strip()
                    if value_clean:
                        add_to_record(record, json_key, value_clean)
            
            # Pattern 2: <b>FIELD</b> VALUE (without code tag)
            pattern2 = re.compile(r'<b>(.+?)</b>\s*([^<]+?)(?=<br|<b|$)', re.DOTALL)
            matches2 = pattern2.findall(part)
            
            for field_raw, value in matches2:
                json_key = get_json_key(field_raw)
                if json_key and json_key not in record:
                    value_clean = value.strip()
                    value_clean = re.sub(r'<[^>]+>', '', value_clean)
                    value_clean = value_clean.strip()
                    if value_clean:
                        add_to_record(record, json_key, value_clean)
            
            if record:
                all_records.append({
                    "source": source,
                    "data": record
                })
    
    return all_records

# =========================
# FAST DOWNLOAD WITH CONTINUOUS LOOP
# =========================

async def download_file_with_loop(reply, sent_message_id):
    """Keep clicking download button and checking for file until found"""
    file_path = None
    
    # Click button instantly
    if reply.buttons:
        for row in reply.buttons:
            for btn in row:
                if DOWNLOAD_BUTTON.lower() in btn.text.lower():
                    await btn.click()
                    print("Button clicked")
                    break
            if file_path:
                break
    
    # Fast polling for file - check every 0.3 seconds
    for attempt in range(40):
        await asyncio.sleep(0.3)
        try:
            latest = await client.get_messages(BOT_USERNAME, limit=3)
            for msg in latest:
                if msg.file and msg.id > sent_message_id:
                    file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                    print(f"File found and downloaded: {file_path}")
                    return file_path
        except Exception as e:
            print(f"Error checking messages: {e}")
    
    return None

# =========================
# API ENDPOINTS (OPTIMIZED)
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

        # Fast polling for reply - check every 0.3 seconds
        reply = None
        for attempt in range(20):
            await asyncio.sleep(0.3)
            messages = await client.get_messages(BOT_USERNAME, limit=3)
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

        # Download file
        file_path = await download_file_with_loop(reply, sent_message_id)
        
        if not file_path:
            return {"status": False, "error": "No file received after multiple attempts"}
        
        print(f"File downloaded in {asyncio.get_event_loop().time() - start_time:.2f}s")

        # Parse HTML in thread pool to avoid blocking
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
        
        # Use thread pool for CPU-intensive parsing
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            records_data = await loop.run_in_executor(pool, parse_leakbase_html, html_content)
        
        # Clean up temp file
        if "temp_" in str(file_path):
            try:
                os.remove(file_path)
            except:
                pass
        
        total_time = asyncio.get_event_loop().time() - start_time
        total_records = len(records_data)
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

# =========================
# RUN: uvicorn main:app --host 0.0.0.0 --port 8000
# =========================
