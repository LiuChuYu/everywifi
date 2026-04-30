from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from ..models import Purchase, User
from ..routes.usage import _find_active_purchase

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("", methods=["POST"])
def check_auth():
    """OpenWrt (nodogsplash/coovachilli) 呼叫此端點驗證使用者是否可上網。
    Body: { "token": "...", "mac_address": "aa:bb:cc:dd:ee:ff" }
    Returns: { "allowed": true/false, "reason": "..." }
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    mac_address = data.get("mac_address")

    if not token:
        raise BadRequest("token is required")

    user = User.query.filter_by(token=token).first()
    if not user:
        return jsonify({"allowed": False, "reason": "invalid token"}), 200

    purchase = _find_active_purchase(user.id)
    if not purchase:
        return jsonify({"allowed": False, "reason": "no active purchase"}), 200

    return jsonify(
        {
            "allowed": True,
            "reason": "ok",
            "user_id": user.id,
            "username": user.username,
            "purchase_id": purchase.id,
            "mb_remaining": round(purchase.mb_remaining, 3) if purchase.mb_remaining is not None else None,
        }
    )
