from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import login_required

from app.forms import FarmerForm
from app.services.supabase_service import create_farmer, find_farmer_conflicts, get_client, get_farmer, list_farmers, update_farmer
from app.utils.helpers import normalize_phone, validate_master_key


farmers_bp = Blueprint("farmers", __name__)


@farmers_bp.route("/", methods=["GET", "POST"])
@login_required
def index():
    form = FarmerForm()
    search = request.args.get("q", "").strip()
    farmers = list_farmers(search=search)
    all_farmers = list_farmers()
    if form.validate_on_submit():
        payload = {
            "unique_code": int(form.unique_code.data),
            "name": form.name.data.strip(),
            "phone": normalize_phone(form.phone.data),
            "village": form.village.data.strip() if form.village.data else None,
            "is_active": bool(form.is_active.data),
        }
        conflicts = find_farmer_conflicts(payload["unique_code"], payload["name"], payload["phone"])
        if conflicts:
            if "unique_code" in conflicts:
                form.unique_code.errors = [f"Farmer ID {payload['unique_code']} already exists."]
            if "name" in conflicts:
                form.name.errors = [f"Farmer name '{payload['name']}' already exists."]
            if "phone" in conflicts:
                form.phone.errors = [f"Phone number {payload['phone']} already exists."]
            flash("Please fix the duplicate farmer details shown below.", "danger")
        else:
            is_valid_key, error_message = validate_master_key(request.form.get("master_key"))
            if not is_valid_key:
                flash(error_message, "danger")
            else:
                try:
                    create_farmer(payload)
                    flash("Farmer saved successfully.", "success")
                    return redirect(url_for("farmers.index"))
                except Exception:
                    flash("Unable to save farmer right now. Please check the details and try again.", "danger")
    return render_template("farmers.html", form=form, farmers=farmers, all_farmers=all_farmers, search=search)


@farmers_bp.route("/<int:farmer_id>/edit", methods=["GET", "POST"])
@login_required
def edit(farmer_id):
    farmer = get_farmer(farmer_id)
    if not farmer:
        flash("Farmer not found.", "danger")
        return redirect(url_for("farmers.index"))
    form = FarmerForm(obj=farmer)
    if form.validate_on_submit():
        payload = {
            "unique_code": int(form.unique_code.data),
            "name": form.name.data.strip(),
            "phone": normalize_phone(form.phone.data),
            "village": form.village.data.strip() if form.village.data else None,
            "is_active": bool(form.is_active.data),
        }
        conflicts = find_farmer_conflicts(payload["unique_code"], payload["name"], payload["phone"], exclude_farmer_id=farmer_id)
        if conflicts:
            if "unique_code" in conflicts:
                form.unique_code.errors = [f"Farmer ID {payload['unique_code']} already exists."]
            if "name" in conflicts:
                form.name.errors = [f"Farmer name '{payload['name']}' already exists."]
            if "phone" in conflicts:
                form.phone.errors = [f"Phone number {payload['phone']} already exists."]
            flash("Please fix the duplicate farmer details shown below.", "danger")
        else:
            is_valid_key, error_message = validate_master_key(request.form.get("master_key"))
            if not is_valid_key:
                flash(error_message, "danger")
            else:
                try:
                    update_farmer(farmer_id, payload)
                    flash("Farmer updated successfully.", "success")
                    return redirect(url_for("farmers.index"))
                except Exception:
                    flash("Unable to update farmer right now. Please check the details and try again.", "danger")
    return render_template("farmer_edit.html", form=form, farmer=farmer, all_farmers=list_farmers())


@farmers_bp.route("/<int:farmer_id>/delete", methods=["POST"])
@login_required
def delete(farmer_id):
    farmer = get_farmer(farmer_id)
    if not farmer:
        flash("Farmer not found.", "danger")
        return redirect(url_for("farmers.index"))
    is_valid_key, error_message = validate_master_key(request.form.get("master_key"))
    if not is_valid_key:
        flash(error_message, "danger")
        return redirect(url_for("farmers.index"))
    try:
        get_client().table("farmers").delete().eq("id", farmer_id).execute()
        flash(f"{farmer.name} deleted successfully.", "warning")
    except Exception:
        flash("Unable to delete farmer right now. Please try again.", "danger")
    return redirect(url_for("farmers.index"))
