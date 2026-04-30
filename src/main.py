"""
EveryWifi main entry point — orchestrates all subsystems.

Start order:
  1. Ledger (SQLite)
  2. WireGuard VPN
  3. P2P Gossip
  4. LoRa Gateway + Location Verifier
  5. WiFi Auth Manager + Bandwidth Manager
  6. Captive Portal HTTP server
  7. REST API server
  8. Main event loop
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
import sys
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Optional
from urllib.parse import urlparse

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("everywifi.main")

# ---------------------------------------------------------------------------
# Imports (deferred after logging)
# ---------------------------------------------------------------------------
from src.config import (
    API_HOST,
    API_PORT,
    CAPTIVE_PORTAL_HOST,
    CAPTIVE_PORTAL_PORT,
    DEFAULT_PAID_RATE_KBPS,
    FREE_RATE_KBPS,
    GOSSIP_INTERVAL,
    LORA_DEVICE,
    REWARD_PER_LOCATION_RAW,
    WG_IFACE,
)
from src.ledger.ledger import Ledger, generate_account, GENESIS_ACCOUNT
from src.wifi.auth import AuthManager
from src.wifi.bandwidth import BandwidthManager
from src.wifi.captive_portal import CaptivePortal
from src.lora.lora_gateway import LoRaGateway
from src.lora.location import LocationVerifier, save_position
from src.vpn.wireguard import WireGuardManager
from src.p2p.gossip import GossipNode, MSG_TYPE_BLOCK, MSG_TYPE_LOCATION, MSG_TYPE_PEER

# ---------------------------------------------------------------------------
# Node identity
# ---------------------------------------------------------------------------
_NODE_KEY_FILE = "/opt/everywifi/data/node_identity.json"


def load_or_create_identity() -> dict:
    os.makedirs(os.path.dirname(_NODE_KEY_FILE), exist_ok=True)
    if os.path.exists(_NODE_KEY_FILE):
        with open(_NODE_KEY_FILE) as f:
            return json.load(f)
    private_key, address = generate_account()
    identity = {"private_key": private_key, "address": address}
    with open(_NODE_KEY_FILE, "w") as f:
        json.dump(identity, f)
    os.chmod(_NODE_KEY_FILE, 0o600)
    logger.info("New node identity created: %s", address)
    return identity


def load_or_create_genesis_key() -> str:
    """Load genesis private key (create one-time if not present)."""
    genesis_key_file = "/opt/everywifi/data/genesis.key"
    if os.path.exists(genesis_key_file):
        with open(genesis_key_file) as f:
            return f.read().strip()
    private_key, _ = generate_account()
    with open(genesis_key_file, "w") as f:
        f.write(private_key)
    os.chmod(genesis_key_file, 0o600)
    return private_key


# ---------------------------------------------------------------------------
# Simple REST API handler
# ---------------------------------------------------------------------------

class _APIHandler(BaseHTTPRequestHandler):
    node: "EveryWifiNode"

    def log_message(self, fmt, *args):
        logger.debug("api: " + fmt, *args)

    def _send_json(self, code: int, data: dict) -> None:
        body = json.dumps(data, indent=2).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        n = self.node

        if path == "/api/status":
            self._send_json(200, n.get_status())
        elif path.startswith("/api/account/"):
            addr = path[len("/api/account/"):]
            balance = n.ledger.get_balance(addr)
            chain = n.ledger.account_chain(addr, count=5)
            pending = n.ledger.pending_for(addr)
            self._send_json(200, {
                "address": addr,
                "balance_raw": balance,
                "balance_ewf": balance / (10 ** 30),
                "chain": chain,
                "pending": pending,
            })
        elif path == "/api/wifi/clients":
            self._send_json(200, {"clients": n.auth.get_sessions()})
        elif path == "/api/lora/peers":
            self._send_json(200, {"peers": n.gossip.get_peers()})
        else:
            self._send_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/")
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        n = self.node

        if path == "/api/pay":
            address = body.get("address", "")
            amount_ewf = float(body.get("amount_ewf", 0))
            if not address or amount_ewf <= 0:
                self._send_json(400, {"error": "address and amount_ewf required"})
                return
            amount_raw = int(amount_ewf * 10 ** 30)
            block = n.ledger.send(
                n.identity["address"],
                address,
                amount_raw,
                n.identity["private_key"],
            )
            if block:
                self._send_json(200, {"hash": block.hash})
            else:
                self._send_json(400, {"error": "insufficient balance or invalid"})
        else:
            self._send_json(404, {"error": "not found"})


# ---------------------------------------------------------------------------
# Main node class
# ---------------------------------------------------------------------------

class EveryWifiNode:
    def __init__(self) -> None:
        self.identity = load_or_create_identity()
        self._genesis_key = load_or_create_genesis_key()

        # Core subsystems
        self.ledger = Ledger()
        self.auth = AuthManager(ledger=self.ledger)
        self.bw = BandwidthManager()
        self.portal = CaptivePortal(
            auth_manager=self.auth,
            bw_manager=self.bw,
            node_address=self.identity["address"],
        )
        self.vpn = WireGuardManager()
        self.gossip = GossipNode()
        self.lora_gw = LoRaGateway(
            dev_eui=self.identity["address"][:16],
            device=LORA_DEVICE,
            simulated=not os.path.exists(LORA_DEVICE),
        )
        self.locator = LocationVerifier(
            gateway=self.lora_gw,
            dev_eui=self.identity["address"][:16],
        )

    def start(self) -> None:
        logger.info("EveryWifi node starting (address: %s)", self.identity["address"])

        # 1. Ledger: ensure genesis account exists
        self.ledger.create_account(
            GENESIS_ACCOUNT,
            public_key="0" * 64,
        )

        # 2. VPN
        try:
            self.vpn.up()
        except Exception as exc:
            logger.warning("VPN start failed (OK on dev): %s", exc)

        # 3. Gossip P2P
        self.gossip.on_message(MSG_TYPE_BLOCK, self._on_gossip_block)
        self.gossip.on_message(MSG_TYPE_LOCATION, self._on_gossip_location)
        self.gossip.start()

        # 4. LoRa
        self.locator.on_verified(self._on_location_verified)
        self.lora_gw.start()

        # 5. WiFi bandwidth setup
        try:
            self.bw.setup()
        except Exception as exc:
            logger.warning("tc setup failed (OK on dev): %s", exc)

        # 6. Captive portal
        self.portal.start()

        # 7. REST API
        self._start_api()

        # 8. Main loop
        logger.info("EveryWifi node ready")
        self._main_loop()

    def _main_loop(self) -> None:
        while True:
            try:
                self.auth.tick()
                self.locator.tick()
                # Broadcast own position periodically
                self.locator.broadcast_own_position()
                time.sleep(GOSSIP_INTERVAL)
            except KeyboardInterrupt:
                break
        self.stop()

    def stop(self) -> None:
        logger.info("EveryWifi node stopping")
        self.lora_gw.stop()
        self.gossip.stop()
        try:
            self.vpn.down()
        except Exception:
            pass
        self.ledger.close()

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_location_verified(self, dev_eui: str, lat: float, lon: float) -> None:
        """Called when a LoRa location is verified — issue token reward."""
        logger.info("Location verified: DevEUI=%s lat=%.4f lon=%.4f", dev_eui, lat, lon)
        # Map DevEUI → node account address (simplified: use DevEUI as prefix)
        dest_address = dev_eui  # In production resolve via peer registry
        success = self.ledger.reward_location(
            dest_address,
            self._genesis_key,
            REWARD_PER_LOCATION_RAW,
        )
        if success:
            logger.info("Rewarded %s with %d raw EWF", dest_address, REWARD_PER_LOCATION_RAW)
            # Gossip the reward block
            self.gossip.broadcast(MSG_TYPE_LOCATION, {
                "dev_eui": dev_eui,
                "lat": lat,
                "lon": lon,
                "reward_raw": REWARD_PER_LOCATION_RAW,
            })

    def _on_gossip_block(self, payload: dict) -> None:
        """Process an incoming block from a gossip peer."""
        from src.ledger.ledger import Block
        try:
            block = Block.from_dict(payload)
            self.ledger.process_block(block)
        except Exception as exc:
            logger.debug("gossip block error: %s", exc)

    def _on_gossip_location(self, payload: dict) -> None:
        logger.debug("gossip location: %s", payload)

    # ------------------------------------------------------------------
    # API server
    # ------------------------------------------------------------------

    def _start_api(self) -> None:
        _APIHandler.node = self
        server = HTTPServer((API_HOST, API_PORT), _APIHandler)
        t = Thread(target=server.serve_forever, daemon=True)
        t.start()
        logger.info("REST API listening on %s:%d", API_HOST, API_PORT)

    # ------------------------------------------------------------------
    # Status
    # ------------------------------------------------------------------

    def get_status(self) -> dict:
        return {
            "address": self.identity["address"],
            "balance_raw": self.ledger.get_balance(self.identity["address"]),
            "vpn": self.vpn.status(),
            "gossip_peers": self.gossip.get_peers(),
            "wifi_clients": len(self.auth.get_sessions()),
        }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    node = EveryWifiNode()
    signal.signal(signal.SIGTERM, lambda *_: node.stop())
    node.start()


if __name__ == "__main__":
    main()
