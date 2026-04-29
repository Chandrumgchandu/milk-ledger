from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.forms import EntryForm
from app.services.supabase_service import create_entry, get_current_rate, get_entry, get_entry_by_unique_key, list_entries, list_farmers, update_entry
from app.utils.helpers import money, parse_date, validate_master_key


entries_bp = Blueprint("entries", __name__)


def _farmer_choices():
    return [(farmer.id, f"{farmer.unique_code} - {farmer.name}") for farmer in list_farmers(active_only=True)]


@entries_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = EntryForm()
    form.farmer_id.choices = _farmer_choices()
    current_rate = get_current_rate()
    if request.method == "GET" and current_rate:
        form.rate.data = f"{current_rate.rate:.2f}"
    if form.validate_on_submit():
        duplicate = get_entry_by_unique_key(form.farmer_id.data, form.date.data, form.session.data)
        if duplicate:
            flash("Entry already exists for this farmer, date, and session.", "danger")
        else:
            quantity = money(Decimal(form.quantity.data))
            rate = money(Decimal(form.rate.data))
            try:
                create_entry(
                    {
                        "farmer_id": form.farmer_id.data,
                        "date": form.date.data.isoformat(),
                        "session": form.session.data,
                        "quantity": str(quantity),
                        "rate": str(rate),
                        "amount": str(money(quantity * rate)),
                    }
                )
                flash("Milk entry saved.", "success")
                return redirect(url_for("entries.index"))
            except Exception:
                flash("Unable to save milk entry right now. Please try again.", "danger")

    selected_date = request.args.get("date")
    selected_session = request.args.get("session") or ""
    selected_farmer = request.args.get("farmer_id") or ""
    try:
        selected_farmer_id = int(selected_farmer) if selected_farmer else None
    except ValueError:
        selected_farmer_id = None
        selected_farmer = ""
        flash("Invalid farmer filter was ignored.", "warning")
    entries = list_entries(entry_date=parse_date(selected_date) if selected_date else None, session=selected_session or None, farmer_id=selected_farmer_id)
    return render_template("entries.html", form=form, entries=entries, farmers=list_farmers(active_only=True), selected_date=selected_date, selected_session=selected_session, selected_farmer=selected_farmer)


@entries_bp.route("/<int:entry_id>/edit", methods=["GET", "POST"])
@login_required
def edit(entry_id):
    entry = get_entry(entry_id)
    if not entry:
        flash("Entry not found.", "danger")
        return redirect(url_for("entries.index"))
    form = EntryForm(farmer_id=entry.farmer_id, date=entry.date, session=entry.session, quantity=str(entry.quantity), rate=str(entry.rate))
    form.farmer_id.choices = _farmer_choices()
    if form.validate_on_submit():
        quantity = money(Decimal(form.quantity.data))
        rate = money(Decimal(form.rate.data))
        is_valid_key, error_message = validate_master_key(request.form.get("master_key"))
        if not is_valid_key:
            flash(error_message, "danger")
        else:
            try:
                update_entry(
                    entry_id,
                    {
                        "farmer_id": form.farmer_id.data,
                        "date": form.date.data.isoformat(),
                        "session": form.session.data,
                        "quantity": str(quantity),
                        "rate": str(rate),
                        "amount": str(money(quantity * rate)),
                    },
                )
                flash("Entry updated successfully.", "success")
                return redirect(url_for("entries.index"))
            except Exception:
                flash("Unable to update entry right now. Please try again.", "danger")
    return render_template("entry_edit.html", form=form, entry=entry)
