"""
Distributed P2P Gossip Protocol (UDP).

Nodes gossip:
  - Ledger blocks (new send/receive blocks)
  - Location confirmations
  - Peer announcements

Message format (JSON, UTF-8):
{
  "msg_id": "<16-char hex>",   // unique message ID (anti-replay)
  "ttl": 5,                    // hops remaining
  "type": "block" | "location" | "peer",
  "payload": { ... }
}

Each node maintains a seen-messages cache to avoid re-broadcasting duplicates.
"""

from __future__ import annotations

import json
import logging
import os
import random
import secrets
import socket
import threading
import time
from typing import Callable, Dict, List, Optional, Set

from src.config import (
    BOOTSTRAP_PEERS,
    GOSSIP_FANOUT,
    GOSSIP_INTERVAL,
    GOSSIP_MSG_TTL,
    P2P_PORT,
)

logger = logging.getLogger(__name__)

MSG_TYPE_BLOCK = "block"
MSG_TYPE_LOCATION = "location"
MSG_TYPE_PEER = "peer"
MSG_TYPE_PING = "ping"

_SEEN_CACHE_SIZE = 10_000


class GossipNode:
    """
    UDP gossip node.

    Usage:
        node = GossipNode(bind_port=7777)
        node.on_message("block", handle_block)
        node.start()
        node.broadcast("block", {"hash": "...", ...})
    """

    def __init__(
        self,
        bind_host: str = "0.0.0.0",
        bind_port: int = P2P_PORT,
        node_id: Optional[str] = None,
    ) -> None:
        self._host = bind_host
        self._port = bind_port
        self._node_id = node_id or secrets.token_hex(8)
        self._peers: Dict[str, tuple[str, int]] = {}  # id → (host, port)
        self._seen: Set[str] = set()
        self._seen_order: List[str] = []
        self._handlers: Dict[str, List[Callable[[dict], None]]] = {}
        self._running = False
        self._sock: Optional[socket.socket] = None

        # Bootstrap from config
        for peer_str in BOOTSTRAP_PEERS:
            self._add_peer_str(peer_str)

    # ------------------------------------------------------------------
    # Peer management
    # ------------------------------------------------------------------

    def _add_peer_str(self, peer_str: str) -> None:
        try:
            host, port_s = peer_str.rsplit(":", 1)
            self._peers[peer_str] = (host, int(port_s))
        except ValueError:
            logger.warning("gossip: invalid peer string %r", peer_str)

    def add_peer(self, host: str, port: int, peer_id: str = "") -> None:
        key = peer_id or f"{host}:{port}"
        self._peers[key] = (host, port)

    def remove_peer(self, peer_id: str) -> None:
        self._peers.pop(peer_id, None)

    def get_peers(self) -> List[str]:
        return list(self._peers.keys())

    # ------------------------------------------------------------------
    # Message handlers
    # ------------------------------------------------------------------

    def on_message(self, msg_type: str, cb: Callable[[dict], None]) -> None:
        self._handlers.setdefault(msg_type, []).append(cb)

    # ------------------------------------------------------------------
    # Broadcast
    # ------------------------------------------------------------------

    def broadcast(self, msg_type: str, payload: dict) -> None:
        """Broadcast a new message to GOSSIP_FANOUT random peers."""
        msg = {
            "msg_id": secrets.token_hex(8),
            "ttl": GOSSIP_MSG_TTL,
            "from": self._node_id,
            "type": msg_type,
            "payload": payload,
        }
        self._mark_seen(msg["msg_id"])
        self._send_to_peers(msg)

    def _send_to_peers(self, msg: dict) -> None:
        if not self._peers or not self._sock:
            return
        peers = list(self._peers.values())
        targets = random.sample(peers, min(GOSSIP_FANOUT, len(peers)))
        data = json.dumps(msg).encode()
        for host, port in targets:
            try:
                self._sock.sendto(data, (host, port))
            except OSError as exc:
                logger.debug("gossip: send to %s:%d failed: %s", host, port, exc)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._sock.bind((self._host, self._port))
        self._sock.settimeout(1.0)
        self._running = True
        rx_thread = threading.Thread(target=self._rx_loop, daemon=True)
        rx_thread.start()
        ping_thread = threading.Thread(target=self._ping_loop, daemon=True)
        ping_thread.start()
        logger.info(
            "Gossip node %s listening on %s:%d",
            self._node_id,
            self._host,
            self._port,
        )

    def stop(self) -> None:
        self._running = False
        if self._sock:
            self._sock.close()

    # ------------------------------------------------------------------
    # RX loop
    # ------------------------------------------------------------------

    def _rx_loop(self) -> None:
        while self._running:
            try:
                data, addr = self._sock.recvfrom(65535)
            except socket.timeout:
                continue
            except OSError:
                break
            try:
                msg = json.loads(data.decode())
                self._handle_message(msg, addr)
            except Exception as exc:
                logger.debug("gossip: bad message from %s: %s", addr, exc)

    def _handle_message(self, msg: dict, addr: tuple) -> None:
        msg_id = msg.get("msg_id", "")
        if not msg_id or msg_id in self._seen:
            return
        self._mark_seen(msg_id)

        # Learn peer
        from_id = msg.get("from", f"{addr[0]}:{addr[1]}")
        self._peers[from_id] = addr

        # Dispatch to handlers
        msg_type = msg.get("type", "")
        for cb in self._handlers.get(msg_type, []):
            try:
                cb(msg.get("payload", {}))
            except Exception as exc:
                logger.error("gossip handler error: %s", exc)

        # Re-gossip if TTL > 0
        ttl = msg.get("ttl", 0)
        if ttl > 0:
            msg["ttl"] = ttl - 1
            self._send_to_peers(msg)

    # ------------------------------------------------------------------
    # Ping loop (keep-alive + peer discovery)
    # ------------------------------------------------------------------

    def _ping_loop(self) -> None:
        while self._running:
            time.sleep(GOSSIP_INTERVAL)
            self.broadcast(MSG_TYPE_PING, {
                "node_id": self._node_id,
                "port": self._port,
            })

    # ------------------------------------------------------------------
    # Seen-messages cache
    # ------------------------------------------------------------------

    def _mark_seen(self, msg_id: str) -> None:
        if msg_id in self._seen:
            return
        self._seen.add(msg_id)
        self._seen_order.append(msg_id)
        if len(self._seen_order) > _SEEN_CACHE_SIZE:
            old = self._seen_order.pop(0)
            self._seen.discard(old)
