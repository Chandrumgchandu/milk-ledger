from flask import Blueprint, flash, redirect, render_template, session, url_for
from flask_login import current_user, login_required, logout_user

from app.forms import ChangePasswordForm
from app.services.supabase_service import update_admin_password


account_bp = Blueprint("account", __name__)


@account_bp.route("/password", methods=["GET", "POST"])
@login_required
def password():
    form = ChangePasswordForm()
    if form.validate_on_submit():
        if not current_user.check_password(form.current_password.data):
            flash("Current password is incorrect.", "danger")
        else:
            update_admin_password(current_user.id, form.new_password.data)
            logout_user()
            session.clear()
            flash("Password updated successfully. Please login again.", "success")
            return redirect(url_for("auth.login"))
    return render_template("account_password.html", form=form)
