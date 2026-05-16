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
# SIMPLE PARSER - DIRECT HTML EXTRACTION
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse HTML directly without any complex logic
    """
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    
    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
        # Get source title
        title_elem = block.find("div", class_="block-title")
        source = title_elem.get_text(strip=True) if title_elem else "Unknown"
        
        # Get all records within this block
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Get raw HTML and find all record parts
        html_text = str(text_elem)
        
        # Split by double br tags
        parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)
        
        for part in parts:
            part = part.strip()
            if not part or '<b>' not in part:
                continue
            
            # Extract all fields using simple pattern
            # Pattern: <b>FIELD_NAME</b> <code>VALUE</code> or <b>FIELD_NAME</b> VALUE
            fields = {}
            
            # Method 1: Find all <b> tags and their following <code> tags
            for bold in re.finditer(r'<b>(.+?)</b>\s*<code>(.*?)</code>', part, re.DOTALL):
                field_name = bold.group(1).strip()
                field_value = bold.group(2).strip()
                # Clean field name
                field_name_clean = re.sub(r'[^\w\s]', '', field_name)
                field_name_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_name_clean)
                field_name_clean = field_name_clean.strip().replace(" ", "_").lower()
                fields[field_name_clean] = field_value
            
            # Method 2: Find <b> tags with plain text values (no code tag)
            for bold in re.finditer(r'<b>(.+?)</b>\s*([^<]+?)(?=<br|<b|$)', part, re.DOTALL):
                field_name = bold.group(1).strip()
                field_value = bold.group(2).strip()
                # Skip if already captured by code tag method
                field_name_clean = re.sub(r'[^\w\s]', '', field_name)
                field_name_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_name_clean)
                field_name_clean = field_name_clean.strip().replace(" ", "_").lower()
                if field_name_clean not in fields:
                    fields[field_name_clean] = field_value
            
            if fields:
                all_records.append({
                    "source": source,
                    "data": fields
                })
    
    return all_records

# =========================
# ALTERNATIVE: PARSE USING ORIGINAL STRING POSITION
# =========================

def parse_leakbase_html_original(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse using original text lines - most reliable
    """
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    
    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
        # Get source title
        title_elem = block.find("div", class_="block-title")
        source = title_elem.get_text(strip=True) if title_elem else "Unknown"
        
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Get plain text lines
        text = text_elem.get_text(separator="\n", strip=True)
        lines = text.split("\n")
        
        current_record = {}
        is_first_field = True
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            # Skip the description paragraph
            if len(line) > 100 and ':' not in line:
                continue
            
            # Check if line contains a field (starts with emoji or has colon)
            if ':' in line:
                # Split into field and value
                parts = line.split(':', 1)
                if len(parts) == 2:
                    field_raw = parts[0].strip()
                    value = parts[1].strip()
                    
                    # Clean field name
                    field_clean = re.sub(r'[^\w\s]', '', field_raw)
                    field_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_clean)
                    field_clean = field_clean.strip().replace(" ", "_").lower()
                    
                    # If this is a new record (starting with telephone or email)
                    if is_first_field and current_record:
                        all_records.append({
                            "source": source,
                            "data": current_record
                        })
                        current_record = {}
                        is_first_field = True
                    
                    # Handle multiple values for same field
                    if field_clean in current_record:
                        if not isinstance(current_record[field_clean], list):
                            current_record[field_clean] = [current_record[field_clean]]
                        current_record[field_clean].append(value)
                    else:
                        current_record[field_clean] = value
                    
                    is_first_field = False
        
        # Add the last record
        if current_record:
            all_records.append({
                "source": source,
                "data": current_record
            })
    
    return all_records

# =========================
# DOWNLOAD WITH CONTINUOUS LOOP
# =========================

async def download_file_with_loop(reply, sent_message_id):
    """Keep clicking download button and checking for file until found"""
    file_path = None
    
    # Maximum attempts - 60 seconds max wait
    max_attempts = 60
    
    for attempt in range(max_attempts):
        print(f"Attempt {attempt + 1}: Checking for file...")
        
        # Try to click download button every time
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
                if msg.file and msg.id > sent_message_id:
                    file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                    print(f"File found and downloaded: {file_path}")
                    return file_path
        except Exception as e:
            print(f"Error checking messages: {e}")
        
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

        # Download file
        file_path = await download_file_with_loop(reply, sent_message_id)
        
        if not file_path:
            return {"status": False, "error": "No file received after multiple attempts"}
        
        print(f"File downloaded in {asyncio.get_event_loop().time() - start_time:.2f}s")

        # Parse HTML
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            html_content = f.read()
        
        # Try both parsing methods
        records_data = parse_leakbase_html_original(html_content)
        
        # If first method returns empty, try second method
        if not records_data:
            records_data = parse_leakbase_html(html_content)
        
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
