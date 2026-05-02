from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation

from flask import Blueprint, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required

from app.services.pdf_service import build_farmer_statement_pdf
from app.services.session_service import now_ist
from app.services.supabase_service import (
    create_payment,
    create_payment_log,
    get_farmer,
    list_entries,
    list_farmers,
    list_payment_logs,
    list_store_transactions,
    settlement_running_balance,
    settlement_status,
)
from app.utils.helpers import money, validate_master_key


payments_bp = Blueprint("payments", __name__)


@payments_bp.route("/", methods=["GET"])
@login_required
def index():
    today = now_ist().date()
    search = (request.args.get("search") or "").strip()
    status_filter = (request.args.get("status") or "all").strip().lower()
    sort_by = (request.args.get("sort") or "farmer_asc").strip().lower()

    rows = _payment_rows(today, search=search, status_filter=status_filter, sort_by=sort_by)
    return render_template(
        "payments.html",
        today=today,
        rows=rows,
        search=search,
        status_filter=status_filter,
        sort_by=sort_by,
    )


@payments_bp.route("/bill/<int:farmer_id>", methods=["GET"])
@login_required
def bill_pdf(farmer_id):
    today = now_ist().date()
    summary = _farmer_payment_summary(farmer_id, today)
    if not summary:
        flash("Farmer not found.", "danger")
        return redirect(url_for("payments.index"))
    return _send_summary_pdf(summary, download_suffix="bill")


@payments_bp.route("/record", methods=["POST"])
@login_required
def record():
    farmer_id = int(request.form.get("farmer_id", "0"))
    summary = _farmer_payment_summary(farmer_id, now_ist().date())
    if not summary:
        flash("Farmer not found.", "danger")
        return redirect(url_for("payments.index"))

    is_valid_key, error_message = validate_master_key(request.form.get("master_key"))
    if not is_valid_key:
        flash(error_message, "danger")
        return redirect(url_for("payments.index"))

    try:
        amount = money(Decimal((request.form.get("amount") or "0").strip()))
    except (InvalidOperation, ValueError):
        flash("Enter a valid payment amount.", "danger")
        return redirect(url_for("payments.index"))

    if amount <= 0:
        flash("Enter a valid payment amount.", "danger")
        return redirect(url_for("payments.index"))

    if summary["final_balance"] > 0:
        direction = "to_farmer"
        action_label = "Payment"
    elif summary["final_balance"] < 0:
        direction = "from_farmer"
        action_label = "Recovery"
    else:
        flash("This bill is already settled.", "warning")
        return redirect(url_for("payments.index"))

    note = (request.form.get("note") or "").strip() or None
    payment_date = now_ist().date().isoformat()
    payment_log = create_payment_log(
        {
            "farmer_id": farmer_id,
            "settlement_id": None,
            "payment_date": payment_date,
            "amount": str(amount),
            "direction": direction,
            "note": note,
        }
    )
    if direction == "to_farmer":
        create_payment(
            {
                "farmer_id": farmer_id,
                "amount_paid": str(amount),
                "payment_date": payment_date,
                "note": note or f"Simple payment receipt ({summary['period_label']})",
            }
        )

    updated_summary = _farmer_payment_summary(farmer_id, now_ist().date())
    return _send_summary_pdf(
        updated_summary,
        receipt_payment=payment_log.amount,
        receipt_direction=payment_log.direction,
        receipt_label=action_label,
        download_suffix="receipt",
    )


def _payment_rows(today, search="", status_filter="all", sort_by="farmer_asc"):
    farmers = list_farmers(active_only=True)
    entries = list_entries()
    store_transactions = list_store_transactions()
    payment_logs = list_payment_logs()

    entries_by_farmer = defaultdict(list)
    for entry in entries:
        entries_by_farmer[entry.farmer_id].append(entry)

    store_by_farmer = defaultdict(list)
    for tx in store_transactions:
        store_by_farmer[tx.farmer_id].append(tx)

    logs_by_farmer = defaultdict(list)
    for log in payment_logs:
        logs_by_farmer[log.farmer_id].append(log)

    rows = []
    for farmer in farmers:
        row = _build_farmer_payment_summary(farmer, today, entries_by_farmer[farmer.id], store_by_farmer[farmer.id], logs_by_farmer[farmer.id])
        if not row:
            continue
        if search:
            term = search.lower()
            haystack = f"{farmer.unique_code} {farmer.name} {farmer.phone}".lower()
            if term not in haystack:
                continue
        if status_filter != "all" and row["status_key"] != status_filter:
            continue
        rows.append(row)

    sorters = {
        "farmer_asc": lambda item: (item["farmer_code"], item["farmer_name"].lower()),
        "balance_desc": lambda item: (abs(item["final_balance"]), item["farmer_code"]),
        "balance_asc": lambda item: (abs(item["final_balance"]), item["farmer_code"]),
        "milk_desc": lambda item: (item["milk_total_liters"], item["farmer_code"]),
        "paid_desc": lambda item: (item["paid_total"], item["farmer_code"]),
    }
    rows.sort(key=sorters.get(sort_by, sorters["farmer_asc"]), reverse=sort_by in {"balance_desc", "milk_desc", "paid_desc"})
    return rows


def _farmer_payment_summary(farmer_id, today):
    farmer = get_farmer(farmer_id)
    if not farmer:
        return None
    return _build_farmer_payment_summary(
        farmer,
        today,
        list_entries(farmer_id=farmer_id),
        list_store_transactions(farmer_id=farmer_id),
        list_payment_logs(farmer_id=farmer_id),
    )


def _build_farmer_payment_summary(farmer, today, farmer_entries, farmer_store_transactions, farmer_payment_logs):
    period_start = _resolve_period_start(farmer_payment_logs, today)
    period_end = today

    bill_entries = [entry for entry in farmer_entries if period_start <= entry.date <= period_end]
    bill_store = [tx for tx in farmer_store_transactions if period_start <= tx.bill_date <= period_end]
    bill_logs = [log for log in farmer_payment_logs if period_start <= log.payment_date <= period_end]

    milk_total_liters = money(sum((entry.quantity for entry in bill_entries), Decimal("0.00")))
    milk_total_amount = money(sum((entry.amount for entry in bill_entries), Decimal("0.00")))
    store_credit_total = money(sum((tx.total_amount for tx in bill_store), Decimal("0.00")))
    paid_total = money(sum((log.amount for log in bill_logs if log.direction == "to_farmer"), Decimal("0.00")))
    recovered_total = money(sum((log.amount for log in bill_logs if log.direction == "from_farmer"), Decimal("0.00")))
    net_amount = money(milk_total_amount - store_credit_total)
    final_balance = settlement_running_balance(net_amount, paid_total, recovered_total)

    if milk_total_liters == Decimal("0.00") and store_credit_total == Decimal("0.00") and paid_total == Decimal("0.00") and recovered_total == Decimal("0.00"):
        return None

    status_text = settlement_status(final_balance)
    if final_balance > 0:
        status_key = "pay_farmer"
    elif final_balance < 0:
        status_key = "farmer_owes"
    else:
        status_key = "settled"

    return {
        "farmer_id": farmer.id,
        "farmer_code": farmer.unique_code,
        "farmer_name": farmer.name,
        "farmer_phone": farmer.phone,
        "period_start": period_start,
        "period_end": period_end,
        "period_label": f"{period_start.isoformat()} to {period_end.isoformat()}",
        "milk_entries": bill_entries,
        "store_transactions": bill_store,
        "payment_logs": bill_logs,
        "milk_total_liters": milk_total_liters,
        "milk_total_amount": milk_total_amount,
        "store_credit_total": store_credit_total,
        "paid_total": paid_total,
        "recovered_total": recovered_total,
        "net_amount": net_amount,
        "final_balance": final_balance,
        "status": status_text,
        "status_key": status_key,
    }


def _resolve_period_start(payment_logs, today, window_days=30):
    default_start = today - timedelta(days=max(window_days - 1, 0))
    if not payment_logs:
        return default_start

    latest_log = max(payment_logs, key=lambda log: (log.payment_date, log.created_at or datetime.min))
    if latest_log.payment_date >= today:
        return default_start
    return latest_log.payment_date + timedelta(days=1)


def _send_summary_pdf(summary, receipt_payment=None, receipt_direction=None, receipt_label=None, download_suffix="bill"):
    farmer = get_farmer(summary["farmer_id"])
    totals = {
        "quantity": summary["milk_total_liters"],
        "amount": summary["milk_total_amount"],
        "store_total": summary["store_credit_total"],
        "net_amount": summary["net_amount"],
        "paid_to_farmer": summary["paid_total"],
        "recovered_from_farmer": summary["recovered_total"],
        "final_balance": summary["final_balance"],
        "final_status": summary["status"],
    }
    label = f"Bill Period: {summary['period_label']}"
    if receipt_payment is not None and receipt_direction:
        label = f"{label} | {receipt_label}: Rs. {receipt_payment:.2f}"

    pdf_buffer = build_farmer_statement_pdf(
        current_app.config["BUSINESS_NAME"],
        farmer,
        label,
        summary["milk_entries"],
        summary["store_transactions"],
        summary["payment_logs"],
        totals,
    )
    return send_file(
        pdf_buffer,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=f"{farmer.name}_{summary['period_end'].isoformat()}_{download_suffix}.pdf",
    )
