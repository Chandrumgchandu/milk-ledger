from datetime import date, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

from flask import current_app
import logging


IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)


def now_ist():
    return datetime.now(IST)


def today_ist():
    return now_ist().date()


def dashboard_link():
    return f"{current_app.config['APP_BASE_URL'].rstrip('/')}/login"


def get_session_settings():
    defaults = {
        "morning_start": "06:00",
        "morning_end": "09:00",
        "evening_start": "18:00",
        "evening_end": "21:00",
    }
    try:
        from app.services.supabase_service import get_app_settings, safe_query

        values = safe_query(lambda: get_app_settings(defaults.keys(), defaults), fallback={}) or {}
    except Exception:
        logger.exception("Unable to load session settings from database.")
        values = {}

    merged = {key: values.get(key, default) for key, default in defaults.items()}
    merged["morning_start_minutes"] = _to_minutes(merged["morning_start"])
    merged["morning_end_minutes"] = _to_minutes(merged["morning_end"])
    merged["evening_start_minutes"] = _to_minutes(merged["evening_start"])
    merged["evening_end_minutes"] = _to_minutes(merged["evening_end"])
    return merged


def update_session_settings(morning_start, morning_end, evening_start, evening_end):
    from app.services.supabase_service import set_app_setting

    set_app_setting("morning_start", morning_start)
    set_app_setting("morning_end", morning_end)
    set_app_setting("evening_start", evening_start)
    set_app_setting("evening_end", evening_end)


def current_collection_session(current_dt):
    settings = get_session_settings()
    minutes = current_dt.hour * 60 + current_dt.minute
    if settings["morning_start_minutes"] <= minutes <= settings["morning_end_minutes"]:
        return "morning"
    if settings["evening_start_minutes"] <= minutes <= settings["evening_end_minutes"]:
        return "evening"
    return None


def get_active_session(current_dt=None):
    current_dt = current_dt or now_ist()
    override = _session_override()
    if override in {"morning", "evening"}:
        return override
    if override in {"closed", "off"}:
        return None
    return current_collection_session(current_dt)


def is_session_active(current_dt=None):
    return get_active_session(current_dt) is not None


def auto_close_sessions(current_dt=None):
    current_dt = current_dt or now_ist()
    total_created = 0
    if _past_finalization_cutoff(current_dt, "morning"):
        total_created += _safe_finalize_session(current_dt.date(), "morning")
    if _past_finalization_cutoff(current_dt, "evening"):
        total_created += _safe_finalize_session(current_dt.date(), "evening")
    return total_created


def finalize_session(target_date, session_name):
    target_date = _ensure_date(target_date)
    if is_session_closed(target_date, session_name):
        return 0

    from app.services.supabase_service import (
        get_current_rate,
        get_entry_by_unique_key,
        list_farmers,
        create_entry,
        mark_session_closed,
    )

    current_rate = get_current_rate()
    applied_rate = current_rate.rate if current_rate else Decimal("0.00")
    created = 0
    for farmer in list_farmers(active_only=True):
        if get_entry_by_unique_key(farmer.id, target_date, session_name):
            continue
        create_entry(
            {
                "farmer_id": farmer.id,
                "date": target_date.isoformat(),
                "session": session_name,
                "quantity": "0.00",
                "rate": str(applied_rate),
                "amount": "0.00",
            }
        )
        created += 1

    mark_session_closed(target_date, session_name)
    logger.info("Closed %s session for %s with %s zero entries", session_name, target_date.isoformat(), created)
    return created


def is_session_closed(target_date, session_name):
    from app.services.supabase_service import is_session_closed_recorded

    return is_session_closed_recorded(_ensure_date(target_date), session_name)


def _session_override():
    try:
        from app.services.supabase_service import get_app_setting, safe_query

        value = (safe_query(lambda: get_app_setting("active_session_override", ""), fallback="") or "").strip().lower()
        return value
    except Exception:
        logger.exception("Unable to load session override from database.")
        return ""


def _past_finalization_cutoff(current_dt, session_name):
    minutes = current_dt.hour * 60 + current_dt.minute
    if session_name == "morning":
        return minutes >= (11 * 60 + 59)
    if session_name == "evening":
        return minutes >= (23 * 60 + 59)
    return False


def _to_minutes(value):
    hours, minutes = value.split(":")
    return int(hours) * 60 + int(minutes)


def _ensure_date(value):
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value))


def _safe_finalize_session(target_date, session_name):
    try:
        return finalize_session(target_date, session_name)
    except Exception:
        logger.exception("Failed to finalize %s session for %s", session_name, target_date)
        return 0
