from collections import defaultdict
from time import monotonic
from urllib.parse import urlsplit

from flask import Blueprint, current_app, flash, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from app.forms import ForgotPasswordForm, LoginForm
from app.services.supabase_service import get_admin_by_phone, update_admin_password_by_phone
from app.utils.helpers import normalize_phone, validate_master_key


auth_bp = Blueprint("auth", __name__)
_LOGIN_ATTEMPTS = defaultdict(list)
_LOGIN_WINDOW_SECONDS = 15 * 60
_LOGIN_MAX_ATTEMPTS = 5
_LOGIN_LOCK_SECONDS = 15 * 60


def _client_ip():
    forwarded_for = request.headers.get("X-Forwarded-For", "")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.remote_addr or "unknown"


def _is_safe_redirect_target(target):
    if not target:
        return False
    ref_url = urlsplit(request.host_url)
    test_url = urlsplit(target)
    return test_url.scheme in ("", "http", "https") and ref_url.netloc == (test_url.netloc or ref_url.netloc)


def _trim_login_attempts(ip_address):
    now = monotonic()
    attempts = [stamp for stamp in _LOGIN_ATTEMPTS[ip_address] if now - stamp < _LOGIN_WINDOW_SECONDS]
    _LOGIN_ATTEMPTS[ip_address] = attempts
    return attempts


def _login_is_rate_limited(ip_address):
    attempts = _trim_login_attempts(ip_address)
    if len(attempts) < _LOGIN_MAX_ATTEMPTS:
        return False
    return monotonic() - attempts[-1] < _LOGIN_LOCK_SECONDS


def _record_login_failure(ip_address):
    attempts = _trim_login_attempts(ip_address)
    attempts.append(monotonic())
    _LOGIN_ATTEMPTS[ip_address] = attempts


def _clear_login_failures(ip_address):
    _LOGIN_ATTEMPTS.pop(ip_address, None)


@auth_bp.route("/")
def root():
    if current_user.is_authenticated:
        logout_user()
    session.clear()
    return redirect(url_for("auth.login"))


@auth_bp.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = LoginForm()
    if form.validate_on_submit():
        ip_address = _client_ip()
        if _login_is_rate_limited(ip_address):
            flash("Too many failed login attempts. Please wait 15 minutes and try again.", "danger")
            return render_template("login.html", form=form), 429

        phone = normalize_phone(form.phone.data)
        password = form.password.data
        try:
            admin = get_admin_by_phone(phone)
        except Exception:
            flash("Supabase connection failed. Check SUPABASE_URL, SUPABASE_KEY, or local network access.", "danger")
            return render_template("login.html", form=form), 503

        if admin and admin.check_password(password):
            session.clear()
            login_user(admin)
            session.permanent = False
            _clear_login_failures(ip_address)
            flash("Login successful.", "success")
            next_target = request.args.get("next", "")
            return redirect(next_target if _is_safe_redirect_target(next_target) else url_for("dashboard.index"))

        _record_login_failure(ip_address)
        flash("Invalid owner phone or password.", "danger")

    return render_template("login.html", form=form)


@auth_bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard.index"))

    form = ForgotPasswordForm()
    if form.validate_on_submit():
        phone = normalize_phone(form.phone.data)
        is_valid_key, error_message = validate_master_key(form.recovery_key.data)

        if not current_app.config["PASSWORD_RESET_KEY"]:
            flash("Password reset is not configured. Add PASSWORD_RESET_KEY in .env.", "danger")
        else:
            try:
                admin = get_admin_by_phone(phone)
                if admin and is_valid_key:
                    update_admin_password_by_phone(phone, form.new_password.data)
                    flash("Password reset successful. Please login with the new password.", "success")
                    return redirect(url_for("auth.login"))
                flash("Unable to reset password with the provided details.", "danger")
            except Exception:
                flash("Password reset is temporarily unavailable. Please try again.", "danger")

    return render_template("forgot_password.html", form=form)


@auth_bp.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    session.clear()
    flash("Logged out successfully.", "info")
    response = redirect(url_for("auth.login"))
    response.headers["Clear-Site-Data"] = "\"cache\", \"cookies\", \"storage\""
    return response
