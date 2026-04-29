import logging

from flask import Flask, abort, render_template, request, session
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.exceptions import SecurityError

from config import Config
from .extensions import csrf, login_manager


def create_app(config_class=Config):
    app = Flask(__name__)
    app.config.from_object(config_class)

    configure_logging(app)
    validate_runtime_config(app)
    configure_proxy(app)
    register_extensions(app)
    register_blueprints(app)
    register_error_handlers(app)

    return app


def configure_logging(app):
    logging.basicConfig(
        level=getattr(logging, app.config["LOG_LEVEL"].upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )


def validate_runtime_config(app):
    environment = app.config.get("APP_ENV", "development").lower()
    secret_key = (app.config.get("SECRET_KEY") or "").strip()
    supabase_url = (app.config.get("SUPABASE_URL") or "").strip()
    supabase_key = (app.config.get("SUPABASE_KEY") or "").strip()
    trusted_hosts = list(app.config.get("TRUSTED_HOSTS") or [])

    if environment == "production":
        if not secret_key or secret_key == "change-me":
            raise RuntimeError("SECRET_KEY must be set to a strong value in production.")
        if not supabase_url or not supabase_key:
            raise RuntimeError("SUPABASE_URL and SUPABASE_KEY must be configured in production.")
    else:
        for local_host in ("127.0.0.1", "localhost", "0.0.0.0"):
            if local_host not in trusted_hosts:
                trusted_hosts.append(local_host)
        if not secret_key or secret_key == "change-me":
            app.logger.warning("SECRET_KEY is using a default development value. Set a strong SECRET_KEY before production.")
        if not supabase_url or not supabase_key:
            app.logger.warning("SUPABASE_URL or SUPABASE_KEY is not configured.")
    app.config["TRUSTED_HOSTS"] = trusted_hosts or None


def configure_proxy(app):
    if app.config.get("TRUST_PROXY"):
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)


def register_extensions(app):
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message_category = "warning"
    login_manager.session_protection = "strong"

    from .services.supabase_service import get_admin_by_id

    @login_manager.user_loader
    def load_user(user_id):
        return get_admin_by_id(user_id)

    from .services.session_service import auto_finalize_day_entries

    @app.before_request
    def finalize_pending_day_entries():
        # Skip heavy logic for fast endpoints
        if request.path.startswith("/health"):
            return
        if request.path.startswith("/webhooks"):
            return
    # ✅ Allow WhatsApp webhook (Meta servers)
        if request.blueprint == "whatsapp":
            return

    trusted_hosts = app.config.get("TRUSTED_HOSTS") or []
    if trusted_hosts:
        host = (request.host.split(":")[0] if request.host else "").lower()
        if host not in trusted_hosts:
            abort(400)

    session.permanent = False
    auto_finalize_day_entries()

    @app.after_request
    def add_security_headers(response):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "img-src 'self' data:; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "font-src 'self' https://cdn.jsdelivr.net data:; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'"
        )
        if app.config.get("SESSION_COOKIE_SECURE"):
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        return response


def register_blueprints(app):
    from .routes.account import account_bp
    from .routes.auth import auth_bp
    from .routes.dashboard import dashboard_bp
    from .routes.farmers import farmers_bp
    from .routes.health import health_bp
    from .routes.entries import entries_bp
    from .routes.whatsapp import whatsapp_bp

    app.register_blueprint(account_bp, url_prefix="/account")
    app.register_blueprint(auth_bp)
    app.register_blueprint(dashboard_bp)
    app.register_blueprint(health_bp)
    app.register_blueprint(farmers_bp, url_prefix="/farmers")
    app.register_blueprint(entries_bp, url_prefix="/entries")
    app.register_blueprint(whatsapp_bp, url_prefix="/webhooks/whatsapp")
    csrf.exempt(whatsapp_bp)


def register_error_handlers(app):
    def _safe_error_response(status_code, title, message):
        try:
            return render_template("error.html", status_code=status_code, title=title, message=message), status_code
        except Exception:
            return f"{status_code} {title}: {message}", status_code

    @app.errorhandler(SecurityError)
    def security_error(error):
        return "400 Bad Request: Untrusted host.", 400

    @app.errorhandler(400)
    def bad_request(error):
        if request.blueprint == "whatsapp":
            return "Bad request", 400
        return _safe_error_response(400, "Bad Request", "The request could not be processed.")

    @app.errorhandler(404)
    def not_found(error):
        if request.blueprint == "whatsapp":
            return "Not found", 404
        return _safe_error_response(404, "Page Not Found", "The page you requested does not exist.")

    @app.errorhandler(500)
    def server_error(error):
        if request.blueprint == "whatsapp":
            return "Internal server error", 500
        return _safe_error_response(500, "Something Went Wrong", "Please try again. If the issue continues, refresh and retry the action.")
