from config import extract_supabase_project_ref, normalize_supabase_db_url, validate_supabase_db_url


def test_normalize_supabase_db_url_adds_sslmode_and_scheme():
    raw = "postgres://postgres:password@db.project.supabase.co:5432/postgres"
    normalized = normalize_supabase_db_url(raw)

    assert normalized.startswith("postgresql://")
    assert "sslmode=require" in normalized


def test_validate_supabase_db_url_rejects_non_postgres_url():
    ok, error = validate_supabase_db_url("https://project.supabase.co")

    assert ok is False
    assert "postgresql://" in error


def test_validate_supabase_db_url_accepts_render_ready_format():
    ok, error = validate_supabase_db_url(
        "postgresql://postgres:password@db.project.supabase.co:5432/postgres?sslmode=require"
    )

    assert ok is True
    assert error == ""


def test_extract_supabase_project_ref_supports_rest_and_db_urls():
    assert extract_supabase_project_ref("https://abc123.supabase.co") == "abc123"
    assert extract_supabase_project_ref("postgresql://postgres:password@db.xyz789.supabase.co:5432/postgres?sslmode=require") == "xyz789"
