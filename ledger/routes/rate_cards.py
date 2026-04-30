from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Conflict

from ..database import db
from ..models import RateCard

bp = Blueprint("rate_cards", __name__, url_prefix="/rate-cards")


@bp.route("", methods=["GET"])
def list_rate_cards():
    cards = RateCard.query.all()
    return jsonify([c.to_dict() for c in cards])


@bp.route("", methods=["POST"])
def create_rate_card():
    """建立費率表。
    Body: { "name": "Standard", "price_per_mb": 2000, "description": "..." }
    price_per_mb 單位為毫元（milli-TWD）。2000 = 每 MB 2 元。
    """
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    price_per_mb = data.get("price_per_mb")

    if not name or price_per_mb is None:
        raise BadRequest("name and price_per_mb are required")
    if not isinstance(price_per_mb, int) or price_per_mb < 0:
        raise BadRequest("price_per_mb must be a non-negative integer (milli-TWD per MB)")

    if RateCard.query.filter_by(name=name).first():
        raise Conflict("rate card name already exists")

    card = RateCard(
        name=name,
        price_per_mb=price_per_mb,
        description=data.get("description"),
    )
    db.session.add(card)
    db.session.commit()
    return jsonify(card.to_dict()), 201


@bp.route("/<int:card_id>", methods=["GET"])
def get_rate_card(card_id):
    card = db.get_or_404(RateCard, card_id)
    return jsonify(card.to_dict())
