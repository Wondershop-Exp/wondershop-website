from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret-change-in-prod"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    GMAIL_CLIENT_ID: str = ""
    GMAIL_CLIENT_SECRET: str = ""
    GMAIL_REFRESH_TOKEN: str = ""
    EMAIL_FROM: str = "contact@wondershopexperiences.com"
    EMAIL_TEAM: str = "contact@wondershopexperiences.com"

    WHATSAPP_API_URL: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""

    # AiSensy (WhatsApp BSP) — replaces direct Meta Cloud API calls above.
    # API key: AiSensy dashboard → Manage → API Key.
    # AISENSY_CAMPAIGN_NAME: the "API Campaign" linked to the CUSTOMER-facing
    # "Booking Confirmed" template (2026-08-14, per Shruti — confirmed via
    # the actual approved template screenshot). Sent to the customer's own
    # WhatsApp number right when their booking is confirmed.
    AISENSY_API_KEY: str = ""
    AISENSY_CAMPAIGN_NAME: str = ""

    # AISENSY_TEAM_CAMPAIGN_NAME: a SEPARATE "API Campaign" + template for
    # internal team alerts (name/phone/theme/city/budget), still to be
    # created in AiSensy — leave unset until that template is approved and
    # its campaign name is added here; team WhatsApp alerts stay a no-op
    # (team still gets the full email) until then.
    AISENSY_TEAM_CAMPAIGN_NAME: str = ""

    # Google Sheets — Apps Script webhook URL (no service account needed)
    GOOGLE_SHEET_WEBHOOK_URL: str = ""

    # WhatsApp Business API (Meta Cloud)
    # Messages go to both WS_PHONE_1 and WS_PHONE_2
    WS_PHONE_1: str = "+919004435362"   # Shruti
    WS_PHONE_2: str = "+919742240477"   # Sidhant

    # UPI for order confirmation QR code
    UPI_ID: str = ""                    # e.g. wondershop@ybl

    # Shared password gate for the internal admin booking-management page
    # (admin.html). Set this in Railway's env vars — never commit a real
    # value here. Leave blank locally and admin.py will reject all requests.
    ADMIN_PASSWORD: str = ""

    @property
    def origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"

settings = Settings()
