from datetime import datetime, timezone

from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from ..database import db
from ..models import Account, Node, Session, User

bp = Blueprint("sessions", __name__, url_prefix="/sessions")


def _get_account_from_token(token):
    """從 token 解析出 User 及其 Account（如不存在則拋出例外）"""
    if not token:
        raise BadRequest("token is required")
    user = User.query.filter_by(token=token).first()
    if not user:
        raise NotFound("invalid token")
    if not user.account:
        raise NotFound("no account found for this user")
    return user, user.account


@bp.route("", methods=["POST"])
def start_session():
    """開始一個裝置的連線會話。
    Body: { "token": "...", "device_id": "aa:bb:cc:dd:ee:ff", "node_id": 1 (optional) }
    每個設備可以獨立開啟 Session，共用同一個帳戶的預算上限。
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    device_id = data.get("device_id", "").strip()
    node_id = data.get("node_id")

    if not device_id:
        raise BadRequest("device_id is required")

    user, account = _get_account_from_token(token)

    if not account.can_access:
        raise Forbidden("billing not enabled or credit limit reached")

    if node_id is not None:
        node = db.session.get(Node, node_id)
        if not node:
            raise NotFound(f"node {node_id} not found")

    session = Session(
        account_id=account.id,
        device_id=device_id,
        node_id=node_id,
    )
    db.session.add(session)
    db.session.commit()
    return jsonify(session.to_dict()), 201


@bp.route("/<int:session_id>/end", methods=["POST"])
def end_session(session_id):
    """結束連線會話。"""
    session = db.get_or_404(Session, session_id)
    if not session.is_active:
        raise BadRequest("session already ended")
    session.ended_at = datetime.now(timezone.utc)
    db.session.commit()
    return jsonify(session.to_dict())


@bp.route("/<int:session_id>", methods=["GET"])
def get_session(session_id):
    return jsonify(db.get_or_404(Session, session_id).to_dict())


@bp.route("/account/<int:account_id>", methods=["GET"])
def list_sessions(account_id):
    """列出帳戶的所有 Session（包含已結束的）"""
    db.get_or_404(Account, account_id)
    sessions = Session.query.filter_by(account_id=account_id).all()
    return jsonify([s.to_dict() for s in sessions])


@bp.route("/account/<int:account_id>/active", methods=["GET"])
def list_active_sessions(account_id):
    """列出帳戶目前進行中的 Session"""
    db.get_or_404(Account, account_id)
    sessions = Session.query.filter_by(account_id=account_id, ended_at=None).all()
    return jsonify([s.to_dict() for s in sessions])
