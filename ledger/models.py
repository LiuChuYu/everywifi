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

    purchases = db.relationship("Purchase", back_populates="user", lazy=True)

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


class Plan(db.Model):
    """套餐定義"""

    __tablename__ = "plans"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    price = db.Column(db.Integer, nullable=False)  # 新台幣（元）
    data_limit_mb = db.Column(db.Integer, nullable=False)  # 流量上限（MB），0 = 無限
    duration_days = db.Column(db.Integer, nullable=False)  # 有效天數
    description = db.Column(db.String(256), nullable=True)

    purchases = db.relationship("Purchase", back_populates="plan", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "price": self.price,
            "data_limit_mb": self.data_limit_mb,
            "duration_days": self.duration_days,
            "description": self.description,
        }


class Purchase(db.Model):
    """購買紀錄"""

    __tablename__ = "purchases"

    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_EXPIRED = "expired"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    plan_id = db.Column(db.Integer, db.ForeignKey("plans.id"), nullable=False)
    amount = db.Column(db.Integer, nullable=False)  # 實際付款金額（元）
    payment_status = db.Column(db.String(16), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    expires_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", back_populates="purchases")
    plan = db.relationship("Plan", back_populates="purchases")
    usages = db.relationship("Usage", back_populates="purchase", lazy=True)

    @property
    def bytes_used(self):
        return sum(u.bytes_used for u in self.usages)

    @property
    def mb_used(self):
        return self.bytes_used / (1024 * 1024)

    @property
    def mb_remaining(self):
        if self.plan.data_limit_mb == 0:
            return None  # 無限流量
        remaining = self.plan.data_limit_mb - self.mb_used
        return max(0.0, remaining)

    @property
    def is_active(self):
        if self.payment_status != self.STATUS_PAID:
            return False
        now = datetime.now(timezone.utc)
        if self.expires_at and self.expires_at.replace(tzinfo=timezone.utc) < now:
            return False
        if self.plan.data_limit_mb > 0 and self.mb_remaining == 0:
            return False
        return True

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "plan_id": self.plan_id,
            "plan_name": self.plan.name if self.plan else None,
            "amount": self.amount,
            "payment_status": self.payment_status,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat() if self.expires_at else None,
            "mb_used": round(self.mb_used, 3),
            "mb_remaining": round(self.mb_remaining, 3) if self.mb_remaining is not None else None,
            "is_active": self.is_active,
        }


class Usage(db.Model):
    """流量使用紀錄"""

    __tablename__ = "usages"

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    purchase_id = db.Column(db.Integer, db.ForeignKey("purchases.id"), nullable=False)
    bytes_used = db.Column(db.BigInteger, nullable=False)  # 本次扣除的 bytes
    recorded_at = db.Column(db.DateTime, default=lambda: datetime.now(timezone.utc))
    mac_address = db.Column(db.String(17), nullable=True)  # OpenWrt 回報的 MAC

    purchase = db.relationship("Purchase", back_populates="usages")

    def to_dict(self):
        return {
            "id": self.id,
            "user_id": self.user_id,
            "purchase_id": self.purchase_id,
            "bytes_used": self.bytes_used,
            "mb_used": round(self.bytes_used / (1024 * 1024), 3),
            "recorded_at": self.recorded_at.isoformat(),
            "mac_address": self.mac_address,
        }
