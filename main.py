import os
import re
import asyncio

from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from telethon import TelegramClient
from telethon.sessions import StringSession

from bs4 import BeautifulSoup

from dotenv import load_dotenv

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

app = FastAPI(
    title="Telegram HTML Scraper API"
)

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
# STARTUP
# =========================

@app.on_event("startup")
async def startup():
    await client.start()
    print("Telegram Client Connected")

# =========================
# SHUTDOWN
# =========================

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()

# =========================
# CLEAN KEY
# =========================

def clean_key(key):
    key = re.sub(r'[^\w\s]', '', key)
    key = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', key)
    key = key.strip()
    words = key.split()
    return ' '.join(word.capitalize() for word in words)

# =========================
# GET FIELD NAME
# =========================

def get_field_name(raw_key):
    name = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', raw_key)
    name = name.strip()
    name = clean_key(name)
    
    mapping = {
        "Email": "Email",
        "Telephone": "Phone",
        "Phone": "Phone",
        "Adres": "Address",
        "Address": "Address",
        "Document number": "DocumentNumber",
        "Document": "DocumentNumber",
        "Full name": "FullName",
        "Fullname": "FullName",
        "The name of the father": "FatherName",
        "Father name": "FatherName",
        "Region": "Region",
        "Nick": "Nick",
        "Nickname": "Nick"
    }
    
    for key, value in mapping.items():
        if key.lower() in name.lower():
            return value
    
    return name.replace(" ", "")

# =========================
# PARSE LINE FROM TEXT
# =========================

def parse_line(line):
    """Extract field name and value from a line with emoji"""
    line = line.strip()
    if not line:
        return None, None
    
    # Pattern: emoji(s) + field_name: value
    emoji_pattern = re.compile(r'^([\U00010000-\U0010FFFF\u2600-\u27BF]+)\s*(.+?):\s*(.*)$')
    match = emoji_pattern.match(line)
    
    if match:
        key_raw = match.group(2)
        value = match.group(3).strip()
        field_name = get_field_name(key_raw)
        return field_name, value
    
    # Handle Telephone/Email without colon
    if line.startswith('📞'):
        phone_match = re.search(r'(\d+)', line)
        if phone_match:
            return "Phone", phone_match.group(1)
    
    if line.startswith('📩'):
        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line)
        if email_match:
            return "Email", email_match.group(1)
    
    return None, None

# =========================
# PARSE TEXT RECORDS (FALLBACK)
# =========================

def parse_text_records(text):
    """Parse records from plain text if HTML extraction fails"""
    if not text:
        return []
    
    # Remove truncation note
    if "Some data did not fit this message" in text:
        text = text.split("Some data did not fit this message")[0]
    
    lines = text.splitlines()
    
    records = []
    current_record = {}
    i = 0
    
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            if current_record:
                records.append(current_record)
                current_record = {}
            i += 1
            continue
        
        field_name, value = parse_line(line)
        
        if field_name and value:
            if field_name in current_record:
                count = 2
                while f"{field_name}{count}" in current_record:
                    count += 1
                current_record[f"{field_name}{count}"] = value
            else:
                current_record[field_name] = value
        else:
            if current_record and line:
                if "Address" in current_record:
                    current_record["Address"] = current_record["Address"] + " " + line
                elif len(current_record) > 0:
                    last_key = list(current_record.keys())[-1]
                    current_record[last_key] = current_record[last_key] + " " + line
        
        i += 1
    
    if current_record:
        records.append(current_record)
    
    return [r for r in records if r]

# =========================
# HTML PARSER - EXTRACT RECORDS FROM HTML
# =========================

def parse_html_records(html_content):
    """Extract records from downloaded HTML file"""
    soup = BeautifulSoup(html_content, "html.parser")
    
    # Get all text lines
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    records = []
    current_record = {}
    
    field_patterns = {
        "email": r"^Email:\s*(.+)",
        "phone": r"^Telephone:\s*(.+)",
        "phone_alt": r"^Phone:\s*(.+)",
        "address": r"^Adres:\s*(.+)",
        "address_alt": r"^Address:\s*(.+)",
        "document": r"^Document number:\s*(.+)",
        "fullname": r"^Full name:\s*(.+)",
        "father": r"^The name of the father:\s*(.+)",
        "region": r"^Region:\s*(.+)",
        "nick": r"^Nick:\s*(.+)",
    }
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Skip separator lines
        if "---" in line or "===" in line or line.startswith("-----------------------------------"):
            if current_record:
                records.append(current_record)
                current_record = {}
            i += 1
            continue
        
        matched = False
        
        # Try to match field patterns
        for field_key, pattern in field_patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                clean_key = field_key.replace("_alt", "")
                
                # Map to output field names
                if clean_key == "email":
                    output_key = "Email"
                elif clean_key == "phone":
                    output_key = "Phone"
                elif clean_key == "address":
                    output_key = "Address"
                elif clean_key == "document":
                    output_key = "DocumentNumber"
                elif clean_key == "fullname":
                    output_key = "FullName"
                elif clean_key == "father":
                    output_key = "FatherName"
                elif clean_key == "region":
                    output_key = "Region"
                elif clean_key == "nick":
                    output_key = "Nick"
                else:
                    output_key = clean_key.capitalize()
                
                # Handle multiple values
                if output_key in current_record:
                    if isinstance(current_record[output_key], list):
                        current_record[output_key].append(value)
                    else:
                        current_record[output_key] = [current_record[output_key], value]
                else:
                    current_record[output_key] = value
                matched = True
                break
        
        # Handle plain key: value pattern
        if not matched:
            kv_match = re.match(r"^([A-Za-z\s]+):\s*(.+)", line)
            if kv_match:
                key = kv_match.group(1).strip()
                value = kv_match.group(2).strip()
                
                # Map common keys
                key_lower = key.lower()
                if "email" in key_lower:
                    output_key = "Email"
                elif "phone" in key_lower or "telephone" in key_lower:
                    output_key = "Phone"
                elif "address" in key_lower or "adres" in key_lower:
                    output_key = "Address"
                elif "document" in key_lower:
                    output_key = "DocumentNumber"
                elif "full name" in key_lower:
                    output_key = "FullName"
                elif "father" in key_lower:
                    output_key = "FatherName"
                elif "region" in key_lower:
                    output_key = "Region"
                elif "nick" in key_lower:
                    output_key = "Nick"
                else:
                    output_key = key.capitalize()
                
                if output_key in current_record:
                    if isinstance(current_record[output_key], list):
                        current_record[output_key].append(value)
                    else:
                        current_record[output_key] = [current_record[output_key], value]
                else:
                    current_record[output_key] = value
                matched = True
        
        i += 1
    
    if current_record:
        records.append(current_record)
    
    return records

# =========================
# MAIN SEARCH - CLICK BUTTON & DOWNLOAD HTML
# =========================

@app.post("/search")
async def search(data: Query):
    try:
        print("\n========== NEW REQUEST ==========")
        print("Query:", data.message)
        
        # Send message to bot
        sent = await client.send_message(
            BOT_USERNAME,
            data.message
        )
        
        print("Message Sent")
        
        # Wait for bot response with button
        target_message = None
        
        for i in range(15):
            print(f"\nChecking Messages Attempt {i+1}")
            await asyncio.sleep(2)
            
            messages = await client.get_messages(
                BOT_USERNAME,
                limit=10
            )
            
            for msg in messages:
                if msg.out:
                    continue
                if not msg.message and not msg.buttons:
                    continue
                if msg.id <= sent.id:
                    continue
                
                target_message = msg
                print("\nFOUND BOT REPLY")
                if msg.message:
                    print(msg.message[:200] + "...")
                if msg.buttons:
                    print("Has buttons:", msg.buttons)
                break
            
            if target_message:
                break
        
        if not target_message:
            return {
                "status": False,
                "error": "No response from bot"
            }
        
        # Try to click download button
        file_path = None
        
        if target_message.buttons:
            print("\nFound buttons, attempting to click...")
            
            # Find button with DOWNLOAD_BUTTON text
            clicked = False
            for row in target_message.buttons:
                for button in row:
                    if DOWNLOAD_BUTTON.lower() in button.text.lower():
                        print(f"Clicking button: {button.text}")
                        await button.click()
                        clicked = True
                        break
                if clicked:
                    break
            
            # Try first button if not found
            if not clicked and target_message.buttons and target_message.buttons[0]:
                print(f"Trying first button: {target_message.buttons[0][0].text}")
                await target_message.buttons[0][0].click()
            
            # Wait for file message
            print("\nWaiting for file...")
            for i in range(30):
                await asyncio.sleep(2)
                latest = await client.get_messages(BOT_USERNAME, limit=5)
                
                for msg in latest:
                    if msg.file and msg.id > target_message.id:
                        print(f"\nFile found: {msg.file.name if msg.file.name else 'unnamed'}")
                        file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                        print(f"Downloaded to: {file_path}")
                        break
                
                if file_path:
                    break
        
        # If no file from button, try direct HTML extraction from message
        if not file_path and target_message.message:
            print("\nNo file found, trying direct HTML from message...")
            html_match = re.search(r'(<!DOCTYPE html>|<html>.*?</html>)', target_message.message, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(0)
                temp_path = os.path.join(DOWNLOAD_DIR, "temp_message.html")
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                file_path = temp_path
                print("Extracted HTML from message")
        
        # Parse HTML file if downloaded
        if file_path and os.path.exists(file_path):
            print(f"\nParsing file: {file_path}")
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            
            records = parse_html_records(html_content)
            
            # Clean up temp file if needed
            if file_path == os.path.join(DOWNLOAD_DIR, "temp_message.html"):
                os.remove(file_path)
            
            return {
                "status": True,
                "query": data.message,
                "source": "html_file",
                "record_count": len(records),
                "data": records
            }
        
        # Fallback: parse text from message
        if target_message.message:
            print("\nFalling back to text parsing")
            records = parse_text_records(target_message.message)
            
            return {
                "status": True,
                "query": data.message,
                "source": "text_message",
                "record_count": len(records),
                "data": records
            }
        
        return {
            "status": False,
            "error": "Could not extract any data"
        }
        
    except Exception as e:
        print("\nERROR:")
        print(str(e))
        import traceback
        traceback.print_exc()
        return {
            "status": False,
            "error": str(e)
        }

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
    <html>
        <head>
            <title>Telegram HTML Scraper API</title>
        </head>
        <body style="font-family: Arial; padding: 40px;">
            <h2>Telegram HTML Scraper API</h2>
            <form action="/test" method="get">
                <input type="text" name="q" placeholder="Enter query" 
                       style="width:300px; height:40px; padding:10px;">
                <button type="submit" style="height:40px;">Search</button>
            </form>
        </body>
    </html>
    """

# =========================
# RUN
# =========================
# uvicorn main:app --host 0.0.0.0 --port 8000 --reload
