import os
from pathlib import Path
from datetime import timedelta
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def normalize_supabase_db_url(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""

    if raw.startswith("postgres://"):
        raw = "postgresql://" + raw[len("postgres://") :]

    parsed = urlsplit(raw)
    if parsed.scheme not in {"postgresql"}:
        return raw

    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.setdefault("sslmode", "require")
    normalized_query = urlencode(query)
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, normalized_query, parsed.fragment))


def validate_supabase_db_url(value: str) -> tuple[bool, str]:
    raw = (value or "").strip()
    if not raw:
        return False, "SUPABASE_DB_URL is missing."

    parsed = urlsplit(raw)
    if parsed.scheme != "postgresql":
        return False, "SUPABASE_DB_URL must start with postgresql://"
    if not parsed.hostname:
        return False, "SUPABASE_DB_URL must include a database host."
    if not parsed.username:
        return False, "SUPABASE_DB_URL must include the database user."
    if not parsed.path or parsed.path == "/":
        return False, "SUPABASE_DB_URL must include the database name."
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    if query.get("sslmode", "").lower() != "require":
        return False, "SUPABASE_DB_URL must include sslmode=require."
    return True, ""


class Config:
    TRUSTED_HOSTS = ["milk-ledger.onrender.com", "your-vercel-app.vercel.app"]
    APP_ENV = os.getenv("APP_ENV", os.getenv("FLASK_ENV", "development"))
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me")
    APP_BASE_URL = os.getenv("APP_BASE_URL", "https://example.invalid")
    PASSWORD_RESET_KEY = os.getenv("PASSWORD_RESET_KEY", "")
    PREFERRED_URL_SCHEME = os.getenv("PREFERRED_URL_SCHEME", "https")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = os.getenv("SESSION_COOKIE_SAMESITE", "Lax")
    SESSION_COOKIE_SECURE = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"
    SESSION_REFRESH_EACH_REQUEST = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = SESSION_COOKIE_SECURE
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=int(os.getenv("SESSION_TIMEOUT_MINUTES", "15")))
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = SESSION_COOKIE_SECURE
    MAX_CONTENT_LENGTH = int(os.getenv("MAX_CONTENT_LENGTH", str(1024 * 1024)))
    TRUST_PROXY = os.getenv("TRUST_PROXY", "false").lower() == "true"
    TRUSTED_HOSTS = [host.strip().lower() for host in os.getenv("TRUSTED_HOSTS", "").split(",") if host.strip()] or None

    SUPABASE_URL = os.getenv("SUPABASE_URL", "")
    SUPABASE_KEY = os.getenv("SUPABASE_KEY", "")
    SUPABASE_DB_URL = normalize_supabase_db_url(os.getenv("SUPABASE_DB_URL", ""))
    SUPABASE_SCHEMA = os.getenv("SUPABASE_SCHEMA", "public")

    BUSINESS_NAME = os.getenv("BUSINESS_NAME", "Someshwara Dairy Milk")

    WHATSAPP_OWNER_PHONE = os.getenv("WHATSAPP_OWNER_PHONE", "")
    ADMIN_WHATSAPP_NUMBERS = [
        phone.strip()
        for phone in os.getenv("ADMIN_WHATSAPP_NUMBERS", WHATSAPP_OWNER_PHONE).split(",")
        if phone.strip()
    ]

    WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN", os.getenv("ACCESS_TOKEN", ""))
    WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID", "")
    WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID", "")
    WHATSAPP_API_BASE = os.getenv("WHATSAPP_API_BASE", "https://graph.facebook.com/v22.0")
    WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN", os.getenv("VERIFY_TOKEN", ""))

    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
