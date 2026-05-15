import os
import re
import asyncio
import json

from flask import Flask, request, jsonify, render_template_string
from telethon import TelegramClient
from telethon.sessions import StringSession
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

API_ID = int(os.getenv("API_ID"))
API_HASH = os.getenv("API_HASH")
SESSION = os.getenv("SESSION")
BOT_USERNAME = os.getenv("BOT_USERNAME")
DOWNLOAD_BUTTON = os.getenv("DOWNLOAD_BUTTON", "Download")

app = Flask(__name__)

client = TelegramClient(StringSession(SESSION), API_ID, API_HASH)

DOWNLOAD_DIR = "downloads"
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# =========================
# HELPER FUNCTIONS
# =========================

def clean_key(key):
    key = re.sub(r'[^\w\s]', '', key)
    key = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', key)
    key = key.strip()
    words = key.split()
    return ' '.join(word.capitalize() for word in words)

def get_field_name(raw_key):
    name = re.sub(r'[\U00010000-\U0010FFFF\u2600-\u27BF]', '', raw_key)
    name = name.strip()
    name = clean_key(name)
    
    mapping = {
        "Email": "Email", "Telephone": "Phone", "Phone": "Phone",
        "Adres": "Address", "Address": "Address",
        "Document number": "DocumentNumber", "Document": "DocumentNumber",
        "Full name": "FullName", "Fullname": "FullName",
        "The name of the father": "FatherName", "Father name": "FatherName",
        "Region": "Region", "Nick": "Nick", "Nickname": "Nick"
    }
    
    for key, value in mapping.items():
        if key.lower() in name.lower():
            return value
    return name.replace(" ", "")

def parse_html_records(html_content):
    soup = BeautifulSoup(html_content, "html.parser")
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
        
        if "---" in line or "===" in line or line.startswith("-----------------------------------"):
            if current_record:
                records.append(current_record)
                current_record = {}
            i += 1
            continue
        
        matched = False
        for field_key, pattern in field_patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                clean_key = field_key.replace("_alt", "")
                
                output_map = {
                    "email": "Email", "phone": "Phone", "address": "Address",
                    "document": "DocumentNumber", "fullname": "FullName",
                    "father": "FatherName", "region": "Region", "nick": "Nick"
                }
                output_key = output_map.get(clean_key, clean_key.capitalize())
                
                if output_key in current_record:
                    if isinstance(current_record[output_key], list):
                        current_record[output_key].append(value)
                    else:
                        current_record[output_key] = [current_record[output_key], value]
                else:
                    current_record[output_key] = value
                matched = True
                break
        
        if not matched:
            kv_match = re.match(r"^([A-Za-z\s]+):\s*(.+)", line)
            if kv_match:
                key = kv_match.group(1).strip()
                value = kv_match.group(2).strip()
                key_lower = key.lower()
                
                if "email" in key_lower: output_key = "Email"
                elif "phone" in key_lower or "telephone" in key_lower: output_key = "Phone"
                elif "address" in key_lower or "adres" in key_lower: output_key = "Address"
                elif "document" in key_lower: output_key = "DocumentNumber"
                elif "full name" in key_lower: output_key = "FullName"
                elif "father" in key_lower: output_key = "FatherName"
                elif "region" in key_lower: output_key = "Region"
                elif "nick" in key_lower: output_key = "Nick"
                else: output_key = key.capitalize()
                
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

def parse_line(line):
    line = line.strip()
    if not line:
        return None, None
    
    emoji_pattern = re.compile(r'^([\U00010000-\U0010FFFF\u2600-\u27BF]+)\s*(.+?):\s*(.*)$')
    match = emoji_pattern.match(line)
    
    if match:
        key_raw = match.group(2)
        value = match.group(3).strip()
        return get_field_name(key_raw), value
    
    if line.startswith('📞'):
        phone_match = re.search(r'(\d+)', line)
        if phone_match:
            return "Phone", phone_match.group(1)
    
    if line.startswith('📩'):
        email_match = re.search(r'([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', line)
        if email_match:
            return "Email", email_match.group(1)
    
    return None, None

def parse_text_records(text):
    if not text:
        return []
    
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
# TELEGRAM CLIENT EVENT LOOP
# =========================

def run_async(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

# =========================
# FLASK ROUTES
# =========================

@app.route('/')
def home():
    return render_template_string('''
    <html>
        <head><title>Telegram HTML Scraper API</title></head>
        <body style="font-family: Arial; padding: 40px;">
            <h2>Telegram HTML Scraper API</h2>
            <form action="/search" method="get">
                <input type="text" name="q" placeholder="Enter query" 
                       style="width:300px; height:40px; padding:10px;">
                <button type="submit" style="height:40px;">Search</button>
            </form>
        </body>
    </html>
    ''')

@app.route('/search')
def search_get():
    q = request.args.get('q')
    if not q:
        return jsonify({"status": False, "error": "Missing 'q' parameter"})
    return run_async(do_search(q))

@app.route('/search', methods=['POST'])
def search_post():
    data = request.get_json()
    if not data:
        return jsonify({"status": False, "error": "Invalid JSON"})
    q = data.get('message')
    if not q:
        return jsonify({"status": False, "error": "Missing 'message' field"})
    return run_async(do_search(q))

async def do_search(message):
    try:
        print(f"Query: {message}")
        
        await client.start()
        
        sent = await client.send_message(BOT_USERNAME, message)
        
        target_message = None
        for i in range(15):
            await asyncio.sleep(2)
            messages = await client.get_messages(BOT_USERNAME, limit=10)
            
            for msg in messages:
                if msg.out or not msg.message or msg.id <= sent.id:
                    continue
                if msg.message.strip() == message.strip():
                    continue
                target_message = msg
                break
            
            if target_message:
                break
        
        if not target_message:
            return {"status": False, "error": "No response from bot"}
        
        file_path = None
        
        if target_message.buttons:
            for row in target_message.buttons:
                for button in row:
                    if DOWNLOAD_BUTTON.lower() in button.text.lower():
                        await button.click()
                        break
            
            for i in range(30):
                await asyncio.sleep(2)
                latest = await client.get_messages(BOT_USERNAME, limit=5)
                for msg in latest:
                    if msg.file and msg.id > target_message.id:
                        file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                        break
                if file_path:
                    break
        
        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            records = parse_html_records(html_content)
            return {"status": True, "query": message, "record_count": len(records), "data": records}
        
        if target_message.message:
            records = parse_text_records(target_message.message)
            if records:
                return {"status": True, "query": message, "record_count": len(records), "data": records, "source": "text_message"}
            return {"status": False, "error": "No HTML file received", "raw_message": target_message.message[:500]}
        
        return {"status": False, "error": "Could not extract any data"}
        
    except Exception as e:
        return {"status": False, "error": str(e)}

# =========================
# RUN
# =========================

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
