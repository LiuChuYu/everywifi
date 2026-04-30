"""
Ledger (帳本) module for EveryWifi.

Tracks user accounts, credit balances, and data-usage transactions for
public WiFi hotspot and LoRa IoT network billing.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional


class TransactionType(str, Enum):
    CREDIT = "credit"    # 儲值 / top-up
    DEBIT = "debit"      # 扣款 / charge for usage
    TRANSFER = "transfer"  # 轉帳 / transfer between accounts
    REFUND = "refund"    # 退款 / refund


@dataclass
class Transaction:
    """A single ledger entry."""

    id: str
    account_id: str
    tx_type: TransactionType
    amount: float          # positive for credit/refund, negative for debit
    description: str
    timestamp: datetime
    related_account_id: Optional[str] = None  # used for transfers

    def __post_init__(self) -> None:
        if self.amount == 0:
            raise ValueError("Transaction amount must not be zero.")


@dataclass
class Account:
    """A WiFi user account with a credit balance."""

    id: str
    name: str
    balance: float = 0.0
    transactions: List[Transaction] = field(default_factory=list)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    # ------------------------------------------------------------------ #
    # Internal helpers                                                     #
    # ------------------------------------------------------------------ #

    def _record(
        self,
        tx_type: TransactionType,
        amount: float,
        description: str,
        related_account_id: Optional[str] = None,
    ) -> Transaction:
        tx = Transaction(
            id=str(uuid.uuid4()),
            account_id=self.id,
            tx_type=tx_type,
            amount=amount,
            description=description,
            timestamp=datetime.now(timezone.utc),
            related_account_id=related_account_id,
        )
        self.transactions.append(tx)
        self.balance = round(self.balance + amount, 6)
        return tx

    # ------------------------------------------------------------------ #
    # Public API                                                           #
    # ------------------------------------------------------------------ #

    def deposit(self, amount: float, description: str = "儲值") -> Transaction:
        """Credit the account (top-up)."""
        if amount <= 0:
            raise ValueError(f"Deposit amount must be positive, got {amount}.")
        return self._record(TransactionType.CREDIT, amount, description)

    def charge(self, amount: float, description: str = "使用費") -> Transaction:
        """Debit the account for WiFi / LoRa usage."""
        if amount <= 0:
            raise ValueError(f"Charge amount must be positive, got {amount}.")
        if self.balance < amount:
            raise ValueError(
                f"Insufficient balance ({self.balance:.4f}) for charge of {amount:.4f}."
            )
        return self._record(TransactionType.DEBIT, -amount, description)

    def refund(self, amount: float, description: str = "退款") -> Transaction:
        """Refund a previously charged amount."""
        if amount <= 0:
            raise ValueError(f"Refund amount must be positive, got {amount}.")
        return self._record(TransactionType.REFUND, amount, description)

    def get_history(
        self,
        tx_type: Optional[TransactionType] = None,
        since: Optional[datetime] = None,
    ) -> List[Transaction]:
        """Return transaction history, optionally filtered."""
        result = self.transactions
        if tx_type is not None:
            result = [t for t in result if t.tx_type == tx_type]
        if since is not None:
            result = [t for t in result if t.timestamp >= since]
        return list(result)

    def total_charged(self) -> float:
        """Sum of all debit amounts (returned as a positive number)."""
        return round(
            sum(-t.amount for t in self.transactions if t.tx_type == TransactionType.DEBIT),
            6,
        )

    def total_deposited(self) -> float:
        """Sum of all top-up amounts."""
        return round(
            sum(t.amount for t in self.transactions if t.tx_type == TransactionType.CREDIT),
            6,
        )


class Ledger:
    """Central ledger that manages all accounts."""

    def __init__(self) -> None:
        self._accounts: dict[str, Account] = {}

    # ------------------------------------------------------------------ #
    # Account management                                                   #
    # ------------------------------------------------------------------ #

    def create_account(self, name: str, initial_balance: float = 0.0) -> Account:
        """Create a new account and optionally seed it with an initial balance."""
        if not name or not name.strip():
            raise ValueError("Account name must not be empty.")
        account_id = str(uuid.uuid4())
        account = Account(id=account_id, name=name.strip())
        self._accounts[account_id] = account
        if initial_balance > 0:
            account.deposit(initial_balance, description="初始儲值")
        return account

    def get_account(self, account_id: str) -> Account:
        """Retrieve an account by ID."""
        account = self._accounts.get(account_id)
        if account is None:
            raise KeyError(f"Account '{account_id}' not found.")
        return account

    def list_accounts(self) -> List[Account]:
        """Return all accounts."""
        return list(self._accounts.values())

    def delete_account(self, account_id: str) -> None:
        """Remove an account (must have zero balance)."""
        account = self.get_account(account_id)
        if account.balance != 0:
            raise ValueError(
                f"Cannot delete account with non-zero balance ({account.balance})."
            )
        del self._accounts[account_id]

    # ------------------------------------------------------------------ #
    # Transfer                                                             #
    # ------------------------------------------------------------------ #

    def transfer(
        self,
        from_account_id: str,
        to_account_id: str,
        amount: float,
        description: str = "帳戶轉帳",
    ) -> tuple[Transaction, Transaction]:
        """Transfer credits between two accounts."""
        if from_account_id == to_account_id:
            raise ValueError("Cannot transfer to the same account.")
        if amount <= 0:
            raise ValueError(f"Transfer amount must be positive, got {amount}.")

        sender = self.get_account(from_account_id)
        receiver = self.get_account(to_account_id)

        if sender.balance < amount:
            raise ValueError(
                f"Insufficient balance ({sender.balance:.4f}) for transfer of {amount:.4f}."
            )

        sender_tx = sender._record(
            TransactionType.TRANSFER,
            -amount,
            description,
            related_account_id=to_account_id,
        )
        receiver_tx = receiver._record(
            TransactionType.TRANSFER,
            amount,
            description,
            related_account_id=from_account_id,
        )
        return sender_tx, receiver_tx

    # ------------------------------------------------------------------ #
    # Reports                                                              #
    # ------------------------------------------------------------------ #

    def summary(self) -> dict:
        """High-level ledger summary."""
        accounts = self.list_accounts()
        return {
            "total_accounts": len(accounts),
            "total_balance": round(sum(a.balance for a in accounts), 6),
            "total_deposited": round(sum(a.total_deposited() for a in accounts), 6),
            "total_charged": round(sum(a.total_charged() for a in accounts), 6),
        }
