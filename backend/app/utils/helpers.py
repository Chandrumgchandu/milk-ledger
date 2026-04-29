from datetime import date, datetime
from decimal import Decimal, ROUND_HALF_UP
from hmac import compare_digest

from flask import current_app


def decimal_to_float(value):
    if value is None:
        return None
    return float(value)


def money(value):
    if value is None:
        return Decimal("0.00")
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def parse_date(value, default=None):
    if not value:
        return default
    if isinstance(value, date):
        return value
    return datetime.strptime(value, "%Y-%m-%d").date()


def today_local():
    return date.today()


def normalize_phone(phone):
    return "".join(ch for ch in (phone or "") if ch.isdigit())


def validate_master_key(value):
    configured_key = (current_app.config.get("PASSWORD_RESET_KEY") or "").strip()
    submitted_key = (value or "").strip()
    if not configured_key:
        return False, "Master key is not configured. Add PASSWORD_RESET_KEY in .env."
    if not submitted_key:
        return False, "Master key is required for this action."
    if not compare_digest(submitted_key, configured_key):
        return False, "Invalid master key."
    return True, None
