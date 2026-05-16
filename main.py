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
# POSITION-BASED PARSER (NO FIELD MAPPING)
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse HTML without any field mapping - preserves exact order of fields
    """
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    current_source = None
    records_in_current_source = []

    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
        # Get source title
        title_elem = block.find("div", class_="block-title")
        source = title_elem.get_text(strip=True) if title_elem else "Unknown"

        # If source changed, save previous records
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
        
        # Split by double br tags
        parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)

        for part in parts:
            part = part.strip()
            if not part or '<b>' not in part:
                continue

            # Parse just this record
            soup_part = BeautifulSoup(part, "html.parser")
            record = {}
            
            # Find all field-value pairs in order
            for bold in soup_part.find_all("b"):
                field = bold.get_text(strip=True)
                # Remove emoji and colon for cleaner field name
                field_clean = re.sub(r'[^\w\s]', '', field)
                field_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_clean)
                field_clean = field_clean.strip().replace(" ", "_").lower()
                
                # Get value - check for code tag first
                value = None
                code_tag = bold.find_next_sibling("code")
                if code_tag:
                    value = code_tag.get_text(strip=True)
                else:
                    next_sib = bold.next_sibling
                    if next_sib and isinstance(next_sib, str):
                        value = next_sib.strip()
                        if '<' in value:
                            value = value.split('<')[0].strip()
                
                if value:
                    # Handle multiple same fields (like multiple phones)
                    if field_clean in record:
                        if not isinstance(record[field_clean], list):
                            record[field_clean] = [record[field_clean]]
                        record[field_clean].append(value)
                    else:
                        record[field_clean] = value

            if record:
                records_in_current_source.append(record)

    # Add last source's records
    if current_source is not None and records_in_current_source:
        all_records.append({
            "source": current_source,
            "records": records_in_current_source
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
        
        # Run parser in thread pool
        loop = asyncio.get_event_loop()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            records_data = await loop.run_in_executor(pool, parse_leakbase_html, html_content)
        
        # Clean up temp file
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
