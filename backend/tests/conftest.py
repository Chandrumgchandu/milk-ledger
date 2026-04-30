import os
import sys
from pathlib import Path


BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_KEY", "test-key")
os.environ.setdefault("SUPABASE_SCHEMA", "public")
os.environ.setdefault("SUPABASE_DB_URL", "postgresql://postgres:password@localhost:5432/postgres")
os.environ.setdefault("APP_ENV", "development")
