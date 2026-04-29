import calendar
import csv
from datetime import date
from io import StringIO

from flask import Blueprint, Response, current_app, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from itsdangerous import URLSafeSerializer

from app.forms import PaymentLogForm
from app.services.pdf_service import build_farmer_statement_pdf, build_monthly_settlement_summary_pdf
from app.services.session_service import today_ist
from app.services.supabase_service import (
    create_or_update_monthly_settlement,
    create_payment_log,
    farmer_ledger,
    get_farmer,
    list_entries,
    list_farmers,
    list_payment_logs,
    monthly_farmer_summary,
    settlement_summary,
    unlock_monthly_settlement,
    yearly_totals,
)
from app.utils.helpers import money


reports_bp = Blueprint("reports", __name__)


def _serializer():
    return URLSafeSerializer(current_app.config["SECRET_KEY"], salt="farmer-pdf")


def _farmer_choices():
    return [(farmer.id, f"{farmer.unique_code} - {farmer.name}") for farmer in list_farmers(active_only=True)]


@reports_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    today = today_ist()
    month = int(request.values.get("month", today.month))
    year = int(request.values.get("year", today.year))
    payment_log_form = PaymentLogForm(prefix="payment_log")
    payment_log_form.farmer_id.choices = _farmer_choices()
    if request.method == "GET":
        payment_log_form.payment_date.data = today

    if request.method == "POST":
        action = request.form.get("action")
        if action == "lock_settlement":
            farmer_id = int(request.form.get("farmer_id"))
            create_or_update_monthly_settlement(farmer_id, year, month, note=request.form.get("note") or None)
            flash("Monthly settlement locked successfully.", "success")
            return redirect(url_for("reports.index", month=month, year=year))
        if action == "unlock_settlement":
            farmer_id = int(request.form.get("farmer_id"))
            unlock_monthly_settlement(farmer_id, year, month)
            flash("Monthly settlement unlocked for editing.", "warning")
            return redirect(url_for("reports.index", month=month, year=year))
        if action == "add_payment_log" and payment_log_form.validate():
            create_payment_log(
                {
                    "farmer_id": payment_log_form.farmer_id.data,
                    "payment_date": payment_log_form.payment_date.data.isoformat(),
                    "amount": str(money(payment_log_form.amount.data)),
                    "direction": payment_log_form.direction.data,
                    "note": payment_log_form.note.data.strip() if payment_log_form.note.data else None,
                }
            )
            flash("Settlement payment log saved.", "success")
            return redirect(url_for("reports.index", month=month, year=year))

    settlement_rows = settlement_summary(year, month)
    monthly_summary = monthly_farmer_summary(year, month)
    return render_template(
        "reports.html",
        farmers=list_farmers(),
        monthly_summary=monthly_summary,
        yearly_summary=yearly_totals(),
        settlement_rows=settlement_rows,
        selected_month=month,
        selected_year=year,
        payment_logs=list_payment_logs()[:20],
        payment_log_form=payment_log_form,
    )


@reports_bp.route("/farmer-pdf/<int:farmer_id>")
@login_required
def farmer_pdf(farmer_id):
    return _send_farmer_pdf(farmer_id, int(request.args.get("year")), int(request.args.get("month")))


@reports_bp.route("/farmer-pdf-share")
def farmer_pdf_share():
    token = request.args.get("token", "")
    try:
        data = _serializer().loads(token)
    except Exception:
        flash("Invalid PDF link.", "danger")
        return redirect(url_for("auth.login"))
    return _send_farmer_pdf(int(data["farmer_id"]), int(data["year"]), int(data["month"]))


def _send_farmer_pdf(farmer_id, year, month):
    farmer = get_farmer(farmer_id)
    if not farmer:
        flash("Farmer not found.", "danger")
        return redirect(url_for("reports.index"))
    ledger = farmer_ledger(farmer_id, year, month)
    pdf_buffer = build_farmer_statement_pdf(
        current_app.config["BUSINESS_NAME"],
        farmer,
        f"{calendar.month_name[month]} {year}",
        ledger["milk_entries"],
        ledger["store_transactions"],
        ledger["payment_logs"],
        {
            "quantity": ledger["milk_total_quantity"],
            "amount": ledger["milk_total_amount"],
            "store_total": ledger["store_total"],
            "net_amount": ledger["net_amount"],
            "paid_to_farmer": ledger["paid_to_farmer"],
            "recovered_from_farmer": ledger["recovered_from_farmer"],
            "final_balance": ledger["final_balance"],
            "final_status": ledger["final_status"],
        },
    )
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=f"{farmer.name}_{year}_{month:02d}.pdf")


@reports_bp.route("/summary-pdf")
@login_required
def summary_pdf():
    month = int(request.args.get("month"))
    year = int(request.args.get("year"))
    pdf_buffer = build_monthly_settlement_summary_pdf(current_app.config["BUSINESS_NAME"], month, year, settlement_summary(year, month))
    return send_file(pdf_buffer, mimetype="application/pdf", as_attachment=True, download_name=f"settlement_summary_{year}_{month:02d}.pdf")


def build_farmer_pdf_link(farmer_id, year, month):
    token = _serializer().dumps({"farmer_id": farmer_id, "year": year, "month": month})
    return f"{current_app.config['APP_BASE_URL'].rstrip('/')}/reports/farmer-pdf-share?token={token}"


@reports_bp.route("/csv")
@login_required
def export_csv():
    month = int(request.args.get("month", today_ist().month))
    year = int(request.args.get("year", today_ist().year))
    output = StringIO()
    writer = csv.writer(output)
    writer.writerow(["Farmer ID", "Farmer Name", "Milk Total", "Shop Credit Total", "Net Amount", "Status"])
    for row in settlement_summary(year, month):
        writer.writerow(
            [
                row["farmer_code"],
                row["farmer_name"],
                f"{row['milk_total']:.2f}",
                f"{row['shop_credit_total']:.2f}",
                f"{row['net_amount']:.2f}",
                row["status"],
            ]
        )
    return Response(output.getvalue(), mimetype="text/csv", headers={"Content-Disposition": f"attachment; filename=settlement_{year}_{month:02d}.csv"})
