from datetime import date
from pathlib import Path

from app.services import session_service


def test_finalize_session_skips_when_already_closed(monkeypatch):
    monkeypatch.setattr(session_service, "is_session_closed", lambda target_date, session_name: True)

    result = session_service.finalize_session(date(2026, 4, 30), "morning")

    assert result == 0


def test_session_closures_migration_enforces_unique_session_date():
    migration_path = (
        Path(__file__).resolve().parents[2]
        / "supabase"
        / "migrations"
        / "202605010001_production_baseline.sql"
    )
    sql = migration_path.read_text(encoding="utf-8").lower()

    assert "session_name" in sql
    assert "target_date" in sql
    assert "create unique index if not exists uq_session_closures_session_target_date" in sql
