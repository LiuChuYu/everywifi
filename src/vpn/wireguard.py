"""
WireGuard VPN management.

Responsibilities:
  - Generate WireGuard keypair on first run.
  - Write /etc/wireguard/wg0.conf.
  - Manage peer entries (add / remove via `wg set`).
  - Bring interface up / down (ip link + wg).
"""

from __future__ import annotations

import base64
import ipaddress
import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from typing import Dict, List, Optional

from src.config import WG_CONFIG_PATH, WG_IFACE, WG_PORT, WG_SUBNET

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Keypair management
# ---------------------------------------------------------------------------

_KEY_DIR = "/opt/everywifi/data/keys"
_PRIVATE_KEY_FILE = os.path.join(_KEY_DIR, "wg_private.key")
_PUBLIC_KEY_FILE = os.path.join(_KEY_DIR, "wg_public.key")


def _wg(*args: str, stdin_data: Optional[str] = None) -> str:
    result = subprocess.run(
        ["wg"] + list(args),
        capture_output=True,
        text=True,
        input=stdin_data,
    )
    if result.returncode != 0:
        raise RuntimeError(f"wg {' '.join(args)} failed: {result.stderr.strip()}")
    return result.stdout.strip()


def _ip(*args: str) -> subprocess.CompletedProcess:
    cmd = ["ip"] + list(args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("ip %s: %s", " ".join(args), result.stderr.strip())
    return result


def load_or_generate_keypair() -> tuple[str, str]:
    """Return (private_key_base64, public_key_base64), generating if needed."""
    os.makedirs(_KEY_DIR, mode=0o700, exist_ok=True)
    if not os.path.exists(_PRIVATE_KEY_FILE):
        private_key = _wg("genkey")
        public_key = _wg("pubkey", stdin_data=private_key)
        with open(_PRIVATE_KEY_FILE, "w") as f:
            f.write(private_key)
        os.chmod(_PRIVATE_KEY_FILE, 0o600)
        with open(_PUBLIC_KEY_FILE, "w") as f:
            f.write(public_key)
        logger.info("WireGuard keypair generated")
    else:
        with open(_PRIVATE_KEY_FILE) as f:
            private_key = f.read().strip()
        with open(_PUBLIC_KEY_FILE) as f:
            public_key = f.read().strip()
    return private_key, public_key


# ---------------------------------------------------------------------------
# Peer dataclass
# ---------------------------------------------------------------------------

@dataclass
class WGPeer:
    public_key: str
    endpoint: str           # "ip:port"
    allowed_ips: str        # CIDR, e.g. "10.99.0.2/32"
    preshared_key: str = ""
    keepalive: int = 25


# ---------------------------------------------------------------------------
# WireGuard manager
# ---------------------------------------------------------------------------

class WireGuardManager:
    """
    Manages a single WireGuard interface (wg0 by default).
    """

    def __init__(
        self,
        iface: str = WG_IFACE,
        port: int = WG_PORT,
        address: str = "10.99.0.1/24",
        config_path: str = WG_CONFIG_PATH,
    ) -> None:
        self._iface = iface
        self._port = port
        self._address = address
        self._config_path = config_path
        self._private_key, self.public_key = load_or_generate_keypair()
        self._peers: Dict[str, WGPeer] = {}

    # ------------------------------------------------------------------
    # Interface lifecycle
    # ------------------------------------------------------------------

    def up(self) -> None:
        """Bring up the WireGuard interface, writing config first."""
        self._write_config()
        # Create interface if needed
        _ip("link", "add", self._iface, "type", "wireguard")
        _ip("address", "add", self._address, "dev", self._iface)
        try:
            _wg("setconf", self._iface, self._config_path)
        except RuntimeError as exc:
            logger.warning("wg setconf: %s", exc)
        _ip("link", "set", self._iface, "up")
        logger.info("WireGuard %s up (address %s)", self._iface, self._address)

    def down(self) -> None:
        """Take down the WireGuard interface."""
        _ip("link", "set", self._iface, "down")
        _ip("link", "del", self._iface)
        logger.info("WireGuard %s down", self._iface)

    # ------------------------------------------------------------------
    # Peer management
    # ------------------------------------------------------------------

    def add_peer(self, peer: WGPeer) -> None:
        """Add or update a peer."""
        self._peers[peer.public_key] = peer
        args = [
            "set", self._iface,
            "peer", peer.public_key,
            "allowed-ips", peer.allowed_ips,
            "persistent-keepalive", str(peer.keepalive),
        ]
        if peer.endpoint:
            args += ["endpoint", peer.endpoint]
        if peer.preshared_key:
            args += ["preshared-key", "/dev/stdin"]
            subprocess.run(
                ["wg"] + args,
                input=peer.preshared_key,
                text=True,
                capture_output=True,
            )
        else:
            try:
                _wg(*args)
            except RuntimeError as exc:
                logger.warning("add_peer: %s", exc)
        self._write_config()
        logger.info("WireGuard peer added: %s", peer.public_key[:12] + "...")

    def remove_peer(self, public_key: str) -> None:
        """Remove a peer."""
        self._peers.pop(public_key, None)
        try:
            _wg("set", self._iface, "peer", public_key, "remove")
        except RuntimeError as exc:
            logger.warning("remove_peer: %s", exc)
        self._write_config()

    def get_peers(self) -> List[WGPeer]:
        return list(self._peers.values())

    # ------------------------------------------------------------------
    # Config file
    # ------------------------------------------------------------------

    def _write_config(self) -> None:
        """Write wg0.conf from current state."""
        lines = [
            "[Interface]",
            f"PrivateKey = {self._private_key}",
            f"ListenPort = {self._port}",
            f"Address = {self._address}",
            "",
        ]
        for peer in self._peers.values():
            lines += [
                "[Peer]",
                f"PublicKey = {peer.public_key}",
                f"AllowedIPs = {peer.allowed_ips}",
            ]
            if peer.endpoint:
                lines.append(f"Endpoint = {peer.endpoint}")
            if peer.preshared_key:
                lines.append(f"PresharedKey = {peer.preshared_key}")
            if peer.keepalive:
                lines.append(f"PersistentKeepalive = {peer.keepalive}")
            lines.append("")

        os.makedirs(os.path.dirname(self._config_path), exist_ok=True)
        with open(self._config_path, "w") as f:
            f.write("\n".join(lines))
        os.chmod(self._config_path, 0o600)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def status(self) -> dict:
        try:
            output = _wg("show", self._iface)
        except (RuntimeError, FileNotFoundError):
            output = "(wg not available)"
        return {
            "interface": self._iface,
            "address": self._address,
            "public_key": self.public_key,
            "peer_count": len(self._peers),
            "wg_show": output,
        }
