import calendar
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.services.session_service import current_collection_session, get_session_settings, now_ist, update_session_settings
from app.services.supabase_service import (
    create_rate,
    dashboard_metrics,
    get_current_rate,
    list_entries,
    list_farmers,
    monthly_farmer_summary,
    pending_for_session,
)
from app.utils.helpers import money


dashboard_bp = Blueprint("dashboard", __name__)


@dashboard_bp.route("/dashboard", methods=["GET", "POST"])
@login_required
def index():
    now = now_ist()
    session_name = current_collection_session(now)
    selected_month = _safe_month(request.values.get("month"), now.month)
    selected_year = _safe_year(request.values.get("year"), now.year)
    selected_farmer = request.values.get("farmer", "").strip()
    row_limit = request.values.get("row_limit", "20").strip()
    allowed_limits = [10, 20, 30, 50, 100]
    try:
        selected_row_limit = int(row_limit)
    except ValueError:
        selected_row_limit = 20
    if selected_row_limit not in allowed_limits:
        selected_row_limit = 20

    if request.method == "POST":
        try:
            if request.form.get("settings_action") == "update_sessions":
                update_session_settings(
                    request.form.get("morning_start", "06:00"),
                    request.form.get("morning_end", "09:00"),
                    request.form.get("evening_start", "18:00"),
                    request.form.get("evening_end", "21:00"),
                )
            elif request.form.get("settings_action") == "update_rate":
                rate_value = request.form.get("rate", "").strip()
                if rate_value:
                    parsed_rate = money(Decimal(rate_value))
                    if parsed_rate <= 0:
                        raise ValueError("Rate must be greater than zero.")
                    create_rate(parsed_rate, created_by="dashboard_owner")
        except (InvalidOperation, ValueError):
            if request.form.get("settings_action") == "update_rate":
                flash("Enter a valid positive milk rate.", "danger")
            else:
                flash("Enter valid payment details and try again.", "danger")
        except Exception:
            flash("Unable to complete the request. Please try again.", "danger")
        return redirect(
            url_for(
                "dashboard.index",
                month=request.form.get("month"),
                year=request.form.get("year"),
                farmer=request.form.get("farmer", ""),
                row_limit=request.form.get("row_limit", "20"),
            )
        )

    entries = [entry for entry in list_entries() if entry.date.year == selected_year and entry.date.month == selected_month]
    if selected_farmer:
        entries = [
            entry
            for entry in entries
            if selected_farmer.lower() in (entry.farmer.name.lower() if entry.farmer else "")
            or selected_farmer == str(entry.farmer.unique_code if entry.farmer else "")
        ]

    daily_rows = _build_daily_rows(entries)[:selected_row_limit]
    monthly_summary = monthly_farmer_summary(selected_year, selected_month)
    if selected_farmer:
        monthly_summary = [
            row
            for row in monthly_summary
            if selected_farmer.lower() in row["farmer_name"].lower() or selected_farmer == str(row["farmer_id"])
        ]

    filtered_month_total = money(sum((entry.amount for entry in entries), start=0))
    day_count = calendar.monthrange(selected_year, selected_month)[1]
    calendar_days = [f"{selected_year}-{selected_month:02d}-{day:02d}" for day in range(1, day_count + 1)]

    return render_template(
        "dashboard.html",
        now=now,
        session_name=session_name,
        current_rate=get_current_rate(),
        metrics=dashboard_metrics(now.date(), session_name=session_name),
        selected_month=selected_month,
        selected_year=selected_year,
        selected_farmer=selected_farmer,
        selected_row_limit=selected_row_limit,
        row_limit_options=allowed_limits,
        daily_rows=daily_rows,
        monthly_summary=monthly_summary,
        filtered_month_total=filtered_month_total,
        calendar_days=calendar_days,
        farmers=list_farmers(active_only=True),
        session_settings=get_session_settings(),
    )


def _safe_month(value, default):
    try:
        month = int(value)
    except (TypeError, ValueError):
        return default
    return month if 1 <= month <= 12 else default


def _safe_year(value, default):
    try:
        year = int(value)
    except (TypeError, ValueError):
        return default
    current_year = datetime.now().year
    return year if 2000 <= year <= current_year + 5 else default


@dashboard_bp.route("/dashboard/pending", methods=["GET"])
@login_required
def pending():
    now = now_ist()
    selected_session = (request.args.get("session") or current_collection_session(now) or "morning").strip().lower()
    if selected_session not in {"morning", "evening"}:
        selected_session = "morning"

    pending_farmers = pending_for_session(now.date(), selected_session)
    return render_template(
        "pending_farmers.html",
        now=now,
        selected_session=selected_session,
        pending_farmers=pending_farmers,
    )


def _build_daily_rows(entries):
    grouped = defaultdict(
        lambda: {
            "date": None,
            "farmer_name": "",
            "farmer_code": "",
            "morning_quantity": None,
            "morning_entry_id": None,
            "morning_rate": None,
            "evening_quantity": None,
            "evening_entry_id": None,
            "evening_rate": None,
            "daily_total": 0,
        }
    )
    for entry in entries:
        key = (entry.date.isoformat(), entry.farmer_id)
        row = grouped[key]
        row["date"] = entry.date.isoformat()
        row["farmer_name"] = entry.farmer.name if entry.farmer else str(entry.farmer_id)
        row["farmer_code"] = entry.farmer.unique_code if entry.farmer else "-"
        row[f"{entry.session}_quantity"] = entry.quantity
        row[f"{entry.session}_entry_id"] = entry.id
        row[f"{entry.session}_rate"] = entry.rate
        row["daily_total"] += float(entry.quantity)
    return sorted(grouped.values(), key=lambda item: (item["date"], item["farmer_code"]), reverse=True)
