from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Conflict, NotFound

from ..database import db
from ..models import Account, User

bp = Blueprint("accounts", __name__, url_prefix="/accounts")


@bp.route("", methods=["POST"])
def create_account():
    """為使用者建立計費帳戶。
    Body: { "user_id": 1, "credit_limit": 50000, "billing_enabled": false }
    credit_limit 單位為毫元（milli-TWD），50000 = 50 元。
    """
    data = request.get_json(silent=True) or {}
    user_id = data.get("user_id")
    credit_limit = data.get("credit_limit", 0)
    billing_enabled = data.get("billing_enabled", False)

    if not user_id:
        raise BadRequest("user_id is required")
    if not isinstance(credit_limit, int) or credit_limit < 0:
        raise BadRequest("credit_limit must be a non-negative integer (milli-TWD)")

    db.get_or_404(User, user_id)

    if Account.query.filter_by(user_id=user_id).first():
        raise Conflict("account already exists for this user")

    account = Account(
        user_id=user_id,
        credit_limit=credit_limit,
        billing_enabled=billing_enabled,
    )
    db.session.add(account)
    db.session.commit()
    return jsonify(account.to_dict()), 201


@bp.route("/<int:account_id>", methods=["GET"])
def get_account(account_id):
    account = db.get_or_404(Account, account_id)
    return jsonify(account.to_dict())


@bp.route("/user/<int:user_id>", methods=["GET"])
def get_account_by_user(user_id):
    db.get_or_404(User, user_id)
    account = Account.query.filter_by(user_id=user_id).first()
    if not account:
        raise NotFound("no account found for this user")
    return jsonify(account.to_dict())


@bp.route("/<int:account_id>/enable", methods=["POST"])
def enable_billing(account_id):
    """啟用計費。帳戶必須已設定 credit_limit > 0。"""
    account = db.get_or_404(Account, account_id)
    if account.credit_limit <= 0:
        raise BadRequest("credit_limit must be greater than 0 before enabling billing")
    account.billing_enabled = True
    db.session.commit()
    return jsonify(account.to_dict())


@bp.route("/<int:account_id>/disable", methods=["POST"])
def disable_billing(account_id):
    """停用計費。"""
    account = db.get_or_404(Account, account_id)
    account.billing_enabled = False
    db.session.commit()
    return jsonify(account.to_dict())


@bp.route("/<int:account_id>/credit-limit", methods=["PATCH"])
def update_credit_limit(account_id):
    """更新預算上限。
    Body: { "credit_limit": 100000 }
    """
    account = db.get_or_404(Account, account_id)
    data = request.get_json(silent=True) or {}
    credit_limit = data.get("credit_limit")

    if credit_limit is None or not isinstance(credit_limit, int) or credit_limit < 0:
        raise BadRequest("credit_limit must be a non-negative integer (milli-TWD)")

    account.credit_limit = credit_limit
    db.session.commit()
    return jsonify(account.to_dict())
