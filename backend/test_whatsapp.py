import asyncio, httpx
from dotenv import load_dotenv
import os

load_dotenv()

WA_URL    = os.getenv("WHATSAPP_API_URL", "")
WA_NUM_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
WA_TOKEN  = os.getenv("WHATSAPP_ACCESS_TOKEN", "")

async def send(to, msg):
    url = f"{WA_URL}/{WA_NUM_ID}/messages"
    headers = {"Authorization": f"Bearer {WA_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": msg}}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.post(url, headers=headers, json=payload)
    print(f"To +{to}: {r.status_code} — {r.text}")

async def main():
    msg = "✅ Wondershop test — WhatsApp notifications are working! 🎉"
    await send("919868498877", msg)
    await send("919742240477", msg)

asyncio.run(main())
