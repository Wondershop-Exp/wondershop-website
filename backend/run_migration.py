import sys, psycopg2, os
from dotenv import load_dotenv

load_dotenv()
url = os.getenv("DATABASE_URL").replace("postgresql+asyncpg://", "postgresql://")
conn = psycopg2.connect(url)
conn.autocommit = True
cur = conn.cursor()

# Usage: python run_migration.py [path/to/migration.sql]
# Defaults to 002_mvp_schema.sql for backward compatibility.
path = sys.argv[1] if len(sys.argv) > 1 else "migrations/002_mvp_schema.sql"
sql = open(path).read()
cur.execute(sql)
print(f"✅ Ran {path}")
conn.close()
