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
    latest_relevant_farmer_entry,
    monthly_totals,
    pending_for_session,
    upsert_whatsapp_state,
    update_entry,
)
from app.services.whatsapp_service import send_whatsapp_list, send_whatsapp_message
from app.utils.helpers import money, normalize_phone


logger = logging.getLogger(__name__)
whatsapp_bp = Blueprint("whatsapp", __name__)


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
    logger.info("Incoming WhatsApp webhook payload received.")
    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                for message in change.get("value", {}).get("messages", []):
                    process_message(message)
    except Exception as exc:
        logger.exception("WhatsApp webhook failed: %s", exc)
        return jsonify({"status": "error"}), 500
    return jsonify({"status": "ok"})


def process_message(message):
    phone = normalize_phone(message.get("from"))
    body = extract_message_text(message)
    if not body:
        return
    logger.info("Incoming WhatsApp message from %s: %s", phone, body)
    if phone == normalize_phone(current_app.config["WHATSAPP_OWNER_PHONE"]):
        reply = handle_owner_message(phone, body)
    else:
        reply = handle_farmer_message(phone, body)
    if reply:
        import threading
        threading.Thread(target=send_whatsapp_message, args=(phone, reply)).start()

def extract_message_text(message):
    interactive = message.get("interactive", {})
    if interactive.get("list_reply", {}).get("id"):
        return interactive["list_reply"]["id"]
    return message.get("text", {}).get("body", "").strip()


def handle_owner_message(phone, body):
    normalized = body.lower().strip()
    state = get_whatsapp_state(phone)

    if normalized in {"hi", "hello", "menu", "main_menu"}:
        clear_whatsapp_state(phone)
        return send_owner_menu(phone)
    if normalized in {"owner_entry_morning", "owner_entry_evening"}:
        return start_owner_entry(phone, normalized.replace("owner_entry_", ""))
    if normalized == "owner_rate":
        upsert_whatsapp_state(phone, "owner", "awaiting_rate")
        return "Send new milk rate per liter.\nExample: 42"
    if normalized == "owner_dashboard":
        clear_whatsapp_state(phone)
        return f"Dashboard Link:\n{dashboard_link()}"
    if normalized.startswith("owner_pending_"):
        clear_whatsapp_state(phone)
        return pending_message(normalized.replace("owner_pending_", ""))
    if normalized == "owner_add_next":
        current_state = get_whatsapp_state(phone)
        session_name = current_state.context_value if current_state and current_state.context_value else current_collection_session(now_ist())
        return start_owner_entry(phone, session_name)
    if normalized == "owner_edit_last":
        if not state or not state.last_entry_id:
            return "No recent milk entry found to edit."
        upsert_whatsapp_state(phone, "owner", "awaiting_edit_quantity", context_value=state.context_value, last_entry_id=state.last_entry_id, last_farmer_id=state.last_farmer_id)
        return "Send corrected quantity only.\nExample: 5.8"

    if state and state.state == "awaiting_rate":
        return save_new_rate(phone, body)
    if state and state.state.startswith("awaiting_entry_"):
        return save_owner_entry(phone, state.state.replace("awaiting_entry_", ""), body)
    if state and state.state == "awaiting_edit_quantity":
        return edit_last_entry(phone, state, body)

    return "Send Hi to open the owner milk menu."


def send_owner_menu(phone):
    now = now_ist()
    session_name = current_collection_session(now)
    rows = [
        {"id": "owner_rate", "title": "Change Rate", "description": "Update milk rate"},
        {"id": "owner_dashboard", "title": "Dashboard Link", "description": "Open milk dashboard"},
    ]
    if session_name:
        rows.insert(0, {"id": f"owner_entry_{session_name}", "title": f"{session_name.title()} Entry", "description": "Start milk entry now"})
        rows.append({"id": f"owner_pending_{session_name}", "title": "Pending Today", "description": "See pending farmers"})
    try:
        send_whatsapp_list(phone, "Owner milk menu", "Open Menu", [{"title": "Milk Actions", "rows": rows}], header_text="Milk Assistant")
    except Exception:
        send_whatsapp_message(
            phone,
            "Owner Milk Menu\n"
            + (f"1. {session_name.title()} Entry\n" if session_name else "")
            + "2. Change Rate\n3. Dashboard Link\n"
            + (f"4. Pending Today ({session_name})\n" if session_name else "")
            + "Reply with: "
            + (f"owner_entry_{session_name}, " if session_name else "")
            + "owner_rate, owner_dashboard"
        )
    return None


def start_owner_entry(phone, session_name):
    if current_collection_session(now_ist()) != session_name:
        return f"{session_name.title()} milk entry is disabled right now."
    upsert_whatsapp_state(phone, "owner", f"awaiting_entry_{session_name}", context_value=session_name)
    return f"Start {session_name.title()} Milk Entry\n\nSend format:\n<ID> <Quantity>\n\nExamples:\n1 5.5\n2 7\n3 4.25"


def save_owner_entry(phone, session_name, body):
    if current_collection_session(now_ist()) != session_name:
        clear_whatsapp_state(phone)
        return f"{session_name.title()} session is closed now. Entry not saved."
    match = re.match(r"^(?P<code>\d+)\s+(?P<quantity>\d+(?:\.\d+)?)$", body.strip())
    if not match:
        return "Invalid format.\nSend:\n<ID> <Quantity>\nExample: 1 5.5"
    farmer = get_farmer_by_code(match.group("code"))
    if not farmer or not farmer.is_active:
        return "Invalid farmer ID."
    existing = get_entry_by_unique_key(farmer.id, now_ist().date(), session_name)
    if existing:
        return f"Farmer ID {farmer.unique_code} already entered for today's {session_name}.\nUse Edit option if correction is needed."
    current_rate = get_current_rate()
    if not current_rate:
        return "No active rate found. Change milk rate first."
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
    upsert_whatsapp_state(phone, "owner", f"awaiting_entry_{session_name}", context_value=session_name, last_entry_id=entry.id, last_farmer_id=farmer.id)
    try:
        send_whatsapp_list(
            phone,
            f"{quantity:.2f} liters added for {farmer.name} successfully.",
            "Next Action",
            [{"title": "Entry Actions", "rows": [
                {"id": "owner_edit_last", "title": "Edit Entry", "description": "Correct last quantity"},
                {"id": "owner_add_next", "title": "Add Next", "description": "Enter next farmer"},
                {"id": "main_menu", "title": "Main Menu", "description": "Back to menu"},
                {"id": f"owner_pending_{session_name}", "title": "Pending Today", "description": "See pending farmers"},
            ]}],
            header_text="Entry Saved",
        )
    except Exception:
        send_whatsapp_message(
            phone,
            f"{quantity:.2f} liters added for {farmer.name} successfully.\n"
            "Reply with owner_edit_last, owner_add_next, main_menu, or owner_pending_" + session_name
        )
    return None


def edit_last_entry(phone, state, body):
    entry = get_entry(state.last_entry_id)
    if not entry:
        clear_whatsapp_state(phone)
        return "Previous milk entry not found."
    try:
        quantity = money(Decimal(body.strip()))
    except Exception:
        return "Send only corrected quantity.\nExample: 5.8"
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
    upsert_whatsapp_state(phone, "owner", f"awaiting_entry_{entry.session}", context_value=entry.session, last_entry_id=entry.id, last_farmer_id=entry.farmer_id)
    return f"Updated milk entry successfully.\nNew quantity: {quantity:.2f} liters"


def save_new_rate(phone, body):
    try:
        rate = money(Decimal(body.strip()))
    except Exception:
        return "Invalid rate.\nSend only a number like 42"
    create_rate(rate, created_by=phone)
    clear_whatsapp_state(phone)
    return f"New milk rate saved: Rs. {rate:.2f}\nThis applies only to future entries."


def pending_message(session_name):
    pending = pending_for_session(now_ist().date(), session_name)
    ids = ", ".join(str(farmer.unique_code) for farmer in pending[:20]) or "None"
    return f"Today's {session_name.title()} Pending:\n{len(pending)} farmers remaining.\nPending IDs: {ids}"


def handle_farmer_message(phone, body):
    farmer = get_farmer_by_phone(phone, active_only=True)
    if not farmer:
        return "Your number is not registered. Please contact the milk vendor."
    normalized = body.lower().strip()
    if normalized in {"hi", "hello", "menu"}:
        try:
            send_whatsapp_list(
                phone,
                f"Welcome {farmer.name} Anna",
                "Open Menu",
                [{"title": "Milk Services", "rows": [
                    {"id": "farmer_today", "title": "Today Qty", "description": "See latest quantity"},
                    {"id": "farmer_month_qty", "title": "Month Milk", "description": "See current month liters"},
                    {"id": "farmer_month_amount", "title": "Month Amount", "description": "See current month amount"},
                ]}],
                header_text="Milk Assistant",
            )
        except Exception:
            send_whatsapp_message(
                phone,
                "Farmer Milk Menu\n1. Today Qty\n2. Month Milk\n3. Month Amount\nReply with: farmer_today, farmer_month_qty, farmer_month_amount"
            )
        return None
    if normalized == "farmer_today":
        entry = latest_relevant_farmer_entry(farmer.id, now_ist())
        if not entry:
            return "No recent milk entry found."
        return f"Latest {entry.session.title()} quantity:\n{entry.quantity:.2f} liters\nAmount: Rs. {entry.amount:.2f}\nDate: {entry.date.isoformat()}"
    if normalized == "farmer_month_qty":
        total_qty, _ = monthly_totals(farmer.id, now_ist().year, now_ist().month)
        return f"{now_ist():%B} Total Milk:\n{total_qty:.2f} liters"
    if normalized == "farmer_month_amount":
        _, total_amt = monthly_totals(farmer.id, now_ist().year, now_ist().month)
        return f"{now_ist():%B} Amount:\nRs. {total_amt:.2f}"
    return "Send Hi to open your milk menu."
