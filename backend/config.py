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

    # Instagram feed (2026-08-18, per Shruti — "let's fix instagram with
    # meta's free api now"). IG_ACCESS_TOKEN is only the SEED long-lived
    # token — after the first successful call, routers/instagram.py
    # refreshes it automatically and persists the refreshed token in the
    # instagram_cache DB table, so this env var never needs to be updated by
    # hand again (it's only the initial bootstrap value). Calls go through
    # graph.instagram.com/me/media, which resolves to whichever account the
    # token belongs to — IG_USER_ID isn't required for that, it's kept here
    # only for reference/future use. Never commit real values here.
    IG_USER_ID: str = ""
    IG_ACCESS_TOKEN: str = ""

    # GST readiness — Wondershop is not GST-registered yet (2026-09, per
    # Shruti — "will register in sometime"). Keep GST_ENABLED False until
    # registration is complete; invoice_builder.py already reads these three
    # settings and will start showing GSTIN + a CGST/SGST breakdown the
    # moment GST_ENABLED flips to True, with no other code changes needed.
    GST_ENABLED: bool = False
    GSTIN: str = ""
    GST_RATE_PCT: float = 0.0

    # Admin dashboard (2026-09-11, per Shruti/CGO review — "do we have
    # enough system in place to track website performance"). Weekly target
    # is derived as MONTHLY_REVENUE_TARGET / 4.345 (average weeks/month) —
    # update this single number as the growth target changes, rather than
    # a stored weekly figure that drifts out of sync with the monthly one.
    # CGO's PRD target: Rs.1 crore ARR in 9-12 months (~Rs.8-9L/month) —
    # defaulting to the low end.
    MONTHLY_REVENUE_TARGET: float = 800000

    # GA4 Data API — read-only traffic + builder-funnel numbers on the
    # dashboard. Both blank = GA4 cards show a "not connected yet" state
    # instead of erroring. GA4_SERVICE_ACCOUNT_JSON is the FULL JSON key
    # file content for a service account with Viewer access on the GA4
    # property, pasted as one env var (Railway has no file uploads) — never
    # commit a real value here. See backend/GA4_SETUP.md for the one-time
    # setup steps.
    GA4_PROPERTY_ID: str = ""
    GA4_SERVICE_ACCOUNT_JSON: str = ""

    @property
    def origins(self) -> List[str]:
        return [o.strip() for o in self.ALLOWED_ORIGINS.split(",")]

    class Config:
        env_file = ".env"

settings = Settings()
