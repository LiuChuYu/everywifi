"""Tests for the EveryWifi ledger (帳本) module."""

import pytest

from src.ledger import Account, Ledger, Transaction, TransactionType


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def ledger() -> Ledger:
    return Ledger()


@pytest.fixture
def account(ledger: Ledger) -> Account:
    return ledger.create_account("Alice", initial_balance=100.0)


# ---------------------------------------------------------------------------
# Account creation
# ---------------------------------------------------------------------------


class TestCreateAccount:
    def test_create_basic(self, ledger: Ledger) -> None:
        acc = ledger.create_account("Bob")
        assert acc.name == "Bob"
        assert acc.balance == 0.0
        assert acc.id in [a.id for a in ledger.list_accounts()]

    def test_create_with_initial_balance(self, ledger: Ledger) -> None:
        acc = ledger.create_account("Carol", initial_balance=50.0)
        assert acc.balance == 50.0
        assert len(acc.transactions) == 1
        assert acc.transactions[0].tx_type == TransactionType.CREDIT

    def test_create_empty_name_raises(self, ledger: Ledger) -> None:
        with pytest.raises(ValueError, match="name must not be empty"):
            ledger.create_account("   ")

    def test_create_strips_whitespace(self, ledger: Ledger) -> None:
        acc = ledger.create_account("  Dave  ")
        assert acc.name == "Dave"

    def test_unique_ids(self, ledger: Ledger) -> None:
        ids = {ledger.create_account(f"User{i}").id for i in range(10)}
        assert len(ids) == 10


# ---------------------------------------------------------------------------
# Get / list / delete account
# ---------------------------------------------------------------------------


class TestAccountManagement:
    def test_get_account(self, ledger: Ledger, account: Account) -> None:
        fetched = ledger.get_account(account.id)
        assert fetched is account

    def test_get_missing_account_raises(self, ledger: Ledger) -> None:
        with pytest.raises(KeyError):
            ledger.get_account("nonexistent-id")

    def test_list_accounts(self, ledger: Ledger) -> None:
        ledger.create_account("X")
        ledger.create_account("Y")
        assert len(ledger.list_accounts()) == 2

    def test_delete_zero_balance_account(self, ledger: Ledger) -> None:
        acc = ledger.create_account("Temp")
        ledger.delete_account(acc.id)
        assert acc not in ledger.list_accounts()

    def test_delete_nonzero_balance_raises(self, ledger: Ledger, account: Account) -> None:
        with pytest.raises(ValueError, match="non-zero balance"):
            ledger.delete_account(account.id)

    def test_delete_missing_account_raises(self, ledger: Ledger) -> None:
        with pytest.raises(KeyError):
            ledger.delete_account("ghost")


# ---------------------------------------------------------------------------
# Deposit
# ---------------------------------------------------------------------------


class TestDeposit:
    def test_deposit_increases_balance(self, account: Account) -> None:
        account.deposit(50.0)
        assert account.balance == 150.0

    def test_deposit_records_transaction(self, account: Account) -> None:
        tx = account.deposit(30.0, description="月費儲值")
        assert tx.tx_type == TransactionType.CREDIT
        assert tx.amount == 30.0
        assert tx.description == "月費儲值"

    def test_deposit_zero_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            account.deposit(0.0)

    def test_deposit_negative_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            account.deposit(-10.0)

    def test_multiple_deposits(self, account: Account) -> None:
        account.deposit(10.0)
        account.deposit(20.0)
        account.deposit(30.0)
        assert account.balance == 160.0
        assert account.total_deposited() == 160.0  # 100 initial + 60


# ---------------------------------------------------------------------------
# Charge
# ---------------------------------------------------------------------------


class TestCharge:
    def test_charge_decreases_balance(self, account: Account) -> None:
        account.charge(40.0)
        assert account.balance == 60.0

    def test_charge_records_transaction(self, account: Account) -> None:
        tx = account.charge(25.0, description="WiFi 1小時")
        assert tx.tx_type == TransactionType.DEBIT
        assert tx.amount == -25.0
        assert tx.description == "WiFi 1小時"

    def test_charge_zero_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            account.charge(0.0)

    def test_charge_negative_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            account.charge(-5.0)

    def test_charge_exceeds_balance_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="Insufficient balance"):
            account.charge(200.0)

    def test_charge_exact_balance(self, account: Account) -> None:
        account.charge(100.0)
        assert account.balance == 0.0

    def test_total_charged(self, account: Account) -> None:
        account.charge(10.0)
        account.charge(20.0)
        assert account.total_charged() == 30.0


# ---------------------------------------------------------------------------
# Refund
# ---------------------------------------------------------------------------


class TestRefund:
    def test_refund_increases_balance(self, account: Account) -> None:
        account.charge(40.0)
        account.refund(15.0)
        assert account.balance == 75.0

    def test_refund_records_transaction(self, account: Account) -> None:
        tx = account.refund(5.0, description="客服退款")
        assert tx.tx_type == TransactionType.REFUND
        assert tx.amount == 5.0

    def test_refund_zero_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            account.refund(0.0)

    def test_refund_negative_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="must be positive"):
            account.refund(-1.0)


# ---------------------------------------------------------------------------
# Transfer
# ---------------------------------------------------------------------------


class TestTransfer:
    def test_transfer_moves_balance(self, ledger: Ledger) -> None:
        a = ledger.create_account("Sender", initial_balance=100.0)
        b = ledger.create_account("Receiver")
        ledger.transfer(a.id, b.id, 40.0)
        assert a.balance == 60.0
        assert b.balance == 40.0

    def test_transfer_records_transactions(self, ledger: Ledger) -> None:
        a = ledger.create_account("A", initial_balance=100.0)
        b = ledger.create_account("B")
        sender_tx, receiver_tx = ledger.transfer(a.id, b.id, 25.0)
        assert sender_tx.tx_type == TransactionType.TRANSFER
        assert sender_tx.amount == -25.0
        assert sender_tx.related_account_id == b.id
        assert receiver_tx.tx_type == TransactionType.TRANSFER
        assert receiver_tx.amount == 25.0
        assert receiver_tx.related_account_id == a.id

    def test_transfer_insufficient_balance_raises(self, ledger: Ledger) -> None:
        a = ledger.create_account("A", initial_balance=10.0)
        b = ledger.create_account("B")
        with pytest.raises(ValueError, match="Insufficient balance"):
            ledger.transfer(a.id, b.id, 50.0)

    def test_transfer_same_account_raises(self, ledger: Ledger, account: Account) -> None:
        with pytest.raises(ValueError, match="same account"):
            ledger.transfer(account.id, account.id, 10.0)

    def test_transfer_zero_raises(self, ledger: Ledger) -> None:
        a = ledger.create_account("A", initial_balance=50.0)
        b = ledger.create_account("B")
        with pytest.raises(ValueError, match="must be positive"):
            ledger.transfer(a.id, b.id, 0.0)

    def test_transfer_negative_raises(self, ledger: Ledger) -> None:
        a = ledger.create_account("A", initial_balance=50.0)
        b = ledger.create_account("B")
        with pytest.raises(ValueError, match="must be positive"):
            ledger.transfer(a.id, b.id, -5.0)


# ---------------------------------------------------------------------------
# Transaction history
# ---------------------------------------------------------------------------


class TestHistory:
    def test_full_history(self, account: Account) -> None:
        account.deposit(10.0)
        account.charge(5.0)
        # initial deposit (from fixture) + deposit + charge
        assert len(account.get_history()) == 3

    def test_filter_by_type(self, account: Account) -> None:
        account.deposit(10.0)
        account.charge(5.0)
        credits = account.get_history(tx_type=TransactionType.CREDIT)
        assert all(t.tx_type == TransactionType.CREDIT for t in credits)
        assert len(credits) == 2  # initial + new deposit

    def test_filter_by_since(self, account: Account) -> None:
        from datetime import timedelta

        account.deposit(10.0)
        future = account.transactions[-1].timestamp
        account.charge(5.0)
        results = account.get_history(since=future)
        # Only transactions at or after `future`
        assert all(t.timestamp >= future for t in results)

    def test_empty_history_new_account(self, ledger: Ledger) -> None:
        acc = ledger.create_account("Empty")
        assert acc.get_history() == []


# ---------------------------------------------------------------------------
# Transaction validation
# ---------------------------------------------------------------------------


class TestTransactionValidation:
    def test_zero_amount_raises(self, account: Account) -> None:
        with pytest.raises(ValueError, match="must not be zero"):
            Transaction(
                id="x",
                account_id=account.id,
                tx_type=TransactionType.CREDIT,
                amount=0.0,
                description="bad",
                timestamp=__import__("datetime").datetime.now(),
            )


# ---------------------------------------------------------------------------
# Ledger summary
# ---------------------------------------------------------------------------


class TestSummary:
    def test_summary_empty_ledger(self, ledger: Ledger) -> None:
        s = ledger.summary()
        assert s["total_accounts"] == 0
        assert s["total_balance"] == 0.0

    def test_summary_with_accounts(self, ledger: Ledger) -> None:
        ledger.create_account("A", initial_balance=100.0)
        ledger.create_account("B", initial_balance=50.0)
        a = ledger.list_accounts()[0]
        a.charge(30.0)
        s = ledger.summary()
        assert s["total_accounts"] == 2
        assert s["total_balance"] == 120.0   # (100-30) + 50
        assert s["total_deposited"] == 150.0
        assert s["total_charged"] == 30.0

    def test_summary_total_deposited(self, ledger: Ledger) -> None:
        acc = ledger.create_account("Z", initial_balance=200.0)
        acc.deposit(100.0)
        s = ledger.summary()
        assert s["total_deposited"] == 300.0


# ---------------------------------------------------------------------------
# Floating-point precision
# ---------------------------------------------------------------------------


class TestPrecision:
    def test_repeated_small_charges(self, ledger: Ledger) -> None:
        acc = ledger.create_account("Precision", initial_balance=1.0)
        for _ in range(10):
            acc.charge(0.1)
        assert acc.balance == pytest.approx(0.0, abs=1e-5)

    def test_balance_after_mixed_operations(self, ledger: Ledger) -> None:
        acc = ledger.create_account("Mixed", initial_balance=0.0)
        acc.deposit(99.99)
        acc.charge(33.33)
        acc.charge(33.33)
        acc.refund(10.0)
        # 99.99 - 33.33 - 33.33 + 10.0 = 43.33
        assert acc.balance == pytest.approx(43.33, abs=1e-4)
