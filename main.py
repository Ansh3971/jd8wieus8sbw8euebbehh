import os
import re
import json
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
DOWNLOAD_BUTTON = os.getenv(
    "DOWNLOAD_BUTTON",
    "Download"
)

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

os.makedirs(
    DOWNLOAD_DIR,
    exist_ok=True
)

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

    print(
        "Telegram Client Started"
    )

# =========================
# SHUTDOWN
# =========================

@app.on_event("shutdown")
async def shutdown():

    await client.disconnect()

# =========================
# HOME PAGE
# =========================

@app.get(
    "/",
    response_class=HTMLResponse
)
async def home():

    return """
    <html>

        <head>
            <title>
                Universal HTML Parser API
            </title>
        </head>

        <body
            style="
                font-family: Arial;
                padding: 40px;
            "
        >

            <h2>
                Universal HTML Parser API
            </h2>

            <form
                action="/test"
                method="get"
            >

                <input
                    type="text"
                    name="q"
                    placeholder="Enter query"
                    style="
                        width:300px;
                        height:40px;
                        padding:10px;
                    "
                >

                <button
                    type="submit"
                    style="
                        height:40px;
                    "
                >
                    Search
                </button>

            </form>

        </body>

    </html>
    """

# =========================
# ENHANCED HTML PARSER - FLAT RECORDS
# =========================

def extract_flat_records(html):
    """
    Extracts flat array of records from HTML.
    Each record is an object with fields like Channel, Developer, Email, Mobile, Address, etc.
    """
    soup = BeautifulSoup(html, "html.parser")
    
    # Get all text lines
    text = soup.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    
    records = []
    current_record = {}
    
    # Field patterns
    field_patterns = {
        "channel": r"^📢\s*CHANNEL:\s*(.+)",
        "developer": r"^👨‍💻\s*DEVELOPER:\s*(.+)",
        "email": r"^Email:\s*(.+)",
        "mobile": r"^Mobile:\s*(.+)",
        "mobile_alt": r"^Mobile phone:\s*(.+)",
        "address": r"^Address:\s*(.+)",
        "document": r"^Document number:\s*(.+)",
        "fullname": r"^Full name:\s*(.+)",
        "father": r"^The name of the father:\s*(.+)",
        "region": r"^Region:\s*(.+)",
        "passport": r"^Passport number:\s*(.+)",
        "nick": r"^Nick:\s*(.+)",
        "login": r"^login:\s*(.+)",
        "city": r"^City:\s*(.+)",
        "stat": r"^Stat:\s*(.+)",
        "postal": r"^Postal code:\s*(.+)",
        "gender": r"^Gender:\s*(.+)",
        "age": r"^Age:\s*(.+)",
        "car": r"^Car number:\s*(.+)",
        "ip": r"^IP:\s*(.+)",
        "password": r"^Encrypted password:\s*(.+)",
        "plain_password": r"^Password:\s*(.+)",
        "date_reg": r"^The date of registration:\s*(.+)",
        "last_activity": r"^Last activity:\s*(.+)",
        "level": r"^Level:\s*(.+)",
        "education": r"^Education:\s*(.+)",
        "company": r"^The name of the company:\s*(.+)",
        "category": r"^Category:\s*(.+)",
        "link": r"^Link:\s*(.+)",
        "instagram": r"^Instagram identifier:\s*(.+)",
        "name": r"^Name:\s*(.+)",
        "surname": r"^Surname:\s*(.+)",
        "prefix": r"^Prefix:\s*(.+)",
    }
    
    i = 0
    while i < len(lines):
        line = lines[i]
        
        # Check for separator lines
        if "---" in line or "===" in line or line.startswith("-----------------------------------"):
            # Separator: save current record if not empty
            if current_record:
                records.append(current_record)
                current_record = {}
            i += 1
            continue
        
        # Check for channel/developer headers (start of new record)
        channel_match = re.match(field_patterns["channel"], line, re.IGNORECASE)
        developer_match = re.match(field_patterns["developer"], line, re.IGNORECASE)
        
        if channel_match or developer_match:
            # Save previous record
            if current_record:
                records.append(current_record)
                current_record = {}
            
            if channel_match:
                current_record["channel"] = channel_match.group(1).strip()
            if developer_match:
                current_record["developer"] = developer_match.group(1).strip()
            i += 1
            continue
        
        # Try to match any field pattern
        matched = False
        for field_key, pattern in field_patterns.items():
            match = re.match(pattern, line, re.IGNORECASE)
            if match:
                value = match.group(1).strip()
                # Clean up field name for output
                clean_key = field_key.replace("_alt", "").replace("plain_", "")
                
                # Handle multiple values (like multiple mobiles)
                if clean_key in current_record:
                    if isinstance(current_record[clean_key], list):
                        current_record[clean_key].append(value)
                    else:
                        current_record[clean_key] = [current_record[clean_key], value]
                else:
                    current_record[clean_key] = value
                matched = True
                break
        
        if not matched:
            # Check for "Mobile: 919999988888" pattern without colon space variation
            mobile_match = re.match(r"^Mobile:\s*(\d+)", line)
            if mobile_match:
                value = mobile_match.group(1).strip()
                if "mobile" in current_record:
                    if isinstance(current_record["mobile"], list):
                        current_record["mobile"].append(value)
                    else:
                        current_record["mobile"] = [current_record["mobile"], value]
                else:
                    current_record["mobile"] = value
                matched = True
        
        if not matched:
            # Check for plain key: value pattern (like "Name: John")
            kv_match = re.match(r"^([A-Za-z\s]+):\s*(.+)", line)
            if kv_match:
                key = kv_match.group(1).strip().lower().replace(" ", "_")
                value = kv_match.group(2).strip()
                if key in current_record:
                    if isinstance(current_record[key], list):
                        current_record[key].append(value)
                    else:
                        current_record[key] = [current_record[key], value]
                else:
                    current_record[key] = value
                matched = True
        
        i += 1
    
    # Don't forget last record
    if current_record:
        records.append(current_record)
    
    # Post-process: merge related fields
    for record in records:
        # Rename keys to match desired output
        if "fullname" in record:
            record["Full name"] = record.pop("fullname")
        if "father" in record:
            record["The name of the father"] = record.pop("father")
        if "document" in record:
            record["Document number"] = record.pop("document")
        if "passport" in record:
            record["Passport number"] = record.pop("passport")
        if "channel" in record:
            record["📢 CHANNEL"] = record.pop("channel")
        if "developer" in record:
            record["👨‍💻 DEVELOPER"] = record.pop("developer")
        if "mobile" in record:
            record["Mobile"] = record.pop("mobile")
        if "address" in record:
            record["Address"] = record.pop("address")
        if "email" in record:
            record["Email"] = record.pop("email")
        if "region" in record:
            record["Region"] = record.pop("region")
        if "nick" in record:
            record["Nick"] = record.pop("nick")
        if "login" in record:
            record["login"] = record.pop("login")
        if "city" in record:
            record["City"] = record.pop("city")
        if "stat" in record:
            record["Stat"] = record.pop("stat")
        if "postal" in record:
            record["Postal code"] = record.pop("postal")
        if "gender" in record:
            record["Gender"] = record.pop("gender")
        if "age" in record:
            record["Age"] = record.pop("age")
        if "car" in record:
            record["Car number"] = record.pop("car")
        if "ip" in record:
            record["IP"] = record.pop("ip")
        if "password" in record:
            record["Encrypted password"] = record.pop("password")
        if "plain_password" in record:
            record["Password"] = record.pop("plain_password")
        if "date_reg" in record:
            record["The date of registration"] = record.pop("date_reg")
        if "last_activity" in record:
            record["Last activity"] = record.pop("last_activity")
        if "level" in record:
            record["Level"] = record.pop("level")
        if "education" in record:
            record["Education"] = record.pop("education")
        if "company" in record:
            record["The name of the company"] = record.pop("company")
        if "category" in record:
            record["Category"] = record.pop("category")
        if "link" in record:
            record["Link"] = record.pop("link")
        if "instagram" in record:
            record["Instagram identifier"] = record.pop("instagram")
        if "name" in record:
            record["Name"] = record.pop("name")
        if "surname" in record:
            record["Surname"] = record.pop("surname")
        if "prefix" in record:
            record["Prefix"] = record.pop("prefix")
    
    return records


def parse_html_universal(html):
    """
    Main parser function - returns flat records array.
    Kept for backward compatibility but returns records directly.
    """
    return extract_flat_records(html)


# =========================
# SEARCH FUNCTION
# =========================

@app.post("/search")
async def search(data: Query):

    try:

        # SEND MESSAGE

        await client.send_message(
            BOT_USERNAME,
            data.message
        )

        # WAIT

        await asyncio.sleep(3)

        messages = await client.get_messages(
            BOT_USERNAME,
            limit=1
        )

        if not messages:

            return {
                "status": False,
                "error": "No response"
            }

        reply = messages[0]

        # CLICK BUTTON

        try:

            await reply.click(
                text=DOWNLOAD_BUTTON
            )

        except Exception:

            try:

                await reply.click(0)

            except Exception as e:

                return {
                    "status": False,
                    "error": str(e)
                }

        # WAIT FILE

        file_message = None

        for _ in range(20):

            await asyncio.sleep(1)

            latest = await client.get_messages(
                BOT_USERNAME,
                limit=1
            )

            if (
                latest
                and latest[0].file
            ):

                file_message = latest[0]

                break

        if not file_message:

            return {
                "status": False,
                "error": "No file"
            }

        # DOWNLOAD FILE

        file_path = await client.download_media(
            file_message,
            file=DOWNLOAD_DIR
        )

        file_name = os.path.basename(
            file_path
        )

        response = {
            "status": True,
            "query": data.message,
            "file_name": file_name,
            "size": os.path.getsize(
                file_path
            )
        }

        # PARSE HTML - NOW RETURNS FLAT RECORDS ARRAY

        if file_name.endswith(".html"):

            with open(
                file_path,
                "r",
                encoding="utf-8",
                errors="ignore"
            ) as f:

                html_content = f.read()

            parsed = parse_html_universal(
                html_content
            )

            response["parsed"] = parsed
            response["record_count"] = len(parsed)

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
