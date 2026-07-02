import psycopg2, os
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL").replace("postgresql+asyncpg://", "postgresql://")
conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()
sql = open("migrations/002_mvp_schema.sql").read()
cur.execute(sql)
print("✅ MVP schema created — leads table ready")
conn.close()
