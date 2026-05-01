from app import create_app


class MissingDbUrlConfig:
    APP_ENV = "production"
    LOG_LEVEL = "INFO"
    SECRET_KEY = "test-secret"
    SUPABASE_URL = "https://example.supabase.co"
    SUPABASE_KEY = "test-key"
    SUPABASE_DB_URL = ""
    SUPABASE_SCHEMA = "public"
    TRUSTED_HOSTS = None
    TRUST_PROXY = False
    SESSION_COOKIE_SECURE = False
    SESSION_COOKIE_SAMESITE = "Lax"
    SESSION_COOKIE_HTTPONLY = True
    SESSION_REFRESH_EACH_REQUEST = False
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_SECURE = False
    PERMANENT_SESSION_LIFETIME = 900
    WTF_CSRF_TIME_LIMIT = 3600
    WTF_CSRF_SSL_STRICT = False
    MAX_CONTENT_LENGTH = 1048576
    APP_BASE_URL = "https://example.invalid"
    PASSWORD_RESET_KEY = ""
    PREFERRED_URL_SCHEME = "https"
    WHATSAPP_OWNER_PHONE = ""
    ADMIN_WHATSAPP_NUMBERS = []
    WHATSAPP_ACCESS_TOKEN = ""
    WHATSAPP_PHONE_NUMBER_ID = ""
    WHATSAPP_BUSINESS_ACCOUNT_ID = ""
    WHATSAPP_API_BASE = "https://graph.facebook.com/v22.0"
    WHATSAPP_VERIFY_TOKEN = ""
    BUSINESS_NAME = "Test"


class InvalidDbUrlConfig(MissingDbUrlConfig):
    SUPABASE_DB_URL = "https://not-a-postgres-url"


def test_app_starts_without_supabase_db_url(monkeypatch):
    monkeypatch.setattr("app.validate_database", lambda app: (_ for _ in ()).throw(RuntimeError("db admin unavailable")))
    app = create_app(MissingDbUrlConfig)
    assert app is not None


def test_app_starts_with_invalid_supabase_db_url(monkeypatch):
    monkeypatch.setattr("app.validate_database", lambda app: (_ for _ in ()).throw(RuntimeError("db admin unavailable")))
    app = create_app(InvalidDbUrlConfig)
    assert app is not None
