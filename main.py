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
# FIELD MAPPING
# =========================

def get_json_key(field_tag: str) -> str:
    field_tag = field_tag.strip()
    if "📞Telephone" in field_tag or "📞Phone" in field_tag or "📞Mobile" in field_tag:
        return "telephone"
    if "🏘️Adres" in field_tag or "🏘️Address" in field_tag:
        return "adres"
    if "📩Email" in field_tag or "📩E-mail" in field_tag:
        return "email"
    if "🃏Document number" in field_tag or "🃏Document No" in field_tag:
        return "document_number"
    if "👤Full name" in field_tag or "👤Name" in field_tag:
        return "full_name"
    if "👨The name of the father" in field_tag or "👨Father name" in field_tag:
        return "the_name_of_the_father"
    if "🗺️Region" in field_tag or "🗺️Location" in field_tag or "🗺️ Region" in field_tag:
        return "region"
    if "👤Nick" in field_tag or "👤Nickname" in field_tag:
        return "nick"
    if "📖Passport number" in field_tag:
        return "passport_number"
    if "🔐Encrypted password" in field_tag:
        return "encrypted_password"
    if "🔑Password" in field_tag:
        return "password"
    if "📆Date" in field_tag or "📆The date of registration" in field_tag:
        return "the_date_of_registration"
    if "📆Last activity" in field_tag:
        return "last_activity"
    if "🎂Date of birth" in field_tag:
        return "dob"
    if "🌃City" in field_tag:
        return "city"
    if "🇺🇸Stat" in field_tag:
        return "state"
    if "🏤Postal code" in field_tag:
        return "postal_code"
    if "🎯IP" in field_tag:
        return "ip"
    if "🚻Gender" in field_tag:
        return "gender"
    if "👴Age" in field_tag:
        return "age"
    if "📍District" in field_tag:
        return "district"
    if "🔗Link" in field_tag:
        return "link"
    if "🏷️ login" in field_tag:
        return "login"
    if "📰Category" in field_tag:
        return "category"
    if "🗾Country" in field_tag:
        return "country"
    if "⬆Level" in field_tag:
        return "level"
    if "🏫Education" in field_tag:
        return "education"
    if "👤Surname" in field_tag:
        return "surname"
    if "💶Currency" in field_tag:
        return "currency"
    if "💸Sum" in field_tag:
        return "sum"
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
# MAIN PARSER (FIXED)
# =========================

def parse_leakbase_html(html_content: str) -> List[Dict[str, Any]]:
    soup = BeautifulSoup(html_content, "html.parser")
    all_records = []

    blocks = soup.find_all("div", class_="block")
    for block in blocks:
        # Get source title
        source = "Unknown"
        title_elem = block.find("div", class_="block-title")
        if title_elem:
            source = title_elem.get_text(strip=True)

        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue

        record = {}
        for bold in text_elem.find_all("b"):
            field_tag = bold.get_text(strip=True)
            json_key = get_json_key(field_tag)
            
            if not json_key:
                continue

            value = None
            code_tag = bold.find_next_sibling("code")
            
            # Extract Value Correctly
            if code_tag and bold.next_element == code_tag.previous_element:
                value = code_tag.get_text(strip=True)
            else:
                next_sibling = bold.next_sibling
                if next_sibling and isinstance(next_sibling, str):
                    raw_text = next_sibling.strip()
                    br_pos = raw_text.find('<br')
                    if br_pos != -1:
                        raw_text = raw_text[:br_pos]
                    value = raw_text.lstrip(':').strip()

            if value:
                add_to_record(record, json_key, value)

        if record:
            all_records.append({
                "source": source,
                "data": record
            })

    return all_records

# =========================
# API ENDPOINTS
# =========================

@app.post("/search")
async def search(data: dict):
    try:
        message = data.get("message", "")
        if not message:
            return {"status": False, "error": "message required"}

        print(f"\n=== SEARCH: {message} ===")
        sent = await client.send_message(BOT_USERNAME, message)
        await asyncio.sleep(3)

        messages = await client.get_messages(BOT_USERNAME, limit=10)
        reply = None
        for msg in messages:
            if not msg.out and msg.id > sent.id:
                reply = msg
                break
        if not reply:
            return {"status": False, "error": "No response from bot"}

        file_path = None

        if reply.buttons:
            for row in reply.buttons:
                for btn in row:
                    if DOWNLOAD_BUTTON.lower() in btn.text.lower():
                        await btn.click()
                        break
                if file_path:
                    break
            for _ in range(30):
                await asyncio.sleep(2)
                latest = await client.get_messages(BOT_USERNAME, limit=5)
                for msg in latest:
                    if msg.file and msg.id > reply.id:
                        file_path = await client.download_media(msg, file=DOWNLOAD_DIR)
                        break
                if file_path:
                    break

        if not file_path and reply.message:
            html_match = re.search(r'(<!DOCTYPE html>|<html>.*?</html>)', reply.message, re.DOTALL | re.IGNORECASE)
            if html_match:
                html_content = html_match.group(0)
                temp_path = os.path.join(DOWNLOAD_DIR, f"temp_{reply.id}.html")
                with open(temp_path, "w", encoding="utf-8") as f:
                    f.write(html_content)
                file_path = temp_path

        if file_path and os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                html_content = f.read()
            records_data = parse_leakbase_html(html_content)
            if "temp_" in file_path:
                os.remove(file_path)
            
            # Return JSON Structure
            return {
                "status": True,
                "query": message,
                "record_count": len(records_data),
                "data": records_data
            }

        return {"status": False, "error": "No file received"}

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
