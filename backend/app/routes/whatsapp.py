import logging
import re
from decimal import Decimal

from flask import Blueprint, current_app, jsonify, request

from app.services.session_service import dashboard_link, get_active_session, now_ist
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

BUTTON_START_ENTRY = {"id": "start_entry", "title": "Start Entry"}
BUTTON_PENDING_LIST = {"id": "pending_list", "title": "Pending List"}
BUTTON_MAIN_MENU = {"id": "main_menu", "title": "Main Menu"}
BUTTON_CHANGE_RATE = {"id": "change_rate", "title": "Change Rate"}
BUTTON_DASHBOARD = {"id": "dashboard", "title": "Dashboard"}
BUTTON_STOP_ENTRY = {"id": "stop_entry", "title": "Stop Entry"}
BUTTON_EDIT_LAST = {"id": "edit_last", "title": "Edit Last"}


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
    logger.info("event=whatsapp_webhook_received entry_count=%s change_count=%s", len(payload.get("entry", [])), sum(len(entry.get("changes", [])) for entry in payload.get("entry", [])))
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            if "messages" not in value:
                continue
            for message in value.get("messages", []):
                try:
                    process_message(message)
                except Exception as exc:
                    logger.exception("WhatsApp webhook message processing failed: %s", exc)
    return jsonify({"status": "ok"})


def process_message(message):
    message_id = (message.get("id") or "").strip()
    if not message_id:
        logger.info("event=whatsapp_message_skipped reason=missing_message_id")
        return
    if is_processed_message(message_id):
        logger.info("event=whatsapp_message_skipped reason=duplicate message_id=%s", message_id)
        return

    phone = normalize_phone(message.get("from"))
    body = extract_message_text(message)
    mark_message_processed(message_id, phone)
    if not body:
        logger.info("event=whatsapp_message_skipped reason=empty_body message_id=%s phone=%s", message_id, phone)
        return

    logger.info("event=whatsapp_message_received message_id=%s phone=%s body=%s", message_id, phone, body.replace("\n", "\\n"))
    response = handle_owner_message(phone, body) if is_owner_phone(phone) else handle_farmer_message(phone, body)
    dispatch_response(phone, response)


def extract_message_text(message):
    interactive = message.get("interactive", {})
    if interactive.get("button_reply", {}).get("id"):
        return interactive["button_reply"]["id"]
    if interactive.get("list_reply", {}).get("id"):
        return interactive["list_reply"]["id"]
    return ((message.get("text") or {}).get("body") or "").strip()


def dispatch_response(phone, response):
    if not response:
        logger.info("event=whatsapp_response_skipped phone=%s reason=no_response", phone)
        return
    if response["type"] == "buttons":
        logger.info("event=whatsapp_response_send phone=%s type=buttons button_count=%s", phone, len(response["buttons"]))
        send_owner_buttons(phone, response["text"], response["buttons"])
        return
    if response["type"] == "text":
        logger.info("event=whatsapp_response_send phone=%s type=text", phone)
        send_whatsapp_message(phone, response["text"])


def send_owner_buttons(phone, text, buttons):
    send_whatsapp_buttons(phone, text, buttons[:3])


def is_owner_phone(phone):
    normalized = normalize_phone(phone)
    allowed = {
        normalize_phone(value)
        for value in current_app.config.get("ADMIN_WHATSAPP_NUMBERS", [])
        if value
    }
    owner_phone = normalize_phone(current_app.config.get("WHATSAPP_OWNER_PHONE", ""))
    if owner_phone:
        allowed.add(owner_phone)
    return normalized in allowed


def handle_owner_message(phone, body):
    state = get_whatsapp_state(phone)
    return process_owner_flow(phone, body, state)


def process_owner_flow(phone, body, state):
    now = now_ist()
    active_session = get_active_session(now)
    normalized = body.strip().lower()

    if state and state.state == "awaiting_rate":
        return save_new_rate(phone, body, active_session, state)

    if state and state.state == "awaiting_edit_quantity":
        if not active_session:
            clear_whatsapp_state(phone)
            return closed_collection_response()
        return edit_last_entry(phone, state, body, active_session)

    if normalized == "dashboard":
        return {"type": "text", "text": dashboard_link()}

    if normalized == "change_rate":
        upsert_whatsapp_state(
            phone,
            "owner",
            "awaiting_rate",
            context_value=active_session,
            last_entry_id=state.last_entry_id if state else None,
            last_farmer_id=state.last_farmer_id if state else None,
        )
        return {"type": "text", "text": "Send new rate"}

    if not active_session:
        clear_whatsapp_state(phone)
        return closed_collection_response()

    if state and state.state.startswith("entry_active_"):
        state_session = state.state.replace("entry_active_", "", 1)
        if state_session != active_session:
            clear_whatsapp_state(phone)
            return session_entry_prompt(active_session)

        if normalized == "start_entry":
            return start_entry(phone, active_session, state)
        if normalized == "pending_list":
            return pending_list_response(active_session)
        if normalized == "main_menu":
            return owner_main_menu(active_session, entry_started=True)
        if normalized == "stop_entry":
            clear_whatsapp_state(phone)
            return {"type": "text", "text": "Entry stopped"}
        if normalized == "edit_last":
            return begin_edit_last_entry(phone, state)
        return save_owner_entry(phone, active_session, body, state)

    if normalized in {"hi", "hello", "start", "menu"}:
        return session_entry_prompt(active_session)

    if normalized == "start_entry":
        return start_entry(phone, active_session, state)

    if normalized == "pending_list":
        return pending_list_response(active_session)

    if normalized == "main_menu":
        return owner_main_menu(active_session, entry_started=False)

    if normalized == "stop_entry":
        return {"type": "text", "text": "Milk collection is currently closed."}

    return session_entry_prompt(active_session)


def closed_collection_response():
    return {
        "type": "buttons",
        "text": "Milk collection is currently closed.",
        "buttons": [BUTTON_DASHBOARD, BUTTON_CHANGE_RATE],
    }


def session_entry_prompt(session_name):
    return {
        "type": "buttons",
        "text": f"Start {session_name} milk entry?",
        "buttons": [BUTTON_START_ENTRY, BUTTON_PENDING_LIST, BUTTON_MAIN_MENU],
    }


def owner_main_menu(session_name, entry_started):
    buttons = [BUTTON_CHANGE_RATE, BUTTON_DASHBOARD]
    if session_name:
        buttons.append(BUTTON_STOP_ENTRY if entry_started else BUTTON_START_ENTRY)
    return {"type": "buttons", "text": "Main Menu", "buttons": buttons}


def start_entry(phone, session_name, state):
    upsert_whatsapp_state(
        phone,
        "owner",
        f"entry_active_{session_name}",
        context_value=session_name,
        last_entry_id=state.last_entry_id if state else None,
        last_farmer_id=state.last_farmer_id if state else None,
    )
    return {"type": "text", "text": "Send: <ID> <Liters>\nExample: 1 5.5"}


def save_owner_entry(phone, session_name, body, state):
    if get_active_session(now_ist()) != session_name:
        clear_whatsapp_state(phone)
        return closed_collection_response()

    match = re.match(r"^(?P<code>\d+)\s+(?P<quantity>\d+(?:\.\d+)?)$", body.strip())
    if not match:
        return {"type": "text", "text": "Invalid format.\nSend: <ID> <Liters>\nExample: 1 5.5"}

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
        "text": f"OK: {farmer.name} - {quantity:.2f}L added\nSend: <ID> <Liters>",
        "buttons": [BUTTON_EDIT_LAST, BUTTON_PENDING_LIST, BUTTON_MAIN_MENU],
    }


def begin_edit_last_entry(phone, state):
    if not state or not state.last_entry_id:
        return {"type": "text", "text": "Invalid ID"}
    upsert_whatsapp_state(
        phone,
        "owner",
        "awaiting_edit_quantity",
        context_value=state.context_value,
        last_entry_id=state.last_entry_id,
        last_farmer_id=state.last_farmer_id,
    )
    return {"type": "text", "text": "Send corrected liters only\nExample: 5.8"}


def edit_last_entry(phone, state, body, active_session):
    entry = get_entry(state.last_entry_id)
    if not entry:
        clear_whatsapp_state(phone)
        return {"type": "text", "text": "Invalid ID"}
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
        f"entry_active_{active_session}",
        context_value=active_session,
        last_entry_id=entry.id,
        last_farmer_id=entry.farmer_id,
    )
    return {
        "type": "buttons",
        "text": f"OK: Updated to {quantity:.2f}L\nSend: <ID> <Liters>",
        "buttons": [BUTTON_EDIT_LAST, BUTTON_PENDING_LIST, BUTTON_MAIN_MENU],
    }


def pending_list_response(session_name):
    pending = pending_for_session(now_ist().date(), session_name)
    if pending:
        text = "Pending Farmers:\n" + "\n".join(f"{farmer.unique_code} - {farmer.name}" for farmer in pending[:30])
    else:
        text = "Pending Farmers:\nNone"
    return {"type": "buttons", "text": text, "buttons": [BUTTON_EDIT_LAST, BUTTON_PENDING_LIST, BUTTON_MAIN_MENU]}


def save_new_rate(phone, body, active_session, state):
    try:
        rate = money(Decimal(body.strip()))
    except Exception:
        return {"type": "text", "text": "Invalid rate.\nSend new rate"}
    if rate <= 0:
        return {"type": "text", "text": "Invalid rate.\nSend new rate"}
    create_rate(rate, created_by=phone)
    confirmation_text = f"OK: New rate saved: Rs. {rate:.2f}"
    if active_session and state and state.context_value == active_session:
        upsert_whatsapp_state(
            phone,
            "owner",
            f"entry_active_{active_session}",
            context_value=active_session,
            last_entry_id=state.last_entry_id,
            last_farmer_id=state.last_farmer_id,
        )
        return {"type": "buttons", "text": confirmation_text, "buttons": [BUTTON_EDIT_LAST, BUTTON_PENDING_LIST, BUTTON_MAIN_MENU]}
    clear_whatsapp_state(phone)
    if active_session:
        response = owner_main_menu(active_session, entry_started=False)
        response["text"] = confirmation_text
        return response
    return {"type": "buttons", "text": confirmation_text, "buttons": [BUTTON_DASHBOARD, BUTTON_CHANGE_RATE]}


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
        return {"type": "text", "text": f"Latest {entry.session.title()} quantity:\n{entry.quantity:.2f} liters\nAmount: Rs. {entry.amount:.2f}\nDate: {entry.date.isoformat()}"}
    if normalized == "farmer_month_qty":
        total_qty, _ = monthly_totals(farmer.id, now_ist().year, now_ist().month)
        return {"type": "text", "text": f"{now_ist():%B} Total Milk:\n{total_qty:.2f} liters"}
    if normalized == "farmer_month_amount":
        _, total_amt = monthly_totals(farmer.id, now_ist().year, now_ist().month)
        return {"type": "text", "text": f"{now_ist():%B} Amount:\nRs. {total_amt:.2f}"}
    return {"type": "text", "text": "Reply with:\nfarmer_today\nfarmer_month_qty\nfarmer_month_amount"}
