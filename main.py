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
# SIMPLE PARSER - DIRECT HTML EXTRACTION WITH VALUE CAPTURE
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse HTML directly - works by extracting text and matching patterns
    """
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    
    blocks = soup.find_all("div", class_="block")
    
    for block in blocks:
        # Get source title
        title_elem = block.find("div", class_="block-title")
        source = title_elem.get_text(strip=True) if title_elem else "Unknown"
        
        # Get block-text content
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Get the raw HTML as string
        html_text = str(text_elem)
        
        # Split by double <br> tags to separate records
        parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Skip the description text (no bold tags)
            if '<b>' not in part:
                continue
            
            # Create a temporary soup for this part
            part_soup = BeautifulSoup(part, "html.parser")
            record_data = {}
            
            # Find all bold tags and extract field-value pairs
            for bold in part_soup.find_all("b"):
                # Get the field name (bold text)
                field_raw = bold.get_text(strip=True)
                
                # Clean field name: remove emojis, special chars, convert to lowercase with underscores
                field_clean = re.sub(r'[^\w\s]', '', field_raw)
                field_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_clean)
                field_clean = field_clean.strip().lower().replace(" ", "_")
                
                # Get the value - try multiple methods
                value = None
                
                # Method 1: Next sibling <code> tag
                code_tag = bold.find_next_sibling("code")
                if code_tag:
                    value = code_tag.get_text(strip=True)
                
                # Method 2: Next sibling text node
                if not value:
                    next_sib = bold.next_sibling
                    if next_sib and isinstance(next_sib, str):
                        value = next_sib.strip()
                        # Remove any HTML tags that might be in the text
                        if '<' in value:
                            value = re.sub(r'<[^>]+>', '', value).strip()
                
                # Method 3: Get all text after bold until next bold or end
                if not value:
                    # Get all following siblings until next <b> or end
                    siblings = []
                    for sibling in bold.next_siblings:
                        if sibling.name == 'b':
                            break
                        if isinstance(sibling, str):
                            siblings.append(sibling.strip())
                        elif sibling.name == 'code':
                            siblings.append(sibling.get_text(strip=True))
                    if siblings:
                        value = ' '.join(siblings).strip()
                        # Clean up
                        value = re.sub(r'<[^>]+>', '', value)
                
                # Method 4: Get parent text and remove field name
                if not value:
                    parent_text = bold.parent.get_text()
                    value = parent_text.replace(field_raw, "").strip()
                    # Extract from code tag if present
                    code_match = re.search(r'<code>(.*?)</code>', parent_text)
                    if code_match:
                        value = code_match.group(1).strip()
                
                # Clean the value
                if value:
                    # Remove any remaining HTML tags
                    value = re.sub(r'<[^>]+>', '', value)
                    value = value.strip()
                    
                    # Store the value
                    if field_clean in record_data:
                        # Handle multiple values (like multiple phones)
                        if not isinstance(record_data[field_clean], list):
                            record_data[field_clean] = [record_data[field_clean]]
                        if value not in record_data[field_clean]:
                            record_data[field_clean].append(value)
                    else:
                        record_data[field_clean] = value
            
            # Only add if we have data
            if record_data:
                all_records.append({
                    "source": source,
                    "data": record_data
                })
    
    return all_records

# =========================
# ALTERNATIVE: PARSE USING ORIGINAL STRING POSITION
# =========================

def parse_leakbase_html_simple(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse using simple string find operations - most reliable
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
        
        # Get the raw HTML string
        html_string = str(text_elem)
        
        # Find all record separators (double br)
        # Split by double br while keeping the content
        record_strings = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_string)
        
        for record_str in record_strings:
            record_str = record_str.strip()
            if not record_str or '<b>' not in record_str:
                continue
            
            # Skip description
            if len(record_str) > 200 and '📞' not in record_str and '🏘️' not in record_str:
                continue
            
            record_data = {}
            
            # Find all pattern: <b>TEXT</b> <code>VALUE</code>
            pattern1 = re.compile(r'<b>(.+?)</b>\s*<code>(.+?)</code>')
            matches1 = pattern1.findall(record_str)
            for field_name, value in matches1:
                field_clean = re.sub(r'[^\w\s]', '', field_name)
                field_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_clean)
                field_clean = field_clean.strip().lower().replace(" ", "_")
                record_data[field_clean] = value.strip()
            
            # Find pattern: <b>TEXT</b> VALUE (without code tag)
            pattern2 = re.compile(r'<b>(.+?)</b>\s*([^<]+?)(?=<br|<b|$)')
            matches2 = pattern2.findall(record_str)
            for field_name, value in matches2:
                field_clean = re.sub(r'[^\w\s]', '', field_name)
                field_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_clean)
                field_clean = field_clean.strip().lower().replace(" ", "_")
                if field_clean not in record_data:
                    record_data[field_clean] = value.strip()
            
            if record_data:
                all_records.append({
                    "source": source,
                    "data": record_data
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
        records_data = parse_leakbase_html_simple(html_content)
        
        # If first method returns empty or has empty values, try second method
        if not records_data or all(not r['data'] for r in records_data):
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
