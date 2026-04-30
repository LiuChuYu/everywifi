"""
Block-Lattice ledger inspired by Nano cryptocurrency.

Each account has its own chain of blocks. Transfers are pairs of
  send  (debit from sender's chain)  +
  receive (credit on receiver's chain)

Block types:
  open    – first block on a new account chain (receives the genesis/reward)
  send    – debit; references the destination account and amount
  receive – credit; references the matching send block hash
  change  – change the representative (voting weight delegation)

Storage: SQLite (one DB per node)
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import sqlite3
import struct
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, Optional, Tuple

from src.config import LEDGER_DB_PATH


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
WORK_THRESHOLD = 0xFFFFFE0000000000  # PoW difficulty (adjust for embedded hw)
GENESIS_ACCOUNT = "ewf_genesis_000000000000000000000000000000000000000000000"


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------
class BlockType(str, Enum):
    OPEN = "open"
    SEND = "send"
    RECEIVE = "receive"
    CHANGE = "change"


@dataclass
class Block:
    """Immutable representation of a single block on an account chain."""

    block_type: BlockType
    account: str
    previous: str  # Hash of previous block on this account's chain ("0"*64 for open)
    representative: str  # Account that receives voting weight
    balance: int  # Balance in raw units after this block
    link: str  # Meaning depends on block_type:
    #   open/receive: hash of the matching send block
    #   send: destination account address
    #   change: "0"*64
    signature: str = ""  # Ed25519 hex signature (simplified: HMAC here)
    work: str = ""  # PoW nonce hex
    hash: str = field(default="", init=False)

    def __post_init__(self) -> None:
        self.hash = self._compute_hash()

    def _compute_hash(self) -> str:
        """Compute deterministic block hash."""
        payload = "|".join(
            [
                self.block_type.value,
                self.account,
                self.previous,
                self.representative,
                str(self.balance),
                self.link,
            ]
        )
        return hashlib.blake2b(payload.encode(), digest_size=32).hexdigest()

    def to_dict(self) -> dict:
        return {
            "type": self.block_type.value,
            "account": self.account,
            "previous": self.previous,
            "representative": self.representative,
            "balance": str(self.balance),
            "link": self.link,
            "signature": self.signature,
            "work": self.work,
            "hash": self.hash,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Block":
        b = cls(
            block_type=BlockType(d["type"]),
            account=d["account"],
            previous=d["previous"],
            representative=d["representative"],
            balance=int(d["balance"]),
            link=d["link"],
            signature=d.get("signature", ""),
            work=d.get("work", ""),
        )
        return b


# ---------------------------------------------------------------------------
# Proof-of-Work (lightweight Blake2b PoW, same concept as Nano)
# ---------------------------------------------------------------------------

def compute_pow(block_hash: str, threshold: int = WORK_THRESHOLD) -> str:
    """Brute-force a PoW nonce for *block_hash* meeting *threshold*."""
    target = threshold
    while True:
        nonce = secrets.token_bytes(8)
        digest = hashlib.blake2b(
            nonce + bytes.fromhex(block_hash), digest_size=8
        ).digest()
        value = struct.unpack(">Q", digest)[0]
        if value >= target:
            return nonce.hex()


def verify_pow(block_hash: str, work: str, threshold: int = WORK_THRESHOLD) -> bool:
    """Return True if *work* satisfies *threshold* for *block_hash*."""
    try:
        nonce = bytes.fromhex(work)
        digest = hashlib.blake2b(
            nonce + bytes.fromhex(block_hash), digest_size=8
        ).digest()
        value = struct.unpack(">Q", digest)[0]
        return value >= threshold
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Account key management (simplified: HMAC-based signing, not Ed25519)
# ---------------------------------------------------------------------------

def generate_account() -> Tuple[str, str]:
    """Return (private_key_hex, account_address)."""
    private_key = secrets.token_hex(32)
    pub_bytes = hashlib.blake2b(
        bytes.fromhex(private_key), digest_size=32
    ).digest()
    address = "ewf_" + pub_bytes.hex()
    return private_key, address


def sign_block(block: Block, private_key: str) -> str:
    """Return HMAC-Blake2b signature of block.hash with private_key."""
    return hmac.new(
        bytes.fromhex(private_key),
        bytes.fromhex(block.hash),
        digestmod=hashlib.blake2b,
    ).hexdigest()


def verify_signature(block: Block, signature: str, public_key_hex: str) -> bool:
    """Verify that *signature* was created by the owner of *public_key_hex*."""
    # In production replace with Ed25519; here we use the public key directly
    expected = hmac.new(
        bytes.fromhex(public_key_hex),
        bytes.fromhex(block.hash),
        digestmod=hashlib.blake2b,
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ---------------------------------------------------------------------------
# SQLite persistence
# ---------------------------------------------------------------------------
_SCHEMA = """
CREATE TABLE IF NOT EXISTS blocks (
    hash        TEXT PRIMARY KEY,
    block_type  TEXT NOT NULL,
    account     TEXT NOT NULL,
    previous    TEXT NOT NULL,
    representative TEXT NOT NULL,
    balance     TEXT NOT NULL,
    link        TEXT NOT NULL,
    signature   TEXT NOT NULL,
    work        TEXT NOT NULL,
    created_at  INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_blocks_account ON blocks(account);

CREATE TABLE IF NOT EXISTS accounts (
    address     TEXT PRIMARY KEY,
    head_hash   TEXT NOT NULL,   -- latest block hash on this chain
    balance     TEXT NOT NULL,   -- raw balance
    public_key  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending (
    send_hash   TEXT PRIMARY KEY,  -- hash of the matching send block
    dest_account TEXT NOT NULL,
    amount       TEXT NOT NULL,
    created_at   INTEGER NOT NULL
);
"""


class Ledger:
    """Thread-safe local ledger backed by SQLite."""

    def __init__(self, db_path: str = LEDGER_DB_PATH) -> None:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # ------------------------------------------------------------------
    # Account creation
    # ------------------------------------------------------------------

    def create_account(
        self,
        address: str,
        public_key: str,
        representative: Optional[str] = None,
    ) -> bool:
        """Register a new account (no balance yet). Returns False if exists."""
        rep = representative or GENESIS_ACCOUNT
        try:
            self._conn.execute(
                "INSERT INTO accounts(address, head_hash, balance, public_key)"
                " VALUES (?, ?, ?, ?)",
                (address, "0" * 64, "0", public_key),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_balance(self, address: str) -> int:
        """Return balance in raw units for *address* (0 if unknown)."""
        row = self._conn.execute(
            "SELECT balance FROM accounts WHERE address=?", (address,)
        ).fetchone()
        return int(row["balance"]) if row else 0

    def get_head(self, address: str) -> str:
        """Return the head block hash for *address*."""
        row = self._conn.execute(
            "SELECT head_hash FROM accounts WHERE address=?", (address,)
        ).fetchone()
        return row["head_hash"] if row else "0" * 64

    # ------------------------------------------------------------------
    # Block processing
    # ------------------------------------------------------------------

    def process_block(self, block: Block) -> bool:
        """
        Validate and store a block.  Returns True on success.
        """
        if not self._validate(block):
            return False
        ts = int(time.time())
        try:
            self._conn.execute(
                "INSERT INTO blocks"
                "(hash, block_type, account, previous, representative,"
                " balance, link, signature, work, created_at)"
                " VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    block.hash,
                    block.block_type.value,
                    block.account,
                    block.previous,
                    block.representative,
                    str(block.balance),
                    block.link,
                    block.signature,
                    block.work,
                    ts,
                ),
            )
            if block.block_type == BlockType.SEND:
                # Compute sent amount BEFORE updating the account balance
                prev_balance = self.get_balance(block.account)
                sent_amount = prev_balance - block.balance
                self._conn.execute(
                    "INSERT INTO pending(send_hash, dest_account, amount, created_at)"
                    " VALUES (?,?,?,?)",
                    (block.hash, block.link, str(sent_amount), ts),
                )
            elif block.block_type in (BlockType.RECEIVE, BlockType.OPEN):
                self._conn.execute(
                    "DELETE FROM pending WHERE send_hash=?", (block.link,)
                )
            self._conn.execute(
                "UPDATE accounts SET head_hash=?, balance=? WHERE address=?",
                (block.hash, str(block.balance), block.account),
            )
            self._conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False  # duplicate block

    # ------------------------------------------------------------------
    # High-level helpers
    # ------------------------------------------------------------------

    def send(
        self,
        sender_address: str,
        dest_address: str,
        amount_raw: int,
        private_key: str,
        representative: Optional[str] = None,
    ) -> Optional[Block]:
        """Create and process a send block. Returns the block or None."""
        balance = self.get_balance(sender_address)
        if balance < amount_raw:
            return None
        previous = self.get_head(sender_address)
        rep = representative or sender_address
        block = Block(
            block_type=BlockType.SEND,
            account=sender_address,
            previous=previous,
            representative=rep,
            balance=balance - amount_raw,
            link=dest_address,
        )
        block.work = compute_pow(previous if previous != "0" * 64 else block.hash)
        block.signature = sign_block(block, private_key)
        # Recompute hash after sign/work (hash doesn't include sig/work so it stays)
        if self.process_block(block):
            return block
        return None

    def receive(
        self,
        receiver_address: str,
        send_hash: str,
        private_key: str,
        representative: Optional[str] = None,
    ) -> Optional[Block]:
        """Create and process a receive block for a pending send. Returns block or None."""
        row = self._conn.execute(
            "SELECT dest_account, amount FROM pending WHERE send_hash=?",
            (send_hash,),
        ).fetchone()
        if not row or row["dest_account"] != receiver_address:
            return None
        amount = int(row["amount"])
        previous = self.get_head(receiver_address)
        rep = representative or receiver_address
        new_balance = self.get_balance(receiver_address) + amount
        btype = BlockType.OPEN if previous == "0" * 64 else BlockType.RECEIVE
        block = Block(
            block_type=btype,
            account=receiver_address,
            previous=previous,
            representative=rep,
            balance=new_balance,
            link=send_hash,
        )
        block.work = compute_pow(previous if previous != "0" * 64 else block.hash)
        block.signature = sign_block(block, private_key)
        if self.process_block(block):
            return block
        return None

    def reward_location(
        self,
        dest_address: str,
        genesis_private_key: str,
        amount_raw: int,
    ) -> bool:
        """Issue a location reward from the genesis account."""
        send_block = self.send(
            GENESIS_ACCOUNT, dest_address, amount_raw, genesis_private_key
        )
        return send_block is not None

    def pending_for(self, address: str) -> list[dict]:
        """Return list of pending receives for *address*."""
        rows = self._conn.execute(
            "SELECT send_hash, amount FROM pending WHERE dest_account=?",
            (address,),
        ).fetchall()
        return [{"send_hash": r["send_hash"], "amount": int(r["amount"])} for r in rows]

    def account_chain(self, address: str, count: int = 10) -> list[dict]:
        """Return the last *count* blocks on *address*'s chain."""
        rows = self._conn.execute(
            "SELECT * FROM blocks WHERE account=? ORDER BY created_at DESC LIMIT ?",
            (address, count),
        ).fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # Validation
    # ------------------------------------------------------------------

    def _validate(self, block: Block) -> bool:
        """Basic structural validation."""
        if not block.hash or len(block.hash) != 64:
            return False
        # Check previous matches head (unless it's the very first block)
        head = self.get_head(block.account)
        if block.block_type == BlockType.OPEN:
            # First block: previous must be zero
            if block.previous != "0" * 64:
                return False
        else:
            if block.previous != head:
                return False
        # Balance non-negative
        if block.balance < 0:
            return False
        # Send: balance must decrease; balance must be enough
        if block.block_type == BlockType.SEND:
            current = self.get_balance(block.account)
            if block.balance >= current:
                return False
        return True

    def close(self) -> None:
        self._conn.close()
