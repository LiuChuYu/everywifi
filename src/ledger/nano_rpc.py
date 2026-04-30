"""
Nano RPC client (optional integration with real Nano network).
Used when nodes want to bridge EWF ↔ Nano XNO for liquidity.
"""

from __future__ import annotations

import json
import urllib.request
import urllib.error
from typing import Any, Optional


class NanoRpcError(Exception):
    pass


class NanoRpcClient:
    """
    Minimal HTTP JSON-RPC client for Nano (or NanoTest) nodes.

    Reference: https://docs.nano.org/commands/rpc-protocol/
    """

    def __init__(self, rpc_url: str = "http://127.0.0.1:7076") -> None:
        self._url = rpc_url

    def _call(self, action: str, **kwargs: Any) -> dict:
        payload = json.dumps({"action": action, **kwargs}).encode()
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read())
                if "error" in data:
                    raise NanoRpcError(data["error"])
                return data
        except urllib.error.URLError as exc:
            raise NanoRpcError(f"RPC connection failed: {exc}") from exc

    # ------------------------------------------------------------------
    # Account info
    # ------------------------------------------------------------------

    def account_info(self, account: str) -> dict:
        """Return balance, representative, block count for *account*."""
        return self._call("account_info", account=account, representative=True)

    def account_balance(self, account: str) -> dict:
        """Return {'balance': raw, 'pending': raw} for *account*."""
        return self._call("account_balance", account=account)

    # ------------------------------------------------------------------
    # Block operations
    # ------------------------------------------------------------------

    def block_info(self, block_hash: str) -> dict:
        """Return details for a block by hash."""
        return self._call("block_info", json_block=True, hash=block_hash)

    def process_block(self, block_dict: dict, subtype: str = "send") -> str:
        """Broadcast a signed block to the Nano network. Returns block hash."""
        resp = self._call(
            "process",
            json_block=True,
            subtype=subtype,
            block=block_dict,
        )
        return resp["hash"]

    def receivable(self, account: str, count: int = 10) -> dict:
        """Return pending (receivable) sends for *account*."""
        return self._call("receivable", account=account, count=str(count))

    # ------------------------------------------------------------------
    # Work generation
    # ------------------------------------------------------------------

    def work_generate(self, hash_or_pubkey: str, difficulty: Optional[str] = None) -> str:
        """Generate PoW for *hash_or_pubkey* (optionally with explicit difficulty)."""
        kwargs: dict = {"hash": hash_or_pubkey}
        if difficulty:
            kwargs["difficulty"] = difficulty
        return self._call("work_generate", **kwargs)["work"]
