"""
Authentication / session management for WiFi clients.

Maintains:
  - A set of free-tier MACs (nftables set 'ewf_free')
  - A set of paid-tier MACs with their quota remaining (bytes)
  - Integrates with Ledger to verify EWF token payments

nftables sets are used for zero-overhead kernel-level MAC allowlisting.
The FORWARD chain rule:  ip saddr @ewf_paid accept
                         ip saddr @ewf_free accept  (with rate limit)
"""

from __future__ import annotations

import logging
import subprocess
import time
from typing import Dict, Optional

from src.config import (
    DEFAULT_PAID_RATE_KBPS,
    SESSION_TIMEOUT_SECONDS,
    TRAFFIC_BYTES_PER_EWF,
    EWF_MULTIPLIER,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# nftables helpers
# ---------------------------------------------------------------------------

_NFT_TABLE = "inet filter"
_NFT_FREE_SET = "ewf_free"
_NFT_PAID_SET = "ewf_paid"


def _nft(*args: str) -> subprocess.CompletedProcess:
    cmd = ["nft"] + list(args)
    logger.debug("nft %s", " ".join(args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("nft error: %s", result.stderr.strip())
    return result


def _mac_add(set_name: str, mac: str) -> None:
    """Add *mac* to nftables set *set_name* (best-effort)."""
    _nft("add", "element", _NFT_TABLE, set_name, f"{{ {mac} }}")


def _mac_del(set_name: str, mac: str) -> None:
    """Remove *mac* from nftables set *set_name* (best-effort)."""
    _nft("delete", "element", _NFT_TABLE, set_name, f"{{ {mac} }}")


# ---------------------------------------------------------------------------
# Session data
# ---------------------------------------------------------------------------

class Session:
    def __init__(self, mac: str, tier: str, quota_bytes: int = 0) -> None:
        self.mac = mac
        self.tier = tier  # "free" or "paid"
        self.quota_bytes = quota_bytes  # remaining for paid
        self.created_at = time.time()
        self.last_seen = time.time()

    @property
    def expired(self) -> bool:
        return (time.time() - self.last_seen) > SESSION_TIMEOUT_SECONDS


# ---------------------------------------------------------------------------
# AuthManager
# ---------------------------------------------------------------------------

class AuthManager:
    """
    Manages client authentication and session lifecycle.

    Requires a Ledger instance to verify payments.
    """

    def __init__(self, ledger=None) -> None:
        # ledger: src.ledger.ledger.Ledger  (optional, injected by main)
        self._ledger = ledger
        self._sessions: Dict[str, Session] = {}
        # Track which send block hashes have been consumed (prevent double-spend)
        self._used_send_hashes: set[str] = set()

    def set_ledger(self, ledger) -> None:
        self._ledger = ledger

    # ------------------------------------------------------------------
    # Free tier
    # ------------------------------------------------------------------

    def add_free(self, mac: str) -> None:
        """Authenticate a MAC for the free tier."""
        mac = mac.lower()
        session = Session(mac, "free")
        self._sessions[mac] = session
        _mac_add(_NFT_FREE_SET, mac)
        logger.info("auth: free session for MAC %s", mac)

    # ------------------------------------------------------------------
    # Paid tier
    # ------------------------------------------------------------------

    def confirm_payment(self, mac: str, send_block_hash: str) -> Optional[int]:
        """
        Verify that *send_block_hash* is a valid unspent EWF send to this node.
        Returns the quota in bytes credited, or None on failure.
        """
        mac = mac.lower()
        if send_block_hash in self._used_send_hashes:
            logger.warning("auth: send hash %s already used", send_block_hash)
            return None
        if self._ledger is None:
            logger.warning("auth: no ledger — cannot verify payment")
            return None

        # Look up the pending send
        pending = self._ledger.pending_for(mac)  # simplified: pending keyed by send hash
        # Direct lookup in DB
        amount_raw = self._get_pending_amount(send_block_hash)
        if amount_raw is None:
            return None

        self._used_send_hashes.add(send_block_hash)
        quota_bytes = (amount_raw // EWF_MULTIPLIER) * TRAFFIC_BYTES_PER_EWF

        # Upgrade or create session
        if mac in self._sessions and self._sessions[mac].tier == "paid":
            self._sessions[mac].quota_bytes += quota_bytes
        else:
            self._sessions[mac] = Session(mac, "paid", quota_bytes)
            _mac_del(_NFT_FREE_SET, mac)
            _mac_add(_NFT_PAID_SET, mac)

        logger.info(
            "auth: paid session for MAC %s, quota +%d MB",
            mac,
            quota_bytes // (1024 * 1024),
        )
        return quota_bytes

    def _get_pending_amount(self, send_hash: str) -> Optional[int]:
        """Query ledger DB for a pending send's amount."""
        if self._ledger is None:
            return None
        conn = self._ledger._conn
        row = conn.execute(
            "SELECT amount FROM pending WHERE send_hash=?", (send_hash,)
        ).fetchone()
        return int(row["amount"]) if row else None

    # ------------------------------------------------------------------
    # Session cleanup
    # ------------------------------------------------------------------

    def tick(self) -> None:
        """Expire old sessions (call periodically, e.g. every 60s)."""
        expired = [mac for mac, s in self._sessions.items() if s.expired]
        for mac in expired:
            self._remove_session(mac)

    def deduct_traffic(self, mac: str, bytes_used: int) -> None:
        """Called by traffic accounting to deduct paid quota."""
        mac = mac.lower()
        session = self._sessions.get(mac)
        if session and session.tier == "paid":
            session.quota_bytes -= bytes_used
            if session.quota_bytes <= 0:
                logger.info("auth: MAC %s paid quota exhausted", mac)
                self._downgrade_to_free(mac)

    def _downgrade_to_free(self, mac: str) -> None:
        _mac_del(_NFT_PAID_SET, mac)
        self._sessions[mac] = Session(mac, "free")
        _mac_add(_NFT_FREE_SET, mac)

    def _remove_session(self, mac: str) -> None:
        session = self._sessions.pop(mac, None)
        if session:
            _mac_del(_NFT_FREE_SET, mac)
            _mac_del(_NFT_PAID_SET, mac)
            logger.info("auth: session expired for MAC %s", mac)

    def is_authenticated(self, mac: str) -> bool:
        return mac.lower() in self._sessions

    def get_sessions(self) -> list[dict]:
        return [
            {
                "mac": s.mac,
                "tier": s.tier,
                "quota_mb": round(s.quota_bytes / (1024 * 1024), 2),
                "age_s": int(time.time() - s.created_at),
            }
            for s in self._sessions.values()
        ]
