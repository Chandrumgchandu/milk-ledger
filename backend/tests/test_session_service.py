from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from app.services import session_service


IST = ZoneInfo("Asia/Kolkata")


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


def test_auto_close_sessions_finalizes_same_day_morning_after_cutoff(monkeypatch):
    calls = []
    monkeypatch.setattr(session_service, "_safe_finalize_session", lambda target_date, session_name: calls.append((target_date, session_name)) or 0)

    session_service.auto_close_sessions(datetime(2026, 5, 2, 12, 0, tzinfo=IST))

    assert (date(2026, 5, 2), "morning") in calls


def test_auto_close_sessions_catches_previous_evening_next_day(monkeypatch):
    calls = []
    monkeypatch.setattr(session_service, "_safe_finalize_session", lambda target_date, session_name: calls.append((target_date, session_name)) or 0)

    session_service.auto_close_sessions(datetime(2026, 5, 2, 0, 5, tzinfo=IST))

    assert (date(2026, 5, 1), "evening") in calls


def test_auto_close_sessions_does_not_close_same_day_evening_before_cutoff(monkeypatch):
    calls = []
    monkeypatch.setattr(session_service, "_safe_finalize_session", lambda target_date, session_name: calls.append((target_date, session_name)) or 0)

    session_service.auto_close_sessions(datetime(2026, 5, 2, 22, 0, tzinfo=IST))

    assert (date(2026, 5, 2), "evening") not in calls
    assert (date(2026, 5, 1), "evening") in calls
