from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from functools import lru_cache
import hashlib
import json
import logging

from flask import current_app
from supabase import Client, create_client
from supabase.client import ClientOptions
from werkzeug.security import generate_password_hash

from app.models import (
    Admin,
    Farmer,
    MilkEntry,
    MonthlySettlement,
    Payment,
    PaymentLog,
    Rate,
    StoreTransaction,
    StoreTransactionItem,
    WhatsAppState,
)
from app.utils.helpers import money, normalize_phone

from .migration_service import attempt_database_self_heal


logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _client_for(url, key, schema):
    return create_client(url, key, options=ClientOptions(schema=schema, postgrest_client_timeout=20))


def get_raw_client() -> Client:
    cfg = current_app.config
    return _client_for(cfg["SUPABASE_URL"].strip(), cfg["SUPABASE_KEY"].strip(), cfg["SUPABASE_SCHEMA"].strip())


def get_client() -> Client:
    return SafeClientProxy(get_raw_client())


def _table(name):
    return get_client().table(name)


def _single(response):
    rows = response.data or []
    return rows[0] if rows else None


class SafeClientProxy:
    def __init__(self, client: Client):
        self._client = client

    def table(self, name):
        return SafeQueryProxy(self._client.table(name), table_name=name)

    def __getattr__(self, item):
        return getattr(self._client, item)


class SafeQueryProxy:
    def __init__(self, builder, table_name=None):
        self._builder = builder
        self._table_name = table_name or "<unknown>"

    def execute(self):
        logger.info("Supabase table access: %s", self._table_name)
        try:
            return self._builder.execute()
        except Exception as exc:
            logger.exception("Supabase query failed on table %s", self._table_name)
            if attempt_database_self_heal(exc, self._table_name):
                logger.info("Retrying Supabase query after self-heal: %s", self._table_name)
                return self._builder.execute()
            raise

    def __getattr__(self, item):
        attr = getattr(self._builder, item)
        if not callable(attr):
            return attr

        def wrapper(*args, **kwargs):
            result = attr(*args, **kwargs)
            if hasattr(result, "execute"):
                return SafeQueryProxy(result, table_name=self._table_name)
            return result

        return wrapper


def _date_str(value):
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)


def _ts_str(value):
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _month_start(year, month):
    return date(year, month, 1)


def _month_end(year, month):
    if month == 12:
        return date(year + 1, 1, 1) - timedelta(days=1)
    return date(year, month + 1, 1) - timedelta(days=1)


def get_admin_by_id(admin_id):
    row = _single(_table("admins").select("*").eq("id", int(admin_id)).limit(1).execute())
    return Admin.from_dict(row) if row else None


def get_admin_by_phone(phone):
    row = _single(_table("admins").select("*").eq("phone", normalize_phone(phone)).limit(1).execute())
    return Admin.from_dict(row) if row else None


def update_admin_password(admin_id, new_password):
    password_hash = generate_password_hash(new_password)
    row = _single(_table("admins").update({"password_hash": password_hash}).eq("id", int(admin_id)).execute())
    return Admin.from_dict(row) if row else None


def update_admin_password_by_phone(phone, new_password):
    password_hash = generate_password_hash(new_password)
    row = _single(_table("admins").update({"password_hash": password_hash}).eq("phone", normalize_phone(phone)).execute())
    return Admin.from_dict(row) if row else None


def list_farmers(search=None, active_only=False):
    farmers = [Farmer.from_dict(row) for row in (_table("farmers").select("*").order("unique_code").execute().data or [])]
    if active_only:
        farmers = [farmer for farmer in farmers if farmer.is_active]
    if search:
        term = search.lower()
        farmers = [
            farmer
            for farmer in farmers
            if term in farmer.name.lower()
            or term in farmer.phone.lower()
            or term in str(farmer.unique_code)
            or term in (farmer.village or "").lower()
        ]
    return farmers


def get_farmer(farmer_id):
    row = _single(_table("farmers").select("*").eq("id", int(farmer_id)).limit(1).execute())
    return Farmer.from_dict(row) if row else None


def get_farmer_by_phone(phone, active_only=False):
    row = _single(_table("farmers").select("*").eq("phone", normalize_phone(phone)).limit(1).execute())
    if not row:
        return None
    farmer = Farmer.from_dict(row)
    if active_only and not farmer.is_active:
        return None
    return farmer


def get_farmer_by_code(unique_code):
    row = _single(_table("farmers").select("*").eq("unique_code", int(unique_code)).limit(1).execute())
    return Farmer.from_dict(row) if row else None


def find_farmer_conflicts(unique_code=None, name=None, phone=None, exclude_farmer_id=None):
    conflicts = {}
    normalized_name = (name or "").strip().lower()
    normalized_phone = normalize_phone(phone) if phone else None

    for farmer in list_farmers():
        if exclude_farmer_id and farmer.id == int(exclude_farmer_id):
            continue
        if unique_code not in (None, "") and int(farmer.unique_code) == int(unique_code):
            conflicts["unique_code"] = farmer
        if normalized_name and farmer.name.strip().lower() == normalized_name:
            conflicts["name"] = farmer
        if normalized_phone and farmer.phone == normalized_phone:
            conflicts["phone"] = farmer
    return conflicts


def create_farmer(payload):
    row = _single(_table("farmers").insert(payload).execute())
    return Farmer.from_dict(row)


def update_farmer(farmer_id, payload):
    row = _single(_table("farmers").update(payload).eq("id", int(farmer_id)).execute())
    return Farmer.from_dict(row) if row else None


def list_entries(entry_date=None, session=None, farmer_id=None):
    query = _table("milk_entries").select("*").order("date", desc=True).order("session").order("created_at", desc=True)
    if entry_date:
        query = query.eq("date", _date_str(entry_date))
    if session:
        query = query.eq("session", session)
    if farmer_id:
        query = query.eq("farmer_id", int(farmer_id))
    entries = [MilkEntry.from_dict(row) for row in (query.execute().data or [])]
    _attach_farmers(entries)
    return entries


def get_entry(entry_id):
    row = _single(_table("milk_entries").select("*").eq("id", int(entry_id)).limit(1).execute())
    if not row:
        return None
    entry = MilkEntry.from_dict(row)
    _attach_farmers([entry])
    return entry


def get_entry_by_unique_key(farmer_id, entry_date, session):
    row = _single(
        _table("milk_entries").select("*").eq("farmer_id", int(farmer_id)).eq("date", _date_str(entry_date)).eq("session", session).limit(1).execute()
    )
    if not row:
        return None
    entry = MilkEntry.from_dict(row)
    _attach_farmers([entry])
    return entry


def create_entry(payload):
    _validate_entry_payload(payload)
    row = _single(_table("milk_entries").insert(payload).execute())
    entry = MilkEntry.from_dict(row)
    _attach_farmers([entry])
    return entry


def update_entry(entry_id, payload):
    _validate_entry_payload(payload)
    row = _single(_table("milk_entries").update(payload).eq("id", int(entry_id)).execute())
    if not row:
        return None
    entry = MilkEntry.from_dict(row)
    _attach_farmers([entry])
    return entry


def list_payments(farmer_id=None):
    query = _table("payments").select("*").order("payment_date", desc=True)
    if farmer_id:
        query = query.eq("farmer_id", int(farmer_id))
    payments = [Payment.from_dict(row) for row in (query.execute().data or [])]
    _attach_farmers(payments)
    return payments


def create_payment(payload):
    row = _single(_table("payments").insert(payload).execute())
    payment = Payment.from_dict(row)
    _attach_farmers([payment])
    return payment


def delete_payment(payment_id):
    _table("payments").delete().eq("id", int(payment_id)).execute()


def list_rates():
    return [Rate.from_dict(row) for row in (_table("rates").select("*").order("effective_from", desc=True).execute().data or [])]


def get_current_rate():
    row = _single(_table("rates").select("*").order("effective_from", desc=True).limit(1).execute())
    return Rate.from_dict(row) if row else None


def create_rate(rate, created_by):
    row = _single(
        _table("rates").insert({"rate": str(money(rate)), "effective_from": _ts_str(datetime.utcnow()), "created_by": created_by}).execute()
    )
    return Rate.from_dict(row)


def get_whatsapp_state(phone):
    row = _single(_table("whatsapp_states").select("*").eq("phone", normalize_phone(phone)).limit(1).execute())
    return WhatsAppState.from_dict(row) if row else None


def upsert_whatsapp_state(phone, role, state, context_value=None, last_entry_id=None, last_farmer_id=None):
    row = _single(
        _table("whatsapp_states")
        .upsert(
            {
                "phone": normalize_phone(phone),
                "role": role,
                "state": state,
                "context_value": context_value,
                "last_entry_id": last_entry_id,
                "last_farmer_id": last_farmer_id,
                "updated_at": _ts_str(datetime.utcnow()),
            },
            on_conflict="phone",
        )
        .execute()
    )
    return WhatsAppState.from_dict(row)


def clear_whatsapp_state(phone):
    _table("whatsapp_states").delete().eq("phone", normalize_phone(phone)).execute()


def is_processed_message(message_id):
    if not message_id:
        return False
    row = _single(_table("processed_messages").select("message_id").eq("message_id", message_id).limit(1).execute())
    return bool(row)


def mark_message_processed(message_id, phone):
    if not message_id:
        return
    _table("processed_messages").upsert(
        {
            "message_id": message_id,
            "phone": normalize_phone(phone),
            "processed_at": _ts_str(datetime.utcnow()),
        },
        on_conflict="message_id",
    ).execute()


def is_session_closed_recorded(target_date, session_name):
    row = _single(
        _table("session_closures")
        .select("id")
        .eq("target_date", _date_str(target_date))
        .eq("session_name", session_name)
        .eq("is_closed", True)
        .limit(1)
        .execute()
    )
    return bool(row)


def mark_session_closed(target_date, session_name):
    _table("session_closures").upsert(
        {
            "session_name": session_name,
            "target_date": _date_str(target_date),
            "is_closed": True,
            "created_at": _ts_str(datetime.utcnow()),
        },
        on_conflict="session_name,target_date",
    ).execute()


def farmer_balance(farmer_id):
    total_amount = sum((entry.amount for entry in list_entries(farmer_id=farmer_id)), Decimal("0.00"))
    paid = sum((payment.amount_paid for payment in list_payments(farmer_id=farmer_id)), Decimal("0.00"))
    return money(total_amount - paid)


def dashboard_metrics(today, session_name=None):
    entries = list_entries()
    today_entries = [entry for entry in entries if entry.date == today]
    month_entries = [entry for entry in entries if entry.date.year == today.year and entry.date.month == today.month]
    morning_count = len([entry for entry in today_entries if entry.session == "morning"])
    evening_count = len([entry for entry in today_entries if entry.session == "evening"])
    pending = 0
    if session_name:
        pending = len(pending_for_session(today, session_name))
    return {
        "today_total_liters": money(sum((entry.quantity for entry in today_entries), Decimal("0.00"))),
        "morning_collected_count": morning_count,
        "evening_collected_count": evening_count,
        "pending_farmers": pending,
        "this_month_total_payout": money(sum((entry.amount for entry in month_entries), Decimal("0.00"))),
    }


def pending_for_session(entry_date, session_name):
    active_farmers = list_farmers(active_only=True)
    entered_ids = {entry.farmer_id for entry in list_entries(entry_date=entry_date, session=session_name)}
    return [farmer for farmer in active_farmers if farmer.id not in entered_ids]


def auto_fill_zero_entries(entry_date, session_name):
    current_rate = get_current_rate()
    applied_rate = current_rate.rate if current_rate else Decimal("0.00")
    created = 0
    for farmer in pending_for_session(entry_date, session_name):
        if get_entry_by_unique_key(farmer.id, entry_date, session_name):
            continue
        create_entry(
            {
                "farmer_id": farmer.id,
                "date": _date_str(entry_date),
                "session": session_name,
                "quantity": "0.00",
                "rate": str(applied_rate),
                "amount": "0.00",
            }
        )
        created += 1
    return created


def get_app_setting(key, default=None):
    row = _single(_table("app_settings").select("*").eq("key", key).limit(1).execute())
    if not row:
        return default
    return row.get("value", default)


def get_app_settings(keys, defaults=None):
    defaults = defaults or {}
    rows = _table("app_settings").select("*").in_("key", list(keys)).execute().data or []
    values = {row["key"]: row.get("value") for row in rows}
    return {key: values.get(key, defaults.get(key)) for key in keys}


def set_app_setting(key, value):
    _table("app_settings").upsert([{"key": key, "value": str(value)}], on_conflict="key").execute()


def monthly_totals(farmer_id, year, month):
    entries = [entry for entry in list_entries(farmer_id=farmer_id) if entry.date.year == year and entry.date.month == month]
    total_qty = money(sum((entry.quantity for entry in entries), Decimal("0.00")))
    total_amt = money(sum((entry.amount for entry in entries), Decimal("0.00")))
    return total_qty, total_amt


def latest_relevant_farmer_entry(farmer_id, current_dt):
    target_date = current_dt.date() - timedelta(days=1) if current_dt.hour < 6 else current_dt.date()
    entries = [entry for entry in list_entries(farmer_id=farmer_id) if entry.date == target_date]
    for preferred in ("evening", "morning"):
        for entry in entries:
            if entry.session == preferred:
                return entry
    return entries[0] if entries else None


def farmer_last_month_statement_data(farmer_id, year, month):
    entries = [entry for entry in list_entries(farmer_id=farmer_id) if entry.date.year == year and entry.date.month == month]
    payments = [payment for payment in list_payments(farmer_id=farmer_id) if payment.payment_date.year == year and payment.payment_date.month == month]
    return entries, payments


def monthly_farmer_summary(year, month):
    grouped = defaultdict(lambda: {"farmer_id": None, "farmer_name": "", "total_quantity": Decimal("0.00"), "total_amount": Decimal("0.00")})
    for entry in list_entries():
        if entry.date.year == year and entry.date.month == month:
            bucket = grouped[entry.farmer_id]
            bucket["farmer_id"] = entry.farmer_id
            bucket["farmer_name"] = entry.farmer.name if entry.farmer else str(entry.farmer_id)
            bucket["total_quantity"] += entry.quantity
            bucket["total_amount"] += entry.amount
    return sorted(grouped.values(), key=lambda item: item["farmer_name"].lower())


def yearly_totals():
    grouped = defaultdict(lambda: {"year": 0, "total_quantity": Decimal("0.00"), "total_amount": Decimal("0.00")})
    for entry in list_entries():
        bucket = grouped[entry.date.year]
        bucket["year"] = entry.date.year
        bucket["total_quantity"] += entry.quantity
        bucket["total_amount"] += entry.amount
    return [grouped[year] for year in sorted(grouped)]


def create_store_transaction(farmer_id, bill_date, items, note=None, entry_source="dashboard"):
    bill_date = date.fromisoformat(bill_date) if isinstance(bill_date, str) else bill_date
    if is_month_settlement_locked(farmer_id, bill_date.year, bill_date.month):
        raise ValueError("This farmer's month is locked after settlement. Unlock settlement before editing.")

    cleaned_items = []
    for item in items:
        item_name = (item.get("item_name") or "").strip()
        if not item_name:
            continue
        quantity = money(item.get("quantity") or 0)
        unit_price = money(item.get("unit_price") or 0)
        unit = (item.get("unit") or "").strip() or None
        subtotal = money(item.get("subtotal") or (quantity * unit_price))
        cleaned_items.append(
            {
                "item_name": item_name,
                "quantity": quantity,
                "unit": unit,
                "unit_price": unit_price,
                "subtotal": subtotal,
            }
        )
    if not cleaned_items:
        raise ValueError("At least one item is required.")

    duplicate_guard = _store_duplicate_guard(farmer_id, bill_date, cleaned_items)
    existing = _single(_table("store_transactions").select("*").eq("duplicate_guard", duplicate_guard).limit(1).execute())
    if existing:
        raise ValueError("Duplicate store transaction detected.")

    total_amount = money(sum((item["subtotal"] for item in cleaned_items), Decimal("0.00")))
    transaction_row = _single(
        _table("store_transactions")
        .insert(
            {
                "farmer_id": int(farmer_id),
                "bill_date": _date_str(bill_date),
                "item_count": len(cleaned_items),
                "total_amount": str(total_amount),
                "note": note,
                "entry_source": entry_source,
                "duplicate_guard": duplicate_guard,
                "is_locked": False,
                "updated_at": _ts_str(datetime.utcnow()),
            }
        )
        .execute()
    )
    transaction = StoreTransaction.from_dict(transaction_row)

    item_rows = []
    for item in cleaned_items:
        item_rows.append(
            {
                "transaction_id": transaction.id,
                "item_name": item["item_name"],
                "quantity": str(item["quantity"]),
                "unit": item["unit"],
                "unit_price": str(item["unit_price"]),
                "subtotal": str(item["subtotal"]),
            }
        )
    if item_rows:
        _table("store_transaction_items").insert(item_rows).execute()
    return get_store_transaction(transaction.id)


def list_store_transactions(year=None, month=None, farmer_id=None, search=None):
    query = _table("store_transactions").select("*").order("bill_date", desc=True).order("created_at", desc=True)
    if farmer_id:
        query = query.eq("farmer_id", int(farmer_id))
    if year and month:
        query = query.gte("bill_date", _month_start(year, month).isoformat()).lte("bill_date", _month_end(year, month).isoformat())
    transactions = [StoreTransaction.from_dict(row) for row in (query.execute().data or [])]
    _attach_farmers(transactions)
    _attach_store_items(transactions)
    if search:
        term = search.lower()
        transactions = [
            tx
            for tx in transactions
            if (tx.farmer and (term in tx.farmer.name.lower() or term in tx.farmer.phone.lower() or term in str(tx.farmer.unique_code)))
        ]
    return transactions


def get_store_transaction(transaction_id):
    row = _single(_table("store_transactions").select("*").eq("id", int(transaction_id)).limit(1).execute())
    if not row:
        return None
    tx = StoreTransaction.from_dict(row)
    _attach_farmers([tx])
    _attach_store_items([tx])
    return tx


def monthly_store_totals(farmer_id, year, month):
    transactions = list_store_transactions(year=year, month=month, farmer_id=farmer_id)
    return money(sum((tx.total_amount for tx in transactions), Decimal("0.00")))


def top_shop_buyers(year, month, limit=5, transactions=None):
    grouped = defaultdict(lambda: {"farmer_name": "", "farmer_id": None, "total_amount": Decimal("0.00")})
    transactions = transactions if transactions is not None else list_store_transactions(year=year, month=month)
    for tx in transactions:
        bucket = grouped[tx.farmer_id]
        bucket["farmer_id"] = tx.farmer_id
        bucket["farmer_name"] = tx.farmer.name if tx.farmer else str(tx.farmer_id)
        bucket["total_amount"] += tx.total_amount
    buyers = sorted(grouped.values(), key=lambda row: row["total_amount"], reverse=True)
    return buyers[:limit]


def farmer_ledger(farmer_id, year, month):
    milk_entries = [entry for entry in list_entries(farmer_id=farmer_id) if entry.date.year == year and entry.date.month == month]
    store_transactions = list_store_transactions(year=year, month=month, farmer_id=farmer_id)
    settlements = [row for row in list_settlements(year=year, month=month) if row.farmer_id == farmer_id]
    payment_logs = [row for row in list_payment_logs(farmer_id=farmer_id) if row.payment_date.year == year and row.payment_date.month == month]
    milk_total_qty, milk_total_amount = monthly_totals(farmer_id, year, month)
    store_total = monthly_store_totals(farmer_id, year, month)
    net_amount = money(milk_total_amount - store_total)
    paid_to_farmer = money(sum((row.amount for row in payment_logs if row.direction == "to_farmer"), Decimal("0.00")))
    recovered_from_farmer = money(sum((row.amount for row in payment_logs if row.direction == "from_farmer"), Decimal("0.00")))
    final_balance = settlement_running_balance(net_amount, paid_to_farmer, recovered_from_farmer)
    return {
        "milk_entries": milk_entries,
        "store_transactions": store_transactions,
        "settlements": settlements,
        "payment_logs": payment_logs,
        "milk_total_quantity": milk_total_qty,
        "milk_total_amount": milk_total_amount,
        "store_total": store_total,
        "net_amount": net_amount,
        "paid_to_farmer": paid_to_farmer,
        "recovered_from_farmer": recovered_from_farmer,
        "final_balance": final_balance,
        "status": settlement_status(net_amount),
        "final_status": settlement_status(final_balance),
    }


def settlement_status(net_amount):
    if net_amount > 0:
        return "Pay Farmer"
    if net_amount < 0:
        return "Farmer Owes"
    return "Settled"


def settlement_running_balance(net_amount, paid_to_farmer=Decimal("0.00"), recovered_from_farmer=Decimal("0.00")):
    return money(net_amount - paid_to_farmer + recovered_from_farmer)


def settlement_summary(year, month):
    farmers = list_farmers(active_only=False)
    month_entries = [entry for entry in list_entries() if entry.date.year == year and entry.date.month == month]
    month_store_transactions = list_store_transactions(year=year, month=month)
    locked_settlements = {row.farmer_id: row for row in list_settlements(year=year, month=month)}
    month_payment_logs = [row for row in list_payment_logs() if row.payment_date.year == year and row.payment_date.month == month]

    milk_by_farmer = defaultdict(lambda: {"quantity": Decimal("0.00"), "amount": Decimal("0.00")})
    for entry in month_entries:
        bucket = milk_by_farmer[entry.farmer_id]
        bucket["quantity"] += entry.quantity
        bucket["amount"] += entry.amount

    store_by_farmer = defaultdict(lambda: Decimal("0.00"))
    for tx in month_store_transactions:
        store_by_farmer[tx.farmer_id] += tx.total_amount

    paid_to_farmer_by_farmer = defaultdict(lambda: Decimal("0.00"))
    recovered_from_farmer_by_farmer = defaultdict(lambda: Decimal("0.00"))
    for log in month_payment_logs:
        if log.direction == "to_farmer":
            paid_to_farmer_by_farmer[log.farmer_id] += log.amount
        elif log.direction == "from_farmer":
            recovered_from_farmer_by_farmer[log.farmer_id] += log.amount

    rows = []
    for farmer in farmers:
        milk_qty = money(milk_by_farmer[farmer.id]["quantity"])
        milk_total = money(milk_by_farmer[farmer.id]["amount"])
        store_total = money(store_by_farmer[farmer.id])
        paid_to_farmer = money(paid_to_farmer_by_farmer[farmer.id])
        recovered_from_farmer = money(recovered_from_farmer_by_farmer[farmer.id])
        if milk_qty == Decimal("0.00") and store_total == Decimal("0.00") and paid_to_farmer == Decimal("0.00") and recovered_from_farmer == Decimal("0.00"):
            continue
        net_amount = money(milk_total - store_total)
        final_balance = settlement_running_balance(net_amount, paid_to_farmer, recovered_from_farmer)
        locked = locked_settlements.get(farmer.id)
        rows.append(
            {
                "farmer_id": farmer.id,
                "farmer_code": farmer.unique_code,
                "farmer_name": farmer.name,
                "milk_total": milk_total,
                "milk_quantity": milk_qty,
                "shop_credit_total": store_total,
                "net_amount": net_amount,
                "status": settlement_status(net_amount),
                "paid_to_farmer": paid_to_farmer,
                "recovered_from_farmer": recovered_from_farmer,
                "final_balance": final_balance,
                "final_status": settlement_status(final_balance),
                "is_locked": bool(locked and locked.is_locked),
            }
        )
    return sorted(rows, key=lambda row: (row["status"], row["farmer_code"]))


def get_monthly_settlement(farmer_id, year, month):
    settlement_month = _month_start(year, month)
    row = _single(
        _table("monthly_settlements").select("*").eq("farmer_id", int(farmer_id)).eq("settlement_month", settlement_month.isoformat()).limit(1).execute()
    )
    if not row:
        return None
    settlement = MonthlySettlement.from_dict(row)
    _attach_farmers([settlement])
    return settlement


def is_month_settlement_locked(farmer_id, year, month):
    settlement = get_monthly_settlement(farmer_id, year, month)
    return bool(settlement and settlement.is_locked)


def list_settlements(year=None, month=None):
    query = _table("monthly_settlements").select("*").order("settlement_month", desc=True).order("created_at", desc=True)
    if year and month:
        query = query.eq("settlement_month", _month_start(year, month).isoformat())
    rows = [MonthlySettlement.from_dict(row) for row in (query.execute().data or [])]
    _attach_farmers(rows)
    return rows


def create_or_update_monthly_settlement(farmer_id, year, month, note=None):
    milk_qty, milk_total = monthly_totals(farmer_id, year, month)
    store_total = monthly_store_totals(farmer_id, year, month)
    net_amount = money(milk_total - store_total)
    payload = {
        "farmer_id": int(farmer_id),
        "settlement_month": _month_start(year, month).isoformat(),
        "milk_total": str(milk_total),
        "store_credit_total": str(store_total),
        "net_amount": str(net_amount),
        "status": settlement_status(net_amount),
        "is_locked": True,
        "settled_on": _ts_str(datetime.utcnow()),
        "note": note,
        "updated_at": _ts_str(datetime.utcnow()),
    }
    row = _single(_table("monthly_settlements").upsert(payload, on_conflict="farmer_id,settlement_month").execute())
    settlement = MonthlySettlement.from_dict(row)
    _attach_farmers([settlement])
    _lock_month_transactions(farmer_id, year, month, True)
    return settlement


def unlock_monthly_settlement(farmer_id, year, month):
    settlement_month = _month_start(year, month).isoformat()
    _table("monthly_settlements").update({"is_locked": False, "updated_at": _ts_str(datetime.utcnow())}).eq("farmer_id", int(farmer_id)).eq(
        "settlement_month", settlement_month
    ).execute()
    _lock_month_transactions(farmer_id, year, month, False)


def list_payment_logs(farmer_id=None):
    query = _table("payment_logs").select("*").order("payment_date", desc=True).order("created_at", desc=True)
    if farmer_id:
        query = query.eq("farmer_id", int(farmer_id))
    logs = [PaymentLog.from_dict(row) for row in (query.execute().data or [])]
    _attach_farmers(logs)
    return logs


def create_payment_log(payload):
    row = _single(_table("payment_logs").insert(payload).execute())
    payment_log = PaymentLog.from_dict(row)
    _attach_farmers([payment_log])
    return payment_log


def store_purchase_lines_to_items(lines):
    items = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) < 3:
            raise ValueError("Use: Item | Quantity | Price")
        item_name = parts[0]
        quantity_text = parts[1]
        unit = None
        numeric_qty = ""
        for char in quantity_text:
            if char.isdigit() or char == ".":
                numeric_qty += char
            else:
                unit = (unit or "") + char
        quantity = money(numeric_qty or "1")
        unit_price = money(parts[2])
        items.append(
            {
                "item_name": item_name,
                "quantity": quantity,
                "unit": unit.strip() if unit else None,
                "unit_price": unit_price,
                "subtotal": money(quantity * unit_price),
            }
        )
    return items


def get_store_whatsapp_draft(phone):
    raw = get_app_setting(f"wa_store_draft_{normalize_phone(phone)}")
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


def set_store_whatsapp_draft(phone, payload):
    set_app_setting(f"wa_store_draft_{normalize_phone(phone)}", json.dumps(payload))


def clear_store_whatsapp_draft(phone):
    set_app_setting(f"wa_store_draft_{normalize_phone(phone)}", "")


def _store_duplicate_guard(farmer_id, bill_date, items):
    normalized = json.dumps(
        {
            "farmer_id": int(farmer_id),
            "bill_date": _date_str(bill_date),
            "items": [
                {
                    "item_name": item["item_name"].strip().lower(),
                    "quantity": str(money(item["quantity"])),
                    "unit": (item.get("unit") or "").strip().lower(),
                    "unit_price": str(money(item["unit_price"])),
                    "subtotal": str(money(item["subtotal"])),
                }
                for item in items
            ],
        },
        sort_keys=True,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _lock_month_transactions(farmer_id, year, month, is_locked):
    start = _month_start(year, month).isoformat()
    end = _month_end(year, month).isoformat()
    _table("store_transactions").update({"is_locked": is_locked, "updated_at": _ts_str(datetime.utcnow())}).eq("farmer_id", int(farmer_id)).gte(
        "bill_date", start
    ).lte("bill_date", end).execute()


def _attach_farmers(records):
    farmers = {farmer.id: farmer for farmer in list_farmers()}
    for record in records:
        farmer_id = getattr(record, "farmer_id", None)
        if farmer_id:
            record.farmer = farmers.get(farmer_id)


def _attach_store_items(transactions):
    if not transactions:
        return
    transaction_ids = [tx.id for tx in transactions]
    item_rows = _table("store_transaction_items").select("*").in_("transaction_id", transaction_ids).order("created_at").execute().data or []
    grouped = defaultdict(list)
    for row in item_rows:
        item = StoreTransactionItem.from_dict(row)
        grouped[item.transaction_id].append(item)
    for tx in transactions:
        tx.items = grouped.get(tx.id, [])


def _validate_entry_payload(payload):
    session_name = (payload.get("session") or "").strip().lower()
    if session_name not in {"morning", "evening"}:
        raise ValueError("Session must be morning or evening.")

    quantity = money(payload.get("quantity") or 0)
    rate = money(payload.get("rate") or 0)
    amount = money(payload.get("amount") or 0)
    if quantity < Decimal("0.00"):
        raise ValueError("Milk quantity cannot be negative.")
    if rate < Decimal("0.00"):
        raise ValueError("Milk rate cannot be negative.")
    if amount < Decimal("0.00"):
        raise ValueError("Milk amount cannot be negative.")
