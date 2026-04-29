from flask import Blueprint, jsonify, make_response

from app.services.health_service import live_health_check


health_bp = Blueprint("health", __name__)

@health_bp.route("/live")
def live():
    return {"ok": True}, 200

@health_bp.route("/health", methods=["GET"])
def health_ok():
    response = make_response("OK", 200)
    response.headers["Content-Type"] = "text/plain; charset=utf-8"
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


@health_bp.route("/health/live", methods=["GET"])
def health_live():
    payload = live_health_check()
    status_code = 200 if payload["ok"] else 503
    response = make_response(jsonify(payload), status_code)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response
