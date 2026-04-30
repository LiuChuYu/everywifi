from datetime import datetime, timedelta, timezone

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, NotFound

from ..database import db
from ..models import Plan, Purchase, User

bp = Blueprint("purchases", __name__, url_prefix="/purchases")


@bp.route("", methods=["POST"])
def create_purchase():
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    plan_id = data.get("plan_id")

    if not user_id or not plan_id:
        raise BadRequest("user_id and plan_id are required")

    user = db.get_or_404(User, user_id)
    plan = db.get_or_404(Plan, plan_id)

    purchase = Purchase(
        user_id=user.id,
        plan_id=plan.id,
        amount=plan.price,
        payment_status=Purchase.STATUS_PENDING,
    )
    db.session.add(purchase)
    db.session.commit()
    return jsonify(purchase.to_dict()), 201


@bp.route("/<int:purchase_id>/pay", methods=["POST"])
def pay_purchase(purchase_id):
    """模擬付款確認，將狀態設為 paid 並啟動計時"""
    purchase = db.get_or_404(Purchase, purchase_id)

    if purchase.payment_status == Purchase.STATUS_PAID:
        raise BadRequest("purchase already paid")

    purchase.payment_status = Purchase.STATUS_PAID
    purchase.expires_at = datetime.now(timezone.utc) + timedelta(days=purchase.plan.duration_days)
    db.session.commit()
    return jsonify(purchase.to_dict())


@bp.route("/<int:purchase_id>", methods=["GET"])
def get_purchase(purchase_id):
    purchase = db.get_or_404(Purchase, purchase_id)
    return jsonify(purchase.to_dict())


@bp.route("/user/<int:user_id>", methods=["GET"])
def get_user_purchases(user_id):
    db.get_or_404(User, user_id)
    purchases = Purchase.query.filter_by(user_id=user_id).all()
    return jsonify([p.to_dict() for p in purchases])
