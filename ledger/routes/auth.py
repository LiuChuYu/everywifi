from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest

from ..models import Account, User

bp = Blueprint("auth", __name__, url_prefix="/auth")


@bp.route("", methods=["POST"])
def check_auth():
    """OpenWrt (nodogsplash/coovachilli) 呼叫此端點驗證使用者是否可上網。
    Body: { "token": "...", "mac_address": "aa:bb:cc:dd:ee:ff" }
    Returns: { "allowed": true/false, "reason": "..." }
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()

    if not token:
        raise BadRequest("token is required")

    user = User.query.filter_by(token=token).first()
    if not user:
        return jsonify({"allowed": False, "reason": "invalid token"}), 200

    account = Account.query.filter_by(user_id=user.id).first()
    if not account or not account.billing_enabled:
        return jsonify({"allowed": False, "reason": "billing not enabled"}), 200

    if account.credit_remaining <= 0:
        return jsonify({"allowed": False, "reason": "credit limit reached"}), 200

    return jsonify(
        {
            "allowed": True,
            "reason": "ok",
            "user_id": user.id,
            "username": user.username,
            "account_id": account.id,
            "credit_remaining": account.credit_remaining,
        }
    )
