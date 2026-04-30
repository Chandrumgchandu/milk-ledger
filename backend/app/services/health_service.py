from datetime import datetime, timezone
import logging

import requests
from flask import current_app

from app.services.supabase_service import get_client


logger = logging.getLogger(__name__)


def live_health_check():
    overall_ok = True
    checks = {
        "supabase": check_supabase(),
        "whatsapp": check_whatsapp(),
    }

    overall_ok = all(item["ok"] for item in checks.values())

    return {
        "ok": overall_ok,
        "service": "milk-vendor-assistant",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


def check_supabase():
    try:
        logger.info("Health probe: Supabase target=%s", _masked_supabase_url())
        client = get_client()
        response = client.table("admins").select("id", count="exact").limit(1).execute()
        return {
            "ok": True,
            "detail": "Supabase connection succeeded.",
            "meta": {
                "schema": current_app.config["SUPABASE_SCHEMA"],
                "admins_visible": response.count,
            },
        }
    except Exception as exc:
        return {
            "ok": False,
            "detail": f"Supabase check failed: {exc}",
        }


def check_whatsapp():
    token = current_app.config["WHATSAPP_ACCESS_TOKEN"]
    phone_number_id = current_app.config["WHATSAPP_PHONE_NUMBER_ID"]
    api_base = current_app.config["WHATSAPP_API_BASE"].rstrip("/")

    missing = []
    if not token:
        missing.append("WHATSAPP_ACCESS_TOKEN")
    if not phone_number_id:
        missing.append("WHATSAPP_PHONE_NUMBER_ID")

    if missing:
        return {
            "ok": False,
            "detail": "Missing required WhatsApp configuration.",
            "meta": {"missing": missing},
        }

    url = f"{api_base}/{phone_number_id}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, headers=headers, timeout=20)
        if response.ok:
            data = response.json()
            return {
                "ok": True,
                "detail": "WhatsApp API credentials are valid.",
                "meta": {
                    "display_phone_number": data.get("display_phone_number"),
                    "verified_name": data.get("verified_name"),
                },
            }
        return {
            "ok": False,
            "detail": f"WhatsApp API check failed with HTTP {response.status_code}.",
            "meta": _safe_json(response),
        }
    except Exception as exc:
        return {
            "ok": False,
            "detail": f"WhatsApp API check failed: {exc}",
        }


def _safe_json(response):
    try:
        return response.json()
    except Exception:
        return {"text": response.text[:300]}


def _masked_supabase_url():
    raw = (current_app.config.get("SUPABASE_URL") or "").strip()
    if not raw:
        return "<unset>"
    if "://" in raw:
        scheme, rest = raw.split("://", 1)
        return f"{scheme}://{rest[:10]}***"
    return f"{raw[:10]}***"
