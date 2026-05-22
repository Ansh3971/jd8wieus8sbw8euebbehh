import os
import re
import asyncio
import time
import random
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
from fastapi import FastAPI
from fastapi.responses import JSONResponse, HTMLResponse
from dotenv import load_dotenv
from telethon import TelegramClient
from telethon.sessions import StringSession
from bs4 import BeautifulSoup

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
# FIELD MAPPING (SPELLING FIXED & SWAPPED)
# =========================

def get_json_key(field_tag: str) -> str:
    field_tag = field_tag.strip()
    if "📞Telephone" in field_tag or "📞Phone" in field_tag or "📞Mobile" in field_tag:
        return "Phone"
    if "🏘️Adres" in field_tag or "🏘️Address" in field_tag:
        return "Address"
    if "📩Email" in field_tag or "📩E-mail" in field_tag:
        return "Email"
    if "🃏Document number" in field_tag or "🃏Document No" in field_tag:
        return "DocumentNumber"
    
    # --- EXCHANGE LOGIC APPLIED HERE ---
    if "👤Full name" in field_tag or "👤Name" in field_tag:
        return "FatherName"
    if "👨The name of the father" in field_tag or "👨Father name" in field_tag:
        return "FullName"
    # -----------------------------------
    
    if "🗺️Region" in field_tag or "🗺️Location" in field_tag or "🗺️ Region" in field_tag:
        return "Region"
    if "👤Nick" in field_tag or "👤Nickname" in field_tag:
        return "Nick"
    if "📖Passport number" in field_tag:
        return "PassportNumber"
    if "🔐Encrypted password" in field_tag:
        return "EncryptedPassword"
    if "🔑Password" in field_tag:
        return "Password"
    if "📆Date" in field_tag or "📆The date of registration" in field_tag:
        return "RegistrationDate"
    if "📆Last activity" in field_tag:
        return "LastActivity"
    if "🎂Date of birth" in field_tag:
        return "DOB"
    if "🌃City" in field_tag:
        return "City"
    if "🇺🇸Stat" in field_tag:
        return "State"
    if "🏤Postal code" in field_tag:
        return "PostalCode"
    if "🎯IP" in field_tag:
        return "IP"
    if "🚻Gender" in field_tag:
        return "Gender"
    if "👴Age" in field_tag:
        return "Age"
    if "📍District" in field_tag:
        return "District"
    if "🔗Link" in field_tag:
        return "Link"
    if "🏷️ login" in field_tag:
        return "Login"
    if "📰Category" in field_tag:
        return "Category"
    if "🗾Country" in field_tag:
        return "Country"
    if "⬆Level" in field_tag:
        return "Level"
    if "🏫Education" in field_tag:
        return "Education"
    if "👤Surname" in field_tag:
        return "Surname"
    if "💶Currency" in field_tag:
        return "Currency"
    if "💸Sum" in field_tag:
        return "Sum"
    return None

def add_to_record(record: Dict, key: str, value: str):
    if key == "Address" and value.replace(" ", "").isdigit():
        return
    
    # Handle multiple phones/addresses properly (e.g. Phone, Phone2, Phone3)
    if key in record:
        count = 2
        while f"{key}{count}" in record:
            count += 1
        record[f"{key}{count}"] = value
    else:
        record[key] = value

# =========================
# MAIN PARSER (FLAT CLEAN ARRAY)
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_content, "lxml")
    all_records = []

    blocks = soup.find_all("div", class_="block")
    for block in blocks:
        source = "Unknown"
        title_elem = block.find("div", class_="block-title")
        if title_elem:
            source = title_elem.get_text(strip=True)

        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue

        html_text = str(text_elem)
        parts = re.split(r'<br\s*/?\s*>\s*<br\s*/?\s*>', html_text)

        for part in parts:
            part = part.strip()
            if not part or '<b>' not in part:
                continue

            soup_part = BeautifulSoup(part, "lxml")
            
            # Start fresh record with Source at the top of the object
            record = {"Source": source}

            for bold in soup_part.find_all("b"):
                field_tag = bold.get_text(strip=True)
                json_key = get_json_key(field_tag)
                if not json_key:
                    continue

                raw_text = ""
                for sibling in bold.next_siblings:
                    if getattr(sibling, 'name', None) in ['b', 'br']:
                        break
                    if getattr(sibling, 'name', None) == 'code':
                        raw_text += sibling.get_text(strip=True)
                    elif isinstance(sibling, str):
                        raw_text += sibling
                
                value = raw_text.strip()
                if value.startswith(":"):
                    value = value[1:].strip()

                if value:
                    add_to_record(record, json_key, value)

            # Check if record has more data besides just "Source"
            if len(record) > 1:
                all_records.append(record)

    return all_records

# =========================
# DYNAMIC WATERMARK
# =========================

def get_dynamic_watermark():
    keys = ["developer", "powered_by", "api_author", "system_dev", "licensed_to", "created_by"]
    values = ["@ProPortalx", "API by @ProPortalx", "Dev: @ProPortalx", "ProPortalx"]
    return random.choice(keys), random.choice(values)

# =========================
# API ENDPOINTS
# =========================

@app.post("/search")
async def search(data: dict):
    start_time = time.time()
    try:
        message = data.get("message", "")
        if not message:
            return JSONResponse(content={"status": False, "error": "message required"})

        print(f"\n=== SEARCH: {message} ===")
        sent = await client.send_message(BOT_USERNAME, message)
        
        file_path = None
        html_content = None
        button_clicked = False
        
        # High speed polling
        for attempt in range(300):
            messages = await client.get_messages(BOT_USERNAME, limit=5)
            
            for msg in messages:
                if msg.out or msg.id <= sent.id:
                    continue
                
                if msg.file:
                    file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                    break
                
                if msg.message and not file_path:
                    html_match = re.search(r'(<!DOCTYPE html>|<html>.*?</html>)', msg.message, re.DOTALL | re.IGNORECASE)
                    if html_match:
                        html_content = html_match.group(0)
                        break

                if msg.buttons and not button_clicked:
                    for row in msg.buttons:
                        for btn in row:
                            if DOWNLOAD_BUTTON.lower() in btn.text.lower():
                                await btn.click()
                                button_clicked = True
                                break
                        if button_clicked:
                            break

            if file_path or html_content:
                break
                
            await asyncio.sleep(0.2)

        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            os.remove(file_path)

        if html_content:
            flat_records = parse_leakbase_html(html_content)
            
            # HIDDEN LAYER WATERMARK (Proxies can't filter this easily)
            if flat_records:
                flat_records[0]["_api_by"] = "@ProPortalx"

            # Calculate Response Time & IST Timestamp
            process_time = round(time.time() - start_time, 2)
            ist = timezone(timedelta(hours=5, minutes=30))
            indian_time = datetime.now(ist).strftime("%Y-%m-%dT%H:%M:%S.%f%z")
            indian_time = indian_time[:-2] + ":" + indian_time[-2:]

            # DYNAMIC KEY WATERMARK
            wm_key, wm_value = get_dynamic_watermark()

            content = {
                "status": True,
                "query": message,
                "record_count": len(flat_records),
                "timestamp": indian_time,
                "response_time": process_time,
                "data": flat_records
            }
            
            content[wm_key] = wm_value

            # HEADER WATERMARK
            return JSONResponse(
                content=content,
                headers={"X-Developed-By": "@ProPortalx"}
            )

        return JSONResponse(content={"status": False, "error": "No file received or download failed"})

    except Exception as e:
        print(f"ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        return JSONResponse(content={
            "status": False, 
            "error": str(e),
            "response_time": round(time.time() - start_time, 2)
        })

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
                pre { background: #f5f5f5; padding: 15px; border-radius: 4px; overflow-x: auto; font-size: 12px; }
                .result { margin-top: 20px; }
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
