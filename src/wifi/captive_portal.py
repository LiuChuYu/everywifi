"""
Captive portal HTTP server (asyncio).

Unauthenticated WiFi clients are redirected here by nftables DNAT.
They see a landing page where they can choose:
  - Free 1 Mbps tier (no payment required)
  - Paid high-speed tier (pay EWF tokens)

After authentication the client's MAC is added to the nftables 'allowed'
set and tc bandwidth class is raised.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import ipaddress
import json
import logging
import os
import re
import time
from http.server import BaseHTTPRequestHandler
from typing import Dict, Optional
from urllib.parse import parse_qs, quote, urlparse

from src.config import (
    CAPTIVE_PORTAL_HOST,
    CAPTIVE_PORTAL_PORT,
    FREE_RATE_KBPS,
    SESSION_TIMEOUT_SECONDS,
)
from src.wifi.bandwidth import BandwidthManager
from src.wifi.auth import AuthManager

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# MAC sanitizer (prevents HTTP header injection / response splitting)
# ---------------------------------------------------------------------------
_MAC_RE = re.compile(r'^([0-9a-f]{2}:){5}[0-9a-f]{2}$')
_IP_FALLBACK_RE = re.compile(r'^ip_[\d.]+$')


def _sanitize_mac(mac: str) -> str:
    """Return *mac* only if it matches the expected format; otherwise empty."""
    mac = mac.lower().strip()
    if _MAC_RE.match(mac) or _IP_FALLBACK_RE.match(mac):
        return mac
    return ""


# ---------------------------------------------------------------------------
# HTML pages (minimal, works without JS for embedded devices)
# ---------------------------------------------------------------------------
_PAGE_LANDING = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>EveryWifi 歡迎 Welcome</title>
  <style>
    body{{font-family:sans-serif;max-width:480px;margin:40px auto;padding:0 16px}}
    h1{{color:#2563eb}}
    .btn{{display:block;width:100%;padding:12px;margin:8px 0;
         font-size:1rem;border:none;border-radius:6px;cursor:pointer}}
    .free{{background:#22c55e;color:#fff}}
    .paid{{background:#2563eb;color:#fff}}
    .info{{font-size:.85rem;color:#6b7280;margin-top:24px}}
  </style>
</head>
<body>
  <h1>EveryWifi</h1>
  <p>請選擇連線方案 / Choose your plan:</p>
  <form method="POST" action="/connect">
    <input type="hidden" name="mac" value="{mac}">
    <button class="btn free" name="plan" value="free">
      免費 1 Mbps Free
    </button>
    <button class="btn paid" name="plan" value="paid">
      高速付費 High Speed (需支付 EWF 代幣)
    </button>
  </form>
  <div class="info">
    <p>免費方案：下行 1 Mbps，無需帳號</p>
    <p>付費方案：每 1 EWF = 10 MB 高速流量</p>
    <p>節點地址 Node Address：<code>{node_addr}</code></p>
  </div>
</body>
</html>
"""

_PAGE_SUCCESS_FREE = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><title>EveryWifi 已連線</title></head>
<body>
  <h2>✅ 免費連線已啟用 Free tier activated</h2>
  <p>您目前享有 1 Mbps 下行速度。</p>
  <p>如需升速，請訪問 <a href="/pay">付費頁面</a>。</p>
</body>
</html>
"""

_PAGE_PAY = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><title>EveryWifi 付費</title></head>
<body>
  <h2>付費升速 Pay for High Speed</h2>
  <p>請將 EWF 代幣傳送至以下地址，並在下方輸入交易 hash：</p>
  <p><strong>{node_addr}</strong></p>
  <p>1 EWF = 10 MB 高速流量</p>
  <form method="POST" action="/pay_confirm">
    <input type="hidden" name="mac" value="{mac}">
    <label>交易 Hash / Block Hash:
      <input type="text" name="tx_hash" required style="width:100%">
    </label>
    <button type="submit" style="margin-top:8px;padding:8px 16px">確認付款</button>
  </form>
</body>
</html>
"""

_PAGE_PAID_OK = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><title>EveryWifi 付款成功</title></head>
<body>
  <h2>✅ 付款成功 Payment confirmed</h2>
  <p>已升至高速方案。剩餘流量：{remaining_mb:.1f} MB</p>
</body>
</html>
"""

_PAGE_ERROR = """\
<!DOCTYPE html>
<html lang="zh-TW">
<head><meta charset="UTF-8"><title>EveryWifi 錯誤</title></head>
<body>
  <h2>⚠️ 錯誤 Error</h2>
  <p>{message}</p>
  <a href="/">返回首頁</a>
</body>
</html>
"""


# ---------------------------------------------------------------------------
# HTTP request handler
# ---------------------------------------------------------------------------

class _PortalHandler(BaseHTTPRequestHandler):
    """Minimal sync HTTP handler; replaced by asyncio in production."""

    auth_manager: AuthManager
    bw_manager: BandwidthManager
    node_address: str

    def log_message(self, fmt: str, *args) -> None:  # suppress default logging
        logger.debug("portal: " + fmt, *args)

    def _send_html(self, code: int, body: str) -> None:
        encoded = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _get_client_mac(self) -> str:
        """Resolve client IP → MAC via /proc/net/arp."""
        ip = self.client_address[0]
        try:
            with open("/proc/net/arp") as f:
                for line in f:
                    parts = line.split()
                    if len(parts) >= 4 and parts[0] == ip:
                        return parts[3].lower()
        except OSError:
            pass
        # Fallback: use IP as identifier (testing / non-Linux)
        return f"ip_{ip}"

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        mac = self._get_client_mac()

        if path in ("/", "/generate_204", "/hotspot-detect.html",
                    "/connecttest.txt", "/ncsi.txt"):
            # Redirect to captive portal landing (iOS/Android/Windows detection)
            if path != "/":
                self.send_response(302)
                self.send_header("Location", "/")
                self.end_headers()
                return
            self._send_html(
                200,
                _PAGE_LANDING.format(
                    mac=html.escape(mac),
                    node_addr=html.escape(self.node_address),
                ),
            )
        elif path == "/pay":
            self._send_html(
                200,
                _PAGE_PAY.format(
                    mac=html.escape(mac),
                    node_addr=html.escape(self.node_address),
                ),
            )
        else:
            self._send_html(404, "<h2>404 Not Found</h2>")

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length).decode(errors="replace")
        params = parse_qs(body)
        path = urlparse(self.path).path
        raw_mac = params.get("mac", [""])[0] or self._get_client_mac()
        mac = _sanitize_mac(raw_mac)

        if path == "/connect":
            plan = params.get("plan", ["free"])[0]
            if plan == "free":
                self.auth_manager.add_free(mac)
                self.bw_manager.set_rate(mac, FREE_RATE_KBPS)
                self._send_html(200, _PAGE_SUCCESS_FREE)
            elif plan == "paid":
                self.send_response(302)
                # Use quote() to percent-encode the MAC for safe header value
                self.send_header(
                    "Location", f"/pay?mac={quote(mac, safe='')}"
                )
                self.end_headers()
            else:
                self._send_html(
                    400, _PAGE_ERROR.format(message="Unknown plan.")
                )

        elif path == "/pay_confirm":
            tx_hash = params.get("tx_hash", [""])[0].strip()
            if not tx_hash:
                self._send_html(
                    400, _PAGE_ERROR.format(message="Missing transaction hash.")
                )
                return
            result = self.auth_manager.confirm_payment(mac, tx_hash)
            if result is None:
                self._send_html(
                    400,
                    _PAGE_ERROR.format(
                        message="Transaction not found or already used."
                    ),
                )
            else:
                remaining_mb = result / (1024 * 1024)
                self._send_html(
                    200,
                    _PAGE_PAID_OK.format(remaining_mb=remaining_mb),
                )
        else:
            self._send_html(404, "<h2>404 Not Found</h2>")


# ---------------------------------------------------------------------------
# Server lifecycle
# ---------------------------------------------------------------------------

class CaptivePortal:
    """Thin wrapper that starts the portal HTTP server in a thread."""

    def __init__(
        self,
        auth_manager: AuthManager,
        bw_manager: BandwidthManager,
        node_address: str,
        host: str = CAPTIVE_PORTAL_HOST,
        port: int = CAPTIVE_PORTAL_PORT,
    ) -> None:
        self._host = host
        self._port = port
        # Inject dependencies into handler class (single-process, no multithread issues)
        _PortalHandler.auth_manager = auth_manager
        _PortalHandler.bw_manager = bw_manager
        _PortalHandler.node_address = node_address
        self._server: Optional[object] = None

    def start(self) -> None:
        import threading
        from http.server import HTTPServer

        self._server = HTTPServer((self._host, self._port), _PortalHandler)
        t = threading.Thread(target=self._server.serve_forever, daemon=True)
        t.start()
        logger.info("Captive portal listening on %s:%d", self._host, self._port)

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
