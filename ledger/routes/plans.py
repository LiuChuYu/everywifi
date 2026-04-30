from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Conflict

from ..database import db
from ..models import Plan

bp = Blueprint("plans", __name__, url_prefix="/plans")


@bp.route("", methods=["GET"])
def list_plans():
    plans = Plan.query.all()
    return jsonify([p.to_dict() for p in plans])


@bp.route("", methods=["POST"])
def create_plan():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    price = data.get("price")
    data_limit_mb = data.get("data_limit_mb")
    duration_days = data.get("duration_days")

    if not name or price is None or data_limit_mb is None or duration_days is None:
        raise BadRequest("name, price, data_limit_mb and duration_days are required")
    if not isinstance(price, int) or price < 0:
        raise BadRequest("price must be a non-negative integer")
    if not isinstance(data_limit_mb, int) or data_limit_mb < 0:
        raise BadRequest("data_limit_mb must be a non-negative integer (0 = unlimited)")
    if not isinstance(duration_days, int) or duration_days <= 0:
        raise BadRequest("duration_days must be a positive integer")

    if Plan.query.filter_by(name=name).first():
        raise Conflict("plan name already exists")

    plan = Plan(
        name=name,
        price=price,
        data_limit_mb=data_limit_mb,
        duration_days=duration_days,
        description=data.get("description"),
    )
    db.session.add(plan)
    db.session.commit()
    return jsonify(plan.to_dict()), 201


@bp.route("/<int:plan_id>", methods=["GET"])
def get_plan(plan_id):
    plan = db.get_or_404(Plan, plan_id)
    return jsonify(plan.to_dict())
