import os
import re
import asyncio
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
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

app = FastAPI()

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
    print("Telegram Client Started")

# =========================
# SHUTDOWN
# =========================

@app.on_event("shutdown")
async def shutdown():
    await client.disconnect()

# =========================
# HTML PARSER - EXTRACT CLEAN RECORDS
# =========================

def parse_leakbase_html(html_content):
    """
    Parse LeakBase HTML and extract structured records as clean JSON
    """
    soup = BeautifulSoup(html_content, "html.parser")
    blocks = soup.find_all("div", class_="block")
    
    all_records = []
    
    for block in blocks:
        # Get source title
        title_elem = block.find("div", class_="block-title")
        source = None
        if title_elem:
            title_text = title_elem.get_text(strip=True)
            # Remove emoji but keep name
            title_text = re.sub(r'[^\w\s\.\-]', '', title_text)
            source = title_text.strip()
        
        # Get text content
        text_elem = block.find("div", class_="block-text")
        if not text_elem:
            continue
        
        # Get all lines
        text = text_elem.get_text(separator="\n", strip=True)
        lines = text.split("\n")
        
        # Current record being built
        current_record = {}
        current_record["source"] = source
        
        # Field mapping for consistent keys
        field_mapping = {
            "📞Telephone": "phones",
            "🏘️Adres": "addresses",
            "📩Email": "emails",
            "🃏Document number": "document_number",
            "👤Full name": "full_name",
            "👨The name of the father": "father_name",
            "🗺️ Region": "region",
            "👤Nick": "nick",
            "📖Passport number": "passport_number",
            "🔐Encrypted password": "encrypted_password",
            "🔑Password": "password",
            "📆Date": "date",
            "📆Last activity": "last_activity",
            "📆The date of registration": "registration_date",
            "🌃City": "city",
            "🇺🇸Stat": "state",
            "🎯IP": "ip",
            "🚻Gender": "gender",
            "👴Age": "age",
            "📍District": "district",
            "🏤Postal code": "postal_code",
            "🏷️ login": "login",
            "🔗Link": "link",
            "📰Category": "category",
            "🗾Country": "country",
            "⬆Level": "level",
            "🏫Education": "education"
        }
        
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line:
                i += 1
                continue
            
            # Check if line contains a field
            matched = False
            for emoji_field, json_key in field_mapping.items():
                if line.startswith(emoji_field):
                    # Extract value after colon
                    parts = line.split(":", 1)
                    if len(parts) == 2:
                        value = parts[1].strip()
                        # Clean HTML tags if any
                        value = re.sub(r'<[^>]+>', '', value)
                        value = value.strip()
                        
                        if value:
                            # Handle multi-value fields (phones, addresses, emails)
                            if json_key in ["phones", "addresses", "emails"]:
                                if json_key not in current_record:
                                    current_record[json_key] = []
                                if value not in current_record[json_key]:
                                    current_record[json_key].append(value)
                            else:
                                # Only set if not already set (first occurrence wins)
                                if json_key not in current_record:
                                    current_record[json_key] = value
                    matched = True
                    break
            
            # Check for plain text fields (like "Name:" without emoji)
            if not matched:
                plain_match = re.match(r'^([A-Za-z\s]+):\s*(.+)$', line)
                if plain_match:
                    key = plain_match.group(1).strip().lower()
                    value = plain_match.group(2).strip()
                    # Map common plain text fields
                    if key == "name":
                        if "full_name" not in current_record:
                            current_record["full_name"] = value
                    elif key == "email":
                        if "emails" not in current_record:
                            current_record["emails"] = [value]
                        elif value not in current_record["emails"]:
                            current_record["emails"].append(value)
                    elif key == "phone" or key == "telephone":
                        if "phones" not in current_record:
                            current_record["phones"] = [value]
                        elif value not in current_record["phones"]:
                            current_record["phones"].append(value)
                    elif key == "address" or key == "adres":
                        if "addresses" not in current_record:
                            current_record["addresses"] = [value]
                        elif value not in current_record["addresses"]:
                            current_record["addresses"].append(value)
                    elif "password" in key:
                        if "password" not in current_record:
                            current_record["password"] = value
                    elif "encrypted" in key:
                        if "encrypted_password" not in current_record:
                            current_record["encrypted_password"] = value
            
            i += 1
        
        # Only add record if it has meaningful data (not just source)
        if len(current_record) > 1:
            all_records.append(current_record)
    
    return all_records

# =========================
# MAIN SEARCH FUNCTION
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        # SEND MESSAGE
        sent_message = await client.send_message(
            BOT_USERNAME,
            data.message
        )

        # WAIT FOR BOT REPLY
        await asyncio.sleep(3)

        messages = await client.get_messages(
            BOT_USERNAME,
            limit=1
        )

        if not messages:
            return {
                "status": False,
                "error": "No response from bot"
            }

        reply_message = messages[0]

        # CLICK DOWNLOAD BUTTON
        try:
            await reply_message.click(text=DOWNLOAD_BUTTON)

        except Exception:
            try:
                await reply_message.click(0)

            except Exception as e:
                return {
                    "status": False,
                    "error": f"Button click failed: {str(e)}"
                }

        # WAIT FOR FILE
        file_message = None

        for _ in range(15):

            await asyncio.sleep(1)

            latest = await client.get_messages(
                BOT_USERNAME,
                limit=1
            )

            if latest and latest[0].file:
                file_message = latest[0]
                break

        if not file_message:
            return {
                "status": False,
                "error": "No file received"
            }

        # DOWNLOAD FILE
        file_path = await client.download_media(
            file_message,
            file=DOWNLOAD_DIR
        )

        file_name = os.path.basename(file_path)

        response = {
            "status": True,
            "query": data.message,
            "file_name": file_name,
            "size": os.path.getsize(file_path)
        }

        # READ AND PARSE HTML FILE
        if file_name.endswith(".html"):

            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                html_content = f.read()

            # Parse HTML into clean records
            parsed_records = parse_leakbase_html(html_content)
            
            response["record_count"] = len(parsed_records)
            response["data"] = parsed_records

        return response

    except Exception as e:

        return {
            "status": False,
            "error": str(e)
        }

# =========================
# BROWSER SEARCH
# =========================

@app.get("/test")
async def test(q: str):

    return await search(
        Query(message=q)
    )

# =========================
# HOME PAGE
# =========================

@app.get("/", response_class=HTMLResponse)
async def home():
    return """
    <html>
        <head>
            <title>Telegram Search API</title>
        </head>

        <body style="font-family: Arial; padding: 40px;">
            <h2>Telegram Search API</h2>

            <form action="/test" method="get">

                <input
                    type="text"
                    name="q"
                    placeholder="Enter query"
                    style="width:300px;height:40px;padding:10px;"
                >

                <button
                    type="submit"
                    style="height:40px;"
                >
                    Search
                </button>

            </form>
        </body>
    </html>
    """
