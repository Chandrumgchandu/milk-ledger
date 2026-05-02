from datetime import date
from types import SimpleNamespace

from app.routes import payments


def test_resolve_period_start_uses_last_payment_date_plus_one_day():
    logs = [SimpleNamespace(payment_date=date(2026, 5, 1), created_at=None)]

    result = payments._resolve_period_start(logs, date(2026, 5, 10))

    assert result == date(2026, 5, 2)


def test_resolve_period_start_falls_back_to_30_day_window_when_no_logs():
    result = payments._resolve_period_start([], date(2026, 5, 10))

    assert result == date(2026, 4, 11)
