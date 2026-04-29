from datetime import date

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.forms import StoreTransactionForm
from app.services.session_service import today_ist
from app.services.supabase_service import create_store_transaction, list_farmers, list_store_transactions


store_bp = Blueprint("store", __name__)


def _farmer_choices():
    return [(farmer.id, f"{farmer.unique_code} - {farmer.name} ({farmer.phone})") for farmer in list_farmers(active_only=True)]


@store_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    today = today_ist()
    form = StoreTransactionForm()
    form.farmer_id.choices = _farmer_choices()
    if request.method == "GET":
        form.bill_date.data = today

    if form.validate_on_submit():
        items = []
        for item_name, quantity, unit, unit_price in zip(
            request.form.getlist("item_name[]"),
            request.form.getlist("quantity[]"),
            request.form.getlist("unit[]"),
            request.form.getlist("unit_price[]"),
        ):
            if not (item_name or "").strip():
                continue
            items.append(
                {
                    "item_name": item_name,
                    "quantity": quantity,
                    "unit": unit,
                    "unit_price": unit_price,
                }
            )
        try:
            create_store_transaction(form.farmer_id.data, form.bill_date.data, items, note=form.note.data.strip() if form.note.data else None)
            flash("Provision store bill saved successfully.", "success")
            return redirect(url_for("store.index"))
        except Exception as exc:
            flash(str(exc), "danger")

    selected_month = int(request.args.get("month", today.month))
    selected_year = int(request.args.get("year", today.year))
    search = request.args.get("q", "").strip()
    transactions = list_store_transactions(year=selected_year, month=selected_month, search=search)
    return render_template(
        "store.html",
        form=form,
        transactions=transactions,
        selected_month=selected_month,
        selected_year=selected_year,
        search=search,
        today=today,
    )
