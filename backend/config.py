from pydantic_settings import BaseSettings
from typing import List

class Settings(BaseSettings):
    DATABASE_URL: str
    APP_ENV: str = "development"
    SECRET_KEY: str = "dev-secret-change-in-prod"
    ALLOWED_ORIGINS: str = "http://localhost:3000"

    SMTP_HOST: str = "smtp.gmail.com"
    SMTP_PORT: int = 587
    SMTP_USER: str = ""
    SMTP_PASSWORD: str = ""
    EMAIL_FROM: str = "contact@wondershopexperiences.com"
    EMAIL_TEAM: str = "contact@wondershopexperiences.com"

    WHATSAPP_API_URL: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""

    # Google Sheets — Apps Script webhook URL (no service account needed)
    GOOGLE_SHEET_WEBHOOK_URL: str = ""

    # WhatsApp Business API (Meta Cloud)
    # Messages go to both WS_PHONE_1 and WS_PHONE_2
    WS_PHONE_1: str = "+919004435362"   # Shruti
    WS_PHONE_2: str = "+919742240477"   # Sidhant

    # UPI for order confirmation QR code
    UPI_ID: str = ""                    # e.g. wondershop@ybl

    @property
    def origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"

settings = Settings()
