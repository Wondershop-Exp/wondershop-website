import databases
from sqlalchemy import create_engine, MetaData
from config import settings

# Async database connection (for API requests)
database = databases.Database(settings.DATABASE_URL)

# Sync engine (for schema creation / migrations)
engine = create_engine(settings.DATABASE_URL)

metadata = MetaData()

async def connect_db():
    await database.connect()

async def disconnect_db():
    await database.disconnect()
