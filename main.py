import os
import re
import asyncio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from bs4 import BeautifulSoup
from typing import List, Dict, Any, Optional

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
# REQUEST MODEL
# =========================

class Query(BaseModel):
    message: str

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
# COMPLETE FIELD MAPPING
# =========================

FIELD_MAPPING = {
    # Phone/Contact
    "📞Telephone": "phones",
    "📞Phone": "phones",
    "📞Mobile": "phones",
    "📞Working phone": "phones",
    "📞Mobile phone": "phones",
    "📞Telephone:": "phones",
    "☎️Domestic phone": "phones",
    
    # Address
    "🏘️Adres": "addresses",
    "🏘️Address": "addresses",
    "🏘️Adres:": "addresses",
    "📍Location": "location",
    
    # Email
    "📩Email": "emails",
    "📩E-mail": "emails",
    
    # Documents
    "🃏Document number": "document_number",
    "🃏Document No": "document_number",
    "📖Passport number": "passport_number",
    
    # Personal info
    "👤Full name": "full_name",
    "👤Name": "full_name",
    "👤Name:": "full_name",
    "👨The name of the father": "father_name",
    "👨Father name": "father_name",
    "🗺️Region": "region",
    "🗺️Location": "region",
    "👤Nick": "nick",
    "👤Nickname": "nick",
    "👤Nick:": "nick",
    
    # Authentication
    "🔐Encrypted password": "encrypted_password",
    "🔑Password": "password",
    
    # Dates
    "📆Date": "date",
    "📆Last activity": "last_activity",
    "📆The date of registration": "registration_date",
    "🎂Date of birth": "dob",
    "🎂Year of birth": "birth_year",
    "🎂Month of birth": "birth_month",
    
    # Location/Geo
    "🌃City": "city",
    "🌃Cities": "city",
    "🇺🇸Stat": "state",
    "🏤Postal code": "postal_code",
    "🌐Latitude": "latitude",
    "🌐Longitude": "longitude",
    
    # Network
    "🎯IP": "ip",
    "🆔VK ID": "vk_id",
    
    # Demographics
    "🚻Gender": "gender",
    "👴Age": "age",
    "📍District": "district",
    
    # Other common fields
    "🏷️ login": "login",
    "🔗Link": "link",
    "📰Category": "category",
    "🗾Country": "country",
    "⬆Level": "level",
    "🏫Education": "education",
    "🏢The name of the company": "company",
    "👷Job": "job",
    "💸Sum": "amount",
    "💶Currency": "currency",
    "🚘Car number": "car_number",
    "🚔︎Vin": "vin",
    "📡Mobile operator": "mobile_operator",
    "🏷Tags": "tags",
    "📢Channel identifier": "channel_id",
    "🗝ID": "user_id",
    "🔢SSN": "ssn",
    "👪Relatives": "relatives",
    "💬Comment": "comment_url",
    "📝Text": "comment_text",
    "❤️Likes": "likes",
}

# =========================
# ROBUST HTML PARSER
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    """
    Parse LeakBase HTML and extract structured records
    Works with ALL LeakBase HTML files regardless of structure
    """
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []
    
    # Find all block elements
    blocks = soup.find_all("div", class_="block")
    if not blocks:
        blocks = soup.find_all("div", attrs={"id": re.compile(r'^p\d+')})
    if not blocks:
        blocks = soup.find_all("section")
    
    for block in blocks:
        # Extract source title
        source = "Unknown"
        title_elem = block.find("div", class_="block-title")
        if not title_elem:
            title_elem = block.find("h1") or block.find("h2") or block.find("h3") or block.find("b")
        
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            # Clean emoji and special chars
            title_text = re.sub(r'[^\w\s\.\-]', '', title_text)
            if title_text and len(title_text) < 100:
                source = title_text.strip()
        
        # Get block text content
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            text_elem = block
        
        # Get all lines
        text = text_elem.get_text(separator="\n", strip=True)
        lines = text.split("\n")
        
        # Skip description (first few long lines without field markers)
        records_in_block = []
        current_record = {"source": source}
        description_skipped = False
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # Skip long description paragraphs (usually at block start)
            if not description_skipped and len(line) > 100 and ":" not in line:
                i += 1
                continue
            description_skipped = True
            
            # Check for record separator (double blank line or pattern)
            if line == "---" or line == "===" or line.startswith("-----------------------------------"):
                if current_record and len(current_record) > 1:
                    records_in_block.append(current_record)
                current_record = {"source": source}
                i += 1
                continue
            
            # Try to parse field from line
            parsed = False
            
            # Method 1: Direct field match with emoji
            for emoji_field, json_key in FIELD_MAPPING.items():
                if line.startswith(emoji_field) or (emoji_field in line and ":" in line[:20]):
                    # Extract value after colon
                    if ":" in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            value = parts[1].strip()
                            # Clean HTML tags
                            value = re.sub(r'<[^>]+>', '', value)
                            value = re.sub(r'</?code>', '', value)
                            value = value.strip()
                            
                            if value and value not in ["None", "null", ""]:
                                # Handle multi-value fields
                                if json_key in ["phones", "addresses", "emails"]:
                                    if json_key not in current_record:
                                        current_record[json_key] = []
                                    if value not in current_record[json_key]:
                                        current_record[json_key].append(value)
                                else:
                                    # For single fields, keep first occurrence
                                    if json_key not in current_record:
                                        current_record[json_key] = value
                            parsed = True
                            break
            
            # Method 2: Parse from HTML bold tags
            if not parsed:
                soup_line = BeautifulSoup(line, "html.parser")
                bold_tag = soup_line.find("b")
                if bold_tag:
                    bold_text = bold_tag.get_text(strip=True)
                    for emoji_field, json_key in FIELD_MAPPING.items():
                        if emoji_field in bold_text or emoji_field.replace("📞", "") in bold_text:
                            # Get value from next sibling or parent
                            value = ""
                            next_sib = bold_tag.next_sibling
                            if next_sib:
                                value = str(next_sib).strip()
                            elif bold_tag.parent:
                                # Extract after bold text
                                parent_text = bold_tag.parent.get_text()
                                value = parent_text.replace(bold_text, "").strip()
                            
                            value = re.sub(r'<[^>]+>', '', value)
                            value = value.strip()
                            
                            if value and value not in ["None", "null", ""]:
                                if json_key in ["phones", "addresses", "emails"]:
                                    if json_key not in current_record:
                                        current_record[json_key] = []
                                    if value not in current_record[json_key]:
                                        current_record[json_key].append(value)
                                else:
                                    if json_key not in current_record:
                                        current_record[json_key] = value
                            parsed = True
                            break
            
            # Method 3: Simple key: value pattern
            if not parsed:
                kv_match = re.match(r'^([A-Za-z\s]+):\s*(.+)$', line)
                if kv_match:
                    key = kv_match.group(1).strip().lower()
                    value = kv_match.group(2).strip()
                    value = re.sub(r'<[^>]+>', '', value)
                    
                    if value and value not in ["None", "null", ""]:
                        # Map common keys
                        key_mapping = {
                            "name": "full_name", "email": "emails", "phone": "phones",
                            "telephone": "phones", "address": "addresses", "adres": "addresses",
                            "password": "password", "encrypted password": "encrypted_password",
                            "city": "city", "state": "state", "country": "country",
                            "gender": "gender", "age": "age", "ip": "ip", "link": "link",
                            "nick": "nick", "nickname": "nick", "full name": "full_name"
                        }
                        output_key = key_mapping.get(key, key.replace(" ", "_"))
                        
                        if output_key in ["phones", "addresses", "emails"]:
                            if output_key not in current_record:
                                current_record[output_key] = []
                            if value not in current_record[output_key]:
                                current_record[output_key].append(value)
                        else:
                            if output_key not in current_record:
                                current_record[output_key] = value
            
            i += 1
        
        # Add last record from this block
        if current_record and len(current_record) > 1:
            records_in_block.append(current_record)
        
        # Extend all records
        all_records.extend(records_in_block)
    
    # Post-process: clean empty values and convert single-element arrays
    for record in all_records:
        for key, value in list(record.items()):
            if isinstance(value, list) and len(value) == 1:
                record[key] = value[0]
            elif isinstance(value, list) and len(value) == 0:
                del record[key]
    
    return all_records

# =========================
# MAIN SEARCH FUNCTION
# =========================

@app.post("/search")
async def search(data: Query):
    try:
        print(f"\n=== SEARCH: {data.message} ===")

        # Send message to bot
        sent_message = await client.send_message(BOT_USERNAME, data.message)
        print("Message sent")

        # Wait for bot reply
        await asyncio.sleep(3)

        # Get bot reply
        messages = await client.get_messages(BOT_USERNAME, limit=5)
        
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
                await asyncio.sleep(1)
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
            if "temp_" in file_path:
                os.remove(file_path)
            
            return {
                "status": True,
                "query": data.message,
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
# BROWSER SEARCH (GET)
# =========================

@app.get("/search")
async def search_get(q: str):
    return await search(Query(message=q))

# =========================
# TEST ENDPOINT
# =========================

@app.get("/test")
async def test(q: str):
    return await search(Query(message=q))

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
            </style>
        </head>
        <body>
            <h2>🔍 Telegram LeakBase Parser API</h2>
            <p>Enter query (phone number, email, or name) to search in LeakBase bot</p>
            <form onsubmit="event.preventDefault(); search();">
                <input type="text" id="query" placeholder="e.g., 919999988888" style="width: 70%;">
                <button type="submit">Search</button>
            </form>
            <div id="result" class="result"></div>
            
            <script>
                async function search() {
                    const query = document.getElementById('query').value;
                    if (!query) return;
                    
                    const resultDiv = document.getElementById('result');
                    resultDiv.innerHTML = '<p>Loading... This may take 10-20 seconds...</p>';
                    
                    try {
                        const response = await fetch(`/search?q=${encodeURIComponent(query)}`);
                        const data = await response.json();
                        
                        if (data.status) {
                            resultDiv.innerHTML = `
                                <h3>✅ Success</h3>
                                <p><strong>Query:</strong> ${data.query}</p>
                                <p><strong>Records found:</strong> ${data.record_count}</p>
                                <details>
                                    <summary>View Data (${data.record_count} records)</summary>
                                    <pre>${JSON.stringify(data.data, null, 2)}</pre>
                                </details>
                            `;
                        } else {
                            resultDiv.innerHTML = `<p class="error">❌ Error: ${data.error}</p>`;
                            if (data.raw_message_preview) {
                                resultDiv.innerHTML += `<details><summary>Raw Response</summary><pre>${data.raw_message_preview}</pre></details>`;
                            }
                        }
                    } catch (err) {
                        resultDiv.innerHTML = `<p class="error">❌ Request failed: ${err.message}</p>`;
                    }
                }
            </script>
        </body>
    </html>
    """

# =========================
# REQUIREMENTS.TXT
# =========================

# fastapi==0.104.1
# uvicorn[standard]==0.24.0
# telethon==1.34.0
# beautifulsoup4==4.12.2
# python-dotenv==1.0.0
# pydantic==1.10.13

# =========================
# RUN: uvicorn main:app --host 0.0.0.0 --port 8000 --reload
# =========================
