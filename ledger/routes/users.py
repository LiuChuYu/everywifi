from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Conflict, NotFound

from ..database import db
from ..models import User

bp = Blueprint("users", __name__, url_prefix="/users")


@bp.route("", methods=["POST"])
def create_user():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "")

    if not username or not email or not password:
        raise BadRequest("username, email and password are required")

    if User.query.filter_by(username=username).first():
        raise Conflict("username already exists")
    if User.query.filter_by(email=email).first():
        raise Conflict("email already exists")

    user = User(username=username, email=email)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    return jsonify(user.to_dict()), 201


@bp.route("/<int:user_id>", methods=["GET"])
def get_user(user_id):
    user = db.get_or_404(User, user_id)
    return jsonify(user.to_dict())


@bp.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True) or {}
    username = data.get("username", "").strip()
    password = data.get("password", "")

    user = User.query.filter_by(username=username).first()
    if not user or not user.check_password(password):
        raise NotFound("invalid username or password")

    token = user.generate_token()
    db.session.commit()
    return jsonify({"token": token, "user": user.to_dict()})
