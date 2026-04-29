import logging
import re
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request

from app.services.session_service import current_collection_session, dashboard_link, now_ist
from app.services.supabase_service import (
    clear_whatsapp_state,
    create_entry,
    create_rate,
    get_current_rate,
    get_entry,
    get_entry_by_unique_key,
    get_farmer_by_code,
    get_farmer_by_phone,
    get_whatsapp_state,
    is_processed_message,
    latest_relevant_farmer_entry,
    mark_message_processed,
    monthly_totals,
    pending_for_session,
    update_entry,
    upsert_whatsapp_state,
)
from app.services.whatsapp_service import send_whatsapp_buttons, send_whatsapp_message
from app.utils.helpers import money, normalize_phone


logger = logging.getLogger(__name__)
whatsapp_bp = Blueprint("whatsapp", __name__)

OWNER_MENU_BUTTONS = [
    {"id": "owner_change_rate", "title": "Change Rate"},
    {"id": "owner_dashboard_link", "title": "Dashboard Link"},
    {"id": "owner_stop_entry", "title": "Stop Entry"},
]

ENTRY_ACTION_BUTTONS = [
    {"id": "owner_edit_last", "title": "Edit Last Entry"},
    {"id": "owner_pending_list", "title": "Pending List"},
    {"id": "owner_main_menu", "title": "Main Menu"},
]


@whatsapp_bp.route("", methods=["GET"], strict_slashes=False)
@whatsapp_bp.route("/", methods=["GET"], strict_slashes=False)
def verify_webhook():
    if request.args.get("hub.mode") == "subscribe" and request.args.get("hub.verify_token") == current_app.config["WHATSAPP_VERIFY_TOKEN"]:
        return request.args.get("hub.challenge"), 200
    return jsonify({"error": "Invalid verify token"}), 403


@whatsapp_bp.route("", methods=["POST"], strict_slashes=False)
@whatsapp_bp.route("/", methods=["POST"], strict_slashes=False)
def receive_webhook():
    payload = request.get_json(silent=True) or {}
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})
                if "messages" not in value:
                    continue
                for message in value.get("messages", []):
                    process_message(message)
    except Exception as exc:
        logger.exception("WhatsApp webhook failed: %s", exc)
        return jsonify({"status": "error"}), 500
    return jsonify({"status": "ok"})


def process_message(message):
    message_id = (message.get("id") or "").strip()
    if not message_id:
        return
    if is_processed_message(message_id):
        logger.info("Skipping duplicate WhatsApp message %s", message_id)
        return

    phone = normalize_phone(message.get("from"))
    body = extract_message_text(message)
    if not body:
        mark_message_processed(message_id, phone)
        return

    logger.info("Incoming WhatsApp message from %s: %s", phone, body)
    mark_message_processed(message_id, phone)

    if phone == normalize_phone(current_app.config["WHATSAPP_OWNER_PHONE"]):
        response = handle_owner_message(phone, body)
    else:
        response = handle_farmer_message(phone, body)

    dispatch_response(phone, response)


def extract_message_text(message):
    interactive = message.get("interactive", {})
    if interactive.get("button_reply", {}).get("id"):
        return interactive["button_reply"]["id"]
    if interactive.get("list_reply", {}).get("id"):
        return interactive["list_reply"]["id"]
    return (message.get("text", {}) or {}).get("body", "").strip()


def dispatch_response(phone, response):
    if not response:
        return
    response_type = response.get("type")
    if response_type == "buttons":
        send_owner_buttons(phone, response["text"], response["buttons"])
        return
    if response_type == "text":
        send_whatsapp_message(phone, response["text"])


def send_owner_buttons(phone, text, buttons):
    send_whatsapp_buttons(phone, text, buttons)


def handle_owner_message(phone, body):
    state = get_whatsapp_state(phone)
    return process_owner_flow(phone, body, state)


def process_owner_flow(phone, body, state):
    now = now_ist()
    session_name = current_collection_session(now)
    normalized = body.strip().lower()

    if state and state.state == "awaiting_rate":
        return save_new_rate(phone, body)

    if state and state.state == "awaiting_edit_quantity":
        return edit_last_entry(phone, state, body)

    if state and state.state.startswith("entry_active_"):
        active_session = state.state.replace("entry_active_", "", 1)
        if normalized == "owner_edit_last":
            return begin_edit_last_entry(phone, state)
        if normalized == "owner_pending_list":
            return pending_message(active_session)
        if normalized == "owner_main_menu":
            return owner_main_menu()
        if normalized == "owner_dashboard_link":
            return {"type": "text", "text": dashboard_link()}
        if normalized == "owner_change_rate":
            upsert_whatsapp_state(phone, "owner", "awaiting_rate", context_value=active_session, last_entry_id=state.last_entry_id, last_farmer_id=state.last_farmer_id)
            return {"type": "text", "text": "Send new rate"}
        if normalized == "owner_stop_entry":
            clear_whatsapp_state(phone)
            return {"type": "text", "text": "Entry stopped"}
        if normalized == "owner_start_entry":
            return start_entry_prompt(phone, active_session)
        return save_owner_entry(phone, active_session, body, state)

    if normalized in {"hi", "hello", "start", "menu"}:
        if session_name:
            clear_whatsapp_state(phone)
            return session_entry_point(session_name)
        return owner_main_menu("No active milk session right now.")

    if normalized == "owner_start_entry":
        if not session_name:
            return {"type": "text", "text": "Outside session window."}
        return start_entry_prompt(phone, session_name)

    if normalized == "owner_pending_list":
        if not session_name:
            return {"type": "text", "text": "Outside session window."}
        return pending_message(session_name)

    if normalized == "owner_main_menu":
        return owner_main_menu()

    if normalized == "owner_dashboard_link":
        return {"type": "text", "text": dashboard_link()}

    if normalized == "owner_change_rate":
        upsert_whatsapp_state(phone, "owner", "awaiting_rate")
        return {"type": "text", "text": "Send new rate"}

    if normalized == "owner_stop_entry":
        clear_whatsapp_state(phone)
        return {"type": "text", "text": "Entry stopped"}

    if session_name:
        clear_whatsapp_state(phone)
        return session_entry_point(session_name)

    return owner_main_menu("No active milk session right now.")


def session_entry_point(session_name):
    return {
        "type": "buttons",
        "text": f"Start {session_name} milk entry?",
        "buttons": [
            {"id": "owner_start_entry", "title": "Start Entry"},
            {"id": "owner_pending_list", "title": "Pending List"},
            {"id": "owner_main_menu", "title": "Main Menu"},
        ],
    }


def start_entry_prompt(phone, session_name):
    current_session = current_collection_session(now_ist())
    if current_session != session_name:
        return {"type": "text", "text": "Outside session window."}
    upsert_whatsapp_state(phone, "owner", f"entry_active_{session_name}", context_value=session_name)
    return {"type": "text", "text": "Send in format: <ID> <liters>\nExample: 1 5.5"}


def save_owner_entry(phone, session_name, body, state):
    if current_collection_session(now_ist()) != session_name:
        clear_whatsapp_state(phone)
        return {"type": "text", "text": "Outside session window."}

    match = re.match(r"^(?P<code>\d+)\s+(?P<quantity>\d+(?:\.\d+)?)$", body.strip())
    if not match:
        return {"type": "text", "text": "Invalid format.\nSend in format: <ID> <liters>\nExample: 1 5.5"}

    farmer = get_farmer_by_code(match.group("code"))
    if not farmer or not farmer.is_active:
        return {"type": "text", "text": "Invalid ID"}

    existing = get_entry_by_unique_key(farmer.id, now_ist().date(), session_name)
    if existing:
        return {"type": "text", "text": "Duplicate entry for this farmer in this session."}

    current_rate = get_current_rate()
    if not current_rate:
        return {"type": "text", "text": "No active rate found. Change rate first."}

    quantity = money(Decimal(match.group("quantity")))
    entry = create_entry(
        {
            "farmer_id": farmer.id,
            "date": now_ist().date().isoformat(),
            "session": session_name,
            "quantity": str(quantity),
            "rate": str(current_rate.rate),
            "amount": str(money(quantity * current_rate.rate)),
        }
    )
    upsert_whatsapp_state(
        phone,
        "owner",
        f"entry_active_{session_name}",
        context_value=session_name,
        last_entry_id=entry.id,
        last_farmer_id=farmer.id,
    )
    return {
        "type": "buttons",
        "text": f"✅ {farmer.name} - {quantity:.2f}L added successfully\nSend next in format: <ID> <liters>",
        "buttons": ENTRY_ACTION_BUTTONS,
    }


def begin_edit_last_entry(phone, state):
    if not state or not state.last_entry_id:
        return {"type": "text", "text": "No last entry to edit."}
    upsert_whatsapp_state(
        phone,
        "owner",
        "awaiting_edit_quantity",
        context_value=state.context_value,
        last_entry_id=state.last_entry_id,
        last_farmer_id=state.last_farmer_id,
    )
    return {"type": "text", "text": "Send corrected liters only\nExample: 5.8"}


def edit_last_entry(phone, state, body):
    entry = get_entry(state.last_entry_id)
    if not entry:
        clear_whatsapp_state(phone)
        return {"type": "text", "text": "No last entry to edit."}

    try:
        quantity = money(Decimal(body.strip()))
    except Exception:
        return {"type": "text", "text": "Send corrected liters only\nExample: 5.8"}

    update_entry(
        entry.id,
        {
            "farmer_id": entry.farmer_id,
            "date": entry.date.isoformat(),
            "session": entry.session,
            "quantity": str(quantity),
            "rate": str(entry.rate),
            "amount": str(money(quantity * entry.rate)),
        },
    )
    upsert_whatsapp_state(
        phone,
        "owner",
        f"entry_active_{entry.session}",
        context_value=entry.session,
        last_entry_id=entry.id,
        last_farmer_id=entry.farmer_id,
    )
    return {
        "type": "buttons",
        "text": f"✅ Updated to {quantity:.2f}L\nSend next in format: <ID> <liters>",
        "buttons": ENTRY_ACTION_BUTTONS,
    }


def pending_message(session_name):
    pending = pending_for_session(now_ist().date(), session_name)
    if pending:
        lines = [f"{farmer.unique_code} - {farmer.name}" for farmer in pending[:30]]
        text = "Pending Farmers:\n" + "\n".join(lines)
    else:
        text = "Pending Farmers:\nNone"
    return {"type": "buttons", "text": text, "buttons": ENTRY_ACTION_BUTTONS}


def owner_main_menu(prefix_text=None):
    text = "Main Menu"
    if prefix_text:
        text = f"{prefix_text}\n\nMain Menu"
    return {"type": "buttons", "text": text, "buttons": OWNER_MENU_BUTTONS}


def save_new_rate(phone, body):
    try:
        rate = money(Decimal(body.strip()))
    except Exception:
        return {"type": "text", "text": "Invalid rate.\nSend new rate"}
    if rate <= 0:
        return {"type": "text", "text": "Invalid rate.\nSend new rate"}
    create_rate(rate, created_by=phone)
    clear_whatsapp_state(phone)
    return {"type": "buttons", "text": f"✅ New rate saved: Rs. {rate:.2f}", "buttons": OWNER_MENU_BUTTONS}


def handle_farmer_message(phone, body):
    farmer = get_farmer_by_phone(phone, active_only=True)
    if not farmer:
        return {"type": "text", "text": "Your number is not registered. Please contact the milk vendor."}

    normalized = body.lower().strip()
    if normalized in {"hi", "hello", "menu"}:
        return {"type": "text", "text": "Reply with:\nfarmer_today\nfarmer_month_qty\nfarmer_month_amount"}
    if normalized == "farmer_today":
        entry = latest_relevant_farmer_entry(farmer.id, now_ist())
        if not entry:
            return {"type": "text", "text": "No recent milk entry found."}
        return {
            "type": "text",
            "text": f"Latest {entry.session.title()} quantity:\n{entry.quantity:.2f} liters\nAmount: Rs. {entry.amount:.2f}\nDate: {entry.date.isoformat()}",
        }
    if normalized == "farmer_month_qty":
        total_qty, _ = monthly_totals(farmer.id, now_ist().year, now_ist().month)
        return {"type": "text", "text": f"{now_ist():%B} Total Milk:\n{total_qty:.2f} liters"}
    if normalized == "farmer_month_amount":
        _, total_amt = monthly_totals(farmer.id, now_ist().year, now_ist().month)
        return {"type": "text", "text": f"{now_ist():%B} Amount:\nRs. {total_amt:.2f}"}
    return {"type": "text", "text": "Reply with:\nfarmer_today\nfarmer_month_qty\nfarmer_month_amount"}
