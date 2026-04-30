from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from ..database import db
from ..models import Purchase, Usage, User

bp = Blueprint("usage", __name__, url_prefix="/usage")


def _find_active_purchase(user_id):
    """找到使用者目前有效的購買方案"""
    purchases = Purchase.query.filter_by(
        user_id=user_id, payment_status=Purchase.STATUS_PAID
    ).all()
    for p in purchases:
        if p.is_active:
            return p
    return None


@bp.route("/user/<int:user_id>", methods=["GET"])
def get_usage(user_id):
    db.get_or_404(User, user_id)
    purchase = _find_active_purchase(user_id)
    if not purchase:
        return jsonify({"user_id": user_id, "active_purchase": None, "can_access": False})

    return jsonify(
        {
            "user_id": user_id,
            "can_access": True,
            "active_purchase": purchase.to_dict(),
        }
    )


@bp.route("/deduct", methods=["POST"])
def deduct_usage():
    """OpenWrt 呼叫此端點扣除流量。
    Body: { "token": "...", "bytes_used": 102400, "mac_address": "aa:bb:cc:dd:ee:ff" }
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    bytes_used = data.get("bytes_used")
    mac_address = data.get("mac_address")

    if not token:
        raise BadRequest("token is required")
    if bytes_used is None or not isinstance(bytes_used, int) or bytes_used < 0:
        raise BadRequest("bytes_used must be a non-negative integer")

    user = User.query.filter_by(token=token).first()
    if not user:
        raise NotFound("invalid token")

    purchase = _find_active_purchase(user.id)
    if not purchase:
        raise Forbidden("no active purchase found")

    usage = Usage(
        user_id=user.id,
        purchase_id=purchase.id,
        bytes_used=bytes_used,
        mac_address=mac_address,
    )
    db.session.add(usage)
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "purchase_id": purchase.id,
            "mb_used": round(purchase.mb_used, 3),
            "mb_remaining": round(purchase.mb_remaining, 3) if purchase.mb_remaining is not None else None,
            "is_active": purchase.is_active,
        }
    )
