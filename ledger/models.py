import hashlib
import secrets
from datetime import datetime, timezone

from werkzeug.security import check_password_hash, generate_password_hash

from .database import db


class User(db.Model):
    """WiFi 使用者帳號"""

    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    token = db.Column(db.String(64), unique=True, nullable=True)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    account = db.relationship("Account", back_populates="user", uselist=False, lazy=True)

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def generate_token(self):
        self.token = secrets.token_hex(32)
        return self.token

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "email": self.email,
            "created_at": self.created_at.isoformat(),
        }


class Account(db.Model):
    """使用者計費帳戶（後付計量）

    credit_limit  – 預算上限，單位：毫元（milli-TWD）。1000 = 1 元。
    balance_used  – 已累計費用，單位同上。
    billing_enabled – 是否已啟用付費；False 時不允許上網。
    """

    __tablename__ = "accounts"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), unique=True, nullable=False)
    credit_limit = db.Column(db.Integer, nullable=False, default=0)  # milli-TWD
    balance_used = db.Column(db.Integer, nullable=False, default=0)  # milli-TWD
    billing_enabled = db.Column(db.Boolean, nullable=False, default=False)
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))

    user = db.relationship("User", back_populates="account")
    sessions = db.relationship("Session", back_populates="account", lazy=True)

    @property
    def credit_remaining(self):
        return max(0, self.credit_limit - self.balance_used)

    @property
    def can_access(self):
        return self.billing_enabled and self.credit_remaining > 0

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "credit_limit": self.credit_limit,
            "balance_used": self.balance_used,
            "credit_remaining": self.credit_remaining,
            "billing_enabled": self.billing_enabled,
            "can_access": self.can_access,
            "created_at": self.created_at.isoformat(),
        }


class RateCard(db.Model):
    """費率表：每 MB 收多少錢（毫元）"""

    __tablename__ = "rate_cards"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    price_per_mb = db.Column(db.Integer, nullable=False)  # milli-TWD per MB
    description = db.Column(db.String(256), nullable=True)

    usages = db.relationship("Usage", back_populates="rate_card", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price_per_mb": self.price_per_mb,
            "description": self.description,
        }


class Provider(db.Model):
    """WiFi 熱點業者"""

    __tablename__ = "providers"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256), nullable=True)

    nodes = db.relationship("Node", back_populates="provider", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
        }


class Node(db.Model):
    """WiFi 熱點節點"""

    __tablename__ = "nodes"

    id = db.Column(db.Integer, primary_key=True)
    provider_id = db.Column(db.Integer, db.ForeignKey("providers.id"), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    location = db.Column(db.String(128), nullable=True)

    provider = db.relationship("Provider", back_populates="nodes")
    sessions = db.relationship("Session", back_populates="node", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "provider_id": self.provider_id,
            "provider_name": self.provider.name if self.provider else None,
            "name": self.name,
            "location": self.location,
        }


class Session(db.Model):
    """裝置連線會話（一個帳戶可同時有多個裝置的 Session）"""

    __tablename__ = "sessions"

    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey("accounts.id"), nullable=False)
    device_id = db.Column(db.String(64), nullable=False)  # MAC 或 UUID
    node_id = db.Column(db.Integer, db.ForeignKey("nodes.id"), nullable=True)
    started_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    ended_at = db.Column(db.DateTime, nullable=True)
    bytes_used = db.Column(db.BigInteger, nullable=False, default=0)
    cost_millitwd = db.Column(db.Integer, nullable=False, default=0)  # 本 Session 累計費用

    account = db.relationship("Account", back_populates="sessions")
    node = db.relationship("Node", back_populates="sessions")
    usages = db.relationship("Usage", back_populates="session", lazy=True)

    @property
    def is_active(self):
        return self.ended_at is None

    def to_dict(self):
        return {
            "id": self.id,
            "account_id": self.account_id,
            "device_id": self.device_id,
            "node_id": self.node_id,
            "started_at": self.started_at.isoformat(),
            "ended_at": self.ended_at.isoformat() if self.ended_at else None,
            "is_active": self.is_active,
            "bytes_used": self.bytes_used,
            "mb_used": round(self.bytes_used / (1024 * 1024), 3),
            "cost_millitwd": self.cost_millitwd,
        }


class Usage(db.Model):
    """流量使用紀錄（Hash Chain 帳本）

    每筆記錄包含前一筆的 record_hash，形成 append-only Hash Chain，
    可偵測任何事後竄改。
    prev_hash   – 前一筆 Usage 的 record_hash（創世紀錄為 64 個 '0'）。
    record_hash – sha256(id:user_id:session_id:bytes_used:cost_millitwd:recorded_at:prev_hash)
    """

    __tablename__ = "usages"

    GENESIS_HASH = "0" * 64

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    session_id = db.Column(db.Integer, db.ForeignKey("sessions.id"), nullable=False)
    rate_card_id = db.Column(db.Integer, db.ForeignKey("rate_cards.id"), nullable=True)
    bytes_used = db.Column(db.BigInteger, nullable=False)
    cost_millitwd = db.Column(db.Integer, nullable=False, default=0)  # 本次費用（毫元）
    recorded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    mac_address = db.Column(db.String(17), nullable=True)
    prev_hash = db.Column(db.String(64), nullable=False, default=GENESIS_HASH)
    record_hash = db.Column(db.String(64), nullable=False, default="")

    session = db.relationship("Session", back_populates="usages")
    rate_card = db.relationship("RateCard", back_populates="usages")

    def compute_hash(self):
        """計算本筆記錄的 Hash（必須在 recorded_at 確定後呼叫）"""
        raw = (
            f"{self.id}:{self.user_id}:{self.session_id}:"
            f"{self.bytes_used}:{self.cost_millitwd}:"
            f"{self.recorded_at.isoformat()}:{self.prev_hash}"
        )
        return hashlib.sha256(raw.encode()).hexdigest()

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "rate_card_id": self.rate_card_id,
            "bytes_used": self.bytes_used,
            "mb_used": round(self.bytes_used / (1024 * 1024), 3),
            "cost_millitwd": self.cost_millitwd,
            "recorded_at": self.recorded_at.isoformat(),
            "mac_address": self.mac_address,
            "prev_hash": self.prev_hash,
            "record_hash": self.record_hash,
        }
