from datetime import datetime
from zoneinfo import ZoneInfo

from flask import current_app
import logging


IST = ZoneInfo("Asia/Kolkata")
logger = logging.getLogger(__name__)


def now_ist():
    return datetime.now(IST)


def today_ist():
    return now_ist().date()


def current_collection_session(current_dt):
    settings = get_session_settings()
    minutes = current_dt.hour * 60 + current_dt.minute
    if settings["morning_start_minutes"] <= minutes <= settings["morning_end_minutes"]:
        return "morning"
    if settings["evening_start_minutes"] <= minutes <= settings["evening_end_minutes"]:
        return "evening"
    return None


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
        from app.services.supabase_service import get_client

        rows = get_client().table("app_settings").select("*").in_("key", list(defaults.keys())).execute().data or []
        values = {row["key"]: row["value"] for row in rows}
    except Exception:
        values = {}

    merged = {key: values.get(key, default) for key, default in defaults.items()}
    merged["morning_start_minutes"] = _to_minutes(merged["morning_start"])
    merged["morning_end_minutes"] = _to_minutes(merged["morning_end"])
    merged["evening_start_minutes"] = _to_minutes(merged["evening_start"])
    merged["evening_end_minutes"] = _to_minutes(merged["evening_end"])
    return merged


def update_session_settings(morning_start, morning_end, evening_start, evening_end):
    from app.services.supabase_service import get_client

    rows = [
        {"key": "morning_start", "value": morning_start},
        {"key": "morning_end", "value": morning_end},
        {"key": "evening_start", "value": evening_start},
        {"key": "evening_end", "value": evening_end},
    ]
    get_client().table("app_settings").upsert(rows, on_conflict="key").execute()


def auto_finalize_day_entries(current_dt=None):
    current_dt = current_dt or now_ist()
    total_created = 0

    if _past_finalization_cutoff(current_dt, "morning"):
        total_created += _finalize_session(current_dt, "morning")
    if _past_finalization_cutoff(current_dt, "evening"):
        total_created += _finalize_session(current_dt, "evening")

    return total_created


def _finalize_session(current_dt, session_name):
    session_key = f"session_finalized_{current_dt.date().isoformat()}_{session_name}"
    if _is_flag_set(session_key):
        return 0

    try:
        from app.services.supabase_service import auto_fill_zero_entries, set_app_setting

        created = auto_fill_zero_entries(current_dt.date(), session_name)
        set_app_setting(session_key, "true")
        logger.info(
            "Finalized %s session for %s with %s zero-filled pending entries",
            session_name,
            current_dt.date().isoformat(),
            created,
        )
        return created
    except Exception as exc:
        logger.warning("Automatic %s zero-fill failed: %s", session_name, exc)
        return 0


def _is_flag_set(key):
    try:
        from app.services.supabase_service import get_app_setting

        return get_app_setting(key) == "true"
    except Exception:
        return False


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
