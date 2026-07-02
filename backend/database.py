import databases
from config import settings

# Async database connection (for all API requests)
database = databases.Database(settings.DATABASE_URL)

async def connect_db():
    await database.connect()

async def disconnect_db():
    await database.disconnect()
