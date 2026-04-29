from decimal import Decimal

from flask import Blueprint, flash, redirect, render_template, url_for
from flask_login import login_required

from app.forms import PaymentForm, RateForm
from app.services.session_service import today_ist
from app.services.supabase_service import create_payment, create_rate, list_farmers, list_payments, list_rates
from app.utils.helpers import money


payments_bp = Blueprint("payments", __name__)


def _farmer_choices():
    return [(farmer.id, f"{farmer.unique_code} - {farmer.name}") for farmer in list_farmers(active_only=True)]


@payments_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = PaymentForm()
    form.farmer_id.choices = _farmer_choices()
    rate_form = RateForm(prefix="rate")
    if form.submit.data and form.validate_on_submit():
        create_payment(
            {
                "farmer_id": form.farmer_id.data,
                "amount_paid": str(money(Decimal(form.amount_paid.data))),
                "payment_date": form.payment_date.data.isoformat(),
                "note": form.note.data.strip() if form.note.data else None,
            }
        )
        flash("Payment saved successfully.", "success")
        return redirect(url_for("payments.index"))
    if rate_form.submit.data and rate_form.validate_on_submit():
        create_rate(rate_form.rate.data, created_by="dashboard_owner")
        flash("Milk rate updated successfully.", "success")
        return redirect(url_for("payments.index"))
    return render_template("payments.html", form=form, rate_form=rate_form, payments=list_payments(), rates=list_rates()[:10], today=today_ist())
