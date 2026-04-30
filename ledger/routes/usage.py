from flask import Blueprint, jsonify, request
from werkzeug.exceptions import BadRequest, Forbidden, NotFound

from ..database import db
from ..models import Account, RateCard, Session, Usage, User

bp = Blueprint("usage", __name__, url_prefix="/usage")

_BYTES_PER_MB = 1024 * 1024


def _get_prev_hash():
    """取得最新一筆 Usage 的 record_hash 作為 prev_hash；若無則回傳創世雜湊。"""
    last = Usage.query.order_by(Usage.id.desc()).first()
    return last.record_hash if last else Usage.GENESIS_HASH


@bp.route("/user/<int:user_id>", methods=["GET"])
def get_usage(user_id):
    db.get_or_404(User, user_id)
    account = Account.query.filter_by(user_id=user_id).first()
    if not account:
        return jsonify({"user_id": user_id, "account": None, "can_access": False})

    return jsonify(
        {
            "user_id": user_id,
            "can_access": account.can_access,
            "account": account.to_dict(),
        }
    )


@bp.route("/deduct", methods=["POST"])
def deduct_usage():
    """OpenWrt 呼叫此端點回報流量並即時扣費。

    Body: {
        "token": "...",
        "device_id": "aa:bb:cc:dd:ee:ff",   # 裝置識別（MAC 或 UUID）
        "bytes_used": 102400,
        "rate_card_id": 1                    # 選填；未提供則費用為 0
    }

    系統會：
    1. 找到使用者帳戶，確認 billing_enabled 且 credit_remaining > 0。
    2. 找到或建立此裝置的 active Session。
    3. 依費率計算費用並更新 Account.balance_used。
    4. 寫入 Usage 記錄（含 Hash Chain 欄位）。
    """
    data = request.get_json(silent=True) or {}
    token = data.get("token", "").strip()
    device_id = data.get("device_id", "").strip()
    bytes_used = data.get("bytes_used")
    rate_card_id = data.get("rate_card_id")

    if not token:
        raise BadRequest("token is required")
    if not device_id:
        raise BadRequest("device_id is required")
    if bytes_used is None or not isinstance(bytes_used, int) or bytes_used < 0:
        raise BadRequest("bytes_used must be a non-negative integer")

    user = User.query.filter_by(token=token).first()
    if not user:
        raise NotFound("invalid token")

    account = Account.query.filter_by(user_id=user.id).first()
    if not account or not account.billing_enabled:
        raise Forbidden("billing not enabled")
    if account.credit_remaining <= 0:
        raise Forbidden("credit limit reached")

    # 計算費用 ─────────────────────────────────────────────────────────────
    cost_millitwd = 0
    rate_card = None
    if rate_card_id is not None:
        rate_card = db.session.get(RateCard, rate_card_id)
        if not rate_card:
            raise NotFound(f"rate_card {rate_card_id} not found")
        cost_millitwd = (bytes_used * rate_card.price_per_mb) // _BYTES_PER_MB

    # 找 / 建 active Session for this device ─────────────────────────────
    active_session = Session.query.filter_by(
        account_id=account.id, device_id=device_id, ended_at=None
    ).first()
    if not active_session:
        active_session = Session(account_id=account.id, device_id=device_id)
        db.session.add(active_session)
        db.session.flush()  # 取得 id

    # 更新 Session 累計 ───────────────────────────────────────────────────
    active_session.bytes_used += bytes_used
    active_session.cost_millitwd += cost_millitwd

    # 更新 Account 餘額 ───────────────────────────────────────────────────
    account.balance_used += cost_millitwd

    # 寫入 Usage（Hash Chain）────────────────────────────────────────────
    prev_hash = _get_prev_hash()
    usage = Usage(
        user_id=user.id,
        session_id=active_session.id,
        rate_card_id=rate_card_id,
        bytes_used=bytes_used,
        cost_millitwd=cost_millitwd,
        mac_address=device_id if len(device_id) == 17 else None,
        prev_hash=prev_hash,
    )
    db.session.add(usage)
    db.session.flush()  # 取得 id 及 recorded_at

    usage.record_hash = usage.compute_hash()
    db.session.commit()

    return jsonify(
        {
            "ok": True,
            "session_id": active_session.id,
            "usage_id": usage.id,
            "bytes_used": bytes_used,
            "mb_used": round(bytes_used / _BYTES_PER_MB, 3),
            "cost_millitwd": cost_millitwd,
            "account_balance_used": account.balance_used,
            "account_credit_remaining": account.credit_remaining,
            "can_access": account.can_access,
            "record_hash": usage.record_hash,
        }
    )
