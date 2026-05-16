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
# UNIVERSAL PARSER - WORKS ON ALL STRUCTURES
# =========================

def clean_field_name(field_raw: str) -> str:
    """Clean field name by removing emojis and special characters"""
    # Remove emojis
    field_clean = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', field_raw)
    # Remove any remaining non-alphanumeric except spaces and underscores
    field_clean = re.sub(r'[^\w\s]', '', field_clean)
    # Replace spaces with underscores and convert to lowercase
    field_clean = field_clean.strip().lower().replace(" ", "_")
    # Remove duplicate underscores
    field_clean = re.sub(r'_+', '_', field_clean)
    return field_clean


def extract_value_from_bold(bold, part_html: str) -> str:
    """Extract value from a bold tag using multiple methods"""
    value = None
    
    # Method 1: Check for <code> tag as next sibling
    code_tag = bold.find_next_sibling("code")
    if code_tag:
        value = code_tag.get_text(strip=True)
    
    # Method 2: Check for text node as next sibling
    if not value:
        next_sib = bold.next_sibling
        if next_sib and isinstance(next_sib, str):
            value = next_sib.strip()
            # Remove any HTML tags that might be in the text
            if '<' in value:
                value = re.sub(r'<[^>]+>', '', value).strip()
    
    # Method 3: Use regex on the part HTML
    if not value:
        bold_text = bold.get_text(strip=True)
        # Escape special regex characters in bold_text
        escaped_bold = re.escape(bold_text)
        # Pattern: <b>bold_text</b> <code>VALUE</code>
        pattern1 = re.compile(rf'<b>{escaped_bold}</b>\s*<code>(.*?)</code>', re.DOTALL)
        match1 = pattern1.search(part_html)
        if match1:
            value = match1.group(1).strip()
        
        # Pattern: <b>bold_text</b> VALUE (until next <br> or <b>)
        if not value:
            pattern2 = re.compile(rf'<b>{escaped_bold}</b>\s*([^<]+?)(?=<br|<b|$)', re.DOTALL)
            match2 = pattern2.search(part_html)
            if match2:
                value = match2.group(1).strip()
                # Remove any remaining HTML tags
                value = re.sub(r'<[^>]+>', '', value).strip()
    
    # Clean the value
    if value:
        # Remove any HTML entities
        value = re.sub(r'&[a-z]+;', '', value)
        # Remove any remaining HTML tags
        value = re.sub(r'<[^>]+>', '', value)
        # Strip whitespace
        value = value.strip()
    
    return value


def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Universal parser - works on all LeakBase HTML structures
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
        
        # Split by double <br> tags to separate records
        parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_string)
        
        for part in parts:
            part = part.strip()
            if not part:
                continue
            
            # Skip the description text (no bold tags or too long)
            if '<b>' not in part:
                continue
            
            # Skip if it's just the description (more than 200 chars and no emoji fields)
            if len(part) > 300 and '📞' not in part and '📩' not in part and '🔑' not in part and '🔐' not in part:
                continue
            
            # Parse this part with BeautifulSoup
            part_soup = BeautifulSoup(part, "html.parser")
            record_data = {}
            
            # Find all bold tags which represent field names
            bold_tags = part_soup.find_all("b")
            
            for bold in bold_tags:
                field_raw = bold.get_text(strip=True)
                if not field_raw:
                    continue
                
                # Clean the field name
                field_clean = clean_field_name(field_raw)
                if not field_clean:
                    continue
                
                # Extract the value
                value = extract_value_from_bold(bold, part)
                
                if value:
                    # Handle multiple values (like multiple passwords, phones, etc.)
                    if field_clean in record_data:
                        if not isinstance(record_data[field_clean], list):
                            record_data[field_clean] = [record_data[field_clean]]
                        if value not in record_data[field_clean]:
                            record_data[field_clean].append(value)
                    else:
                        record_data[field_clean] = value
            
            # Only add if we have data
            if record_data:
                # Clean up - if a field has a list with single item, convert to string
                for key, val in record_data.items():
                    if isinstance(val, list) and len(val) == 1:
                        record_data[key] = val[0]
                
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
