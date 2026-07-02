"""
Test email + WhatsApp notifications.
Run from the backend folder:
    cd /path/to/Website/backend
    pip install aiosmtplib httpx python-dotenv
    python test_notifications.py
"""
import asyncio, httpx, aiosmtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv
import os

load_dotenv()

SMTP_HOST   = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT   = int(os.getenv("SMTP_PORT", 587))
SMTP_USER   = os.getenv("SMTP_USER", "")
SMTP_PASS   = os.getenv("SMTP_PASSWORD", "")
EMAIL_FROM  = os.getenv("EMAIL_FROM", "")
EMAIL_TEAM  = os.getenv("EMAIL_TEAM", "")

WA_URL      = os.getenv("WHATSAPP_API_URL", "")
WA_NUM_ID   = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WA_TOKEN    = os.getenv("WHATSAPP_ACCESS_TOKEN", "")
WS_PHONE_1  = os.getenv("WS_PHONE_1", "").lstrip("+")
WS_PHONE_2  = os.getenv("WS_PHONE_2", "").lstrip("+")


async def test_email():
    print("\n── EMAIL TEST ──")
    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = "✅ Wondershop notification test"
        msg["From"]    = EMAIL_FROM
        msg["To"]      = EMAIL_TEAM
        msg.attach(MIMEText(
            "This is a test notification from the Wondershop lead system.\n\n"
            "If you received this, email notifications are working correctly! 🎉",
            "plain"
        ))
        await aiosmtplib.send(
            msg,
            hostname=SMTP_HOST,
            port=SMTP_PORT,
            username=SMTP_USER,
            password=SMTP_PASS,
            start_tls=True,
        )
        print(f"  ✅ Email sent to {EMAIL_TEAM}")
    except Exception as e:
        print(f"  ❌ Email failed: {e}")


async def test_whatsapp(to: str):
    try:
        url = f"{WA_URL}/{WA_NUM_ID}/messages"
        headers = {
            "Authorization": f"Bearer {WA_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": "✅ *Wondershop notification test*\n\nIf you received this, WhatsApp notifications are working correctly! 🎉"},
        }
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.post(url, headers=headers, json=payload)
        data = r.json()
        if r.status_code == 200:
            print(f"  ✅ WhatsApp sent to +{to}")
        else:
            print(f"  ❌ WhatsApp failed for +{to}: {data}")
    except Exception as e:
        print(f"  ❌ WhatsApp error for +{to}: {e}")


async def main():
    await test_email()

    print("\n── WHATSAPP TEST ──")
    if not WA_TOKEN or not WA_NUM_ID:
        print("  ⚠️  WhatsApp credentials not set — skipping")
    else:
        await test_whatsapp("919868498877")
        await test_whatsapp("919742240477")

    print("\nDone.")

asyncio.run(main())
