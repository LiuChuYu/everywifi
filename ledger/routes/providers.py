from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Conflict

from ..database import db
from ..models import Node, Provider

bp = Blueprint("providers", __name__, url_prefix="/providers")


# ── Provider ──────────────────────────────────────────────────────────────────

@bp.route("", methods=["GET"])
def list_providers():
    return jsonify([p.to_dict() for p in Provider.query.all()])


@bp.route("", methods=["POST"])
def create_provider():
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        raise BadRequest("name is required")
    if Provider.query.filter_by(name=name).first():
        raise Conflict("provider name already exists")

    provider = Provider(name=name, description=data.get("description"))
    db.session.add(provider)
    db.session.commit()
    return jsonify(provider.to_dict()), 201


@bp.route("/<int:provider_id>", methods=["GET"])
def get_provider(provider_id):
    return jsonify(db.get_or_404(Provider, provider_id).to_dict())


# ── Node ──────────────────────────────────────────────────────────────────────

@bp.route("/<int:provider_id>/nodes", methods=["GET"])
def list_nodes(provider_id):
    db.get_or_404(Provider, provider_id)
    return jsonify([n.to_dict() for n in Node.query.filter_by(provider_id=provider_id).all()])


@bp.route("/<int:provider_id>/nodes", methods=["POST"])
def create_node(provider_id):
    db.get_or_404(Provider, provider_id)
    data = request.get_json(silent=True) or {}
    name = data.get("name", "").strip()
    if not name:
        raise BadRequest("name is required")

    node = Node(
        provider_id=provider_id,
        name=name,
        location=data.get("location"),
    )
    db.session.add(node)
    db.session.commit()
    return jsonify(node.to_dict()), 201


@bp.route("/<int:provider_id>/nodes/<int:node_id>", methods=["GET"])
def get_node(provider_id, node_id):
    node = db.get_or_404(Node, node_id)
    if node.provider_id != provider_id:
        from werkzeug.exceptions import NotFound
        raise NotFound("node not found for this provider")
    return jsonify(node.to_dict())
