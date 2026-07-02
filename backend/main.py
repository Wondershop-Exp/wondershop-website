import logging
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from config import settings
from database import connect_db, disconnect_db
from routers import catalogue, cart, leads, config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("=== Wondershop API starting ===")
    logger.info(f"WhatsApp Phone Number ID : {settings.WHATSAPP_PHONE_NUMBER_ID}")
    logger.info(f"WhatsApp API URL         : {settings.WHATSAPP_API_URL}")
    logger.info(f"WS_PHONE_1               : {settings.WS_PHONE_1}")
    logger.info(f"WS_PHONE_2               : {settings.WS_PHONE_2}")
    logger.info(f"SMTP_USER                : {settings.SMTP_USER}")
    await connect_db()
    yield
    await disconnect_db()

app = FastAPI(
    title="Wondershop Experiences API",
    description="Build a Birthday platform — source of truth: WS_DataDictionary_v1.docx",
    version="2.0.0",
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers
app.include_router(catalogue.router, prefix="/api/catalogue", tags=["Catalogue"])
app.include_router(cart.router,      prefix="/api",           tags=["Orders & Cart"])
app.include_router(leads.router,     prefix="/api/leads",     tags=["Leads"])
app.include_router(config.router,    prefix="/api/config",    tags=["Config"])

@app.get("/")
async def root():
    return {"status": "ok", "message": "Wondershop API is running"}

@app.get("/health")
async def health():
    return {"status": "healthy"}
