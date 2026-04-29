import logging

import requests
from flask import current_app
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


logger = logging.getLogger(__name__)


def _session():
    session = requests.Session()
    retry = Retry(
        total=3,
        read=3,
        connect=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET", "POST"]),
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


def send_whatsapp_message(to_phone, message):
    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "text",
        "text": {"body": message},
    }
    return _post_message(payload)


def send_whatsapp_list(to_phone, body_text, button_text, sections, header_text=None, footer_text=None):
    interactive = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": button_text[:20],
            "sections": sections,
        },
    }
    if header_text:
        interactive["header"] = {"type": "text", "text": header_text[:60]}
    if footer_text:
        interactive["footer"] = {"text": footer_text[:60]}

    payload = {
        "messaging_product": "whatsapp",
        "to": to_phone,
        "type": "interactive",
        "interactive": interactive,
    }
    return _post_message(payload)


def _post_message(payload):
    token = current_app.config["WHATSAPP_ACCESS_TOKEN"]
    phone_number_id = current_app.config["WHATSAPP_PHONE_NUMBER_ID"]
    api_base = current_app.config["WHATSAPP_API_BASE"].rstrip("/")

    if not token or not phone_number_id:
        logger.warning("WhatsApp credentials are not configured. Skipping outbound message.")
        return None

    url = f"{api_base}/{phone_number_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    response = _session().post(url, headers=headers, json=payload, timeout=20)
    if not response.ok:
        logger.error("WhatsApp API error %s: %s", response.status_code, response.text)
    response.raise_for_status()
    return response.json()
