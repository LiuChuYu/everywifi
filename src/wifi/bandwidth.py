"""
Bandwidth management via Linux tc (Traffic Control).

Uses HTB (Hierarchical Token Bucket) qdisc to limit per-client bandwidth
based on their payment status.

Free tier  : 1 Mbps down / 512 Kbps up
Paid tier  : dynamically set based on purchased quota

tc class hierarchy (on LAN interface, e.g. br-lan):
  1:0  root htb default 9999
  1:1  htb rate=<WAN_rate>
    1:10   htb rate=<free_rate>   ceil=<free_rate>    # free clients
    1:20   htb rate=<paid_rate>   ceil=<WAN_rate>     # paid clients
    1:9999 htb rate=64kbps                            # default (unauthenticated)
  u32 filter : src MAC → class

On an embedded OpenWRT device this calls subprocess.run(['tc', ...]).
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Dict, Optional

from src.config import FREE_RATE_KBPS, DEFAULT_PAID_RATE_KBPS, LAN_IFACE

logger = logging.getLogger(__name__)

_MAJOR = "1"          # qdisc/class major number
_FREE_CLASS = "10"    # minor for free tier
_PAID_CLASS = "20"    # minor for paid tier
_DEFAULT_CLASS = "9999"

# Mapping: MAC address → tc class minor number (for cleanup)
_mac_class: Dict[str, str] = {}
# Next available dynamic class minor (for per-client paid classes)
_next_class_minor = 100


def _tc(*args: str, check: bool = False) -> subprocess.CompletedProcess:
    """Run a tc command, logging errors."""
    cmd = ["tc"] + list(args)
    logger.debug("tc %s", " ".join(args))
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning("tc error: %s", result.stderr.strip())
    if check:
        result.check_returncode()
    return result


def _mac_to_hex(mac: str) -> str:
    """Convert colon-separated MAC to hex string for u32 filter."""
    return "0x" + mac.replace(":", "")


def setup_qdisc(iface: str = LAN_IFACE, wan_rate_kbps: int = 100_000) -> None:
    """
    Create the root HTB qdisc and base classes on *iface*.
    Safe to call at startup; existing qdiscs are replaced.
    """
    # Remove existing root qdisc
    _tc("qdisc", "del", "dev", iface, "root")
    # Add root HTB with default class for unauthenticated
    _tc("qdisc", "add", "dev", iface, "root", "handle", f"{_MAJOR}:", "htb",
        "default", _DEFAULT_CLASS, check=True)
    # Top-level class at WAN rate
    _tc("class", "add", "dev", iface, "parent", f"{_MAJOR}:", "classid",
        f"{_MAJOR}:1", "htb", "rate", f"{wan_rate_kbps}kbit", check=True)
    # Free tier class
    _tc("class", "add", "dev", iface, "parent", f"{_MAJOR}:1", "classid",
        f"{_MAJOR}:{_FREE_CLASS}", "htb",
        "rate", f"{FREE_RATE_KBPS}kbit",
        "ceil", f"{FREE_RATE_KBPS}kbit", check=True)
    # Paid tier base class
    _tc("class", "add", "dev", iface, "parent", f"{_MAJOR}:1", "classid",
        f"{_MAJOR}:{_PAID_CLASS}", "htb",
        "rate", f"{DEFAULT_PAID_RATE_KBPS}kbit",
        "ceil", f"{wan_rate_kbps}kbit", check=True)
    # Default (unauthenticated) class — very low rate
    _tc("class", "add", "dev", iface, "parent", f"{_MAJOR}:1", "classid",
        f"{_MAJOR}:{_DEFAULT_CLASS}", "htb",
        "rate", "64kbit", "ceil", "64kbit", check=True)
    logger.info("tc HTB qdisc set up on %s (WAN %d kbps)", iface, wan_rate_kbps)


def set_rate(
    mac: str,
    rate_kbps: int,
    iface: str = LAN_IFACE,
) -> bool:
    """
    Assign (or update) a tc class for *mac* on *iface*.

    rate_kbps == FREE_RATE_KBPS → put in shared free class
    rate_kbps  > FREE_RATE_KBPS → create/update per-client paid class
    """
    global _next_class_minor
    mac = mac.lower()

    if rate_kbps <= FREE_RATE_KBPS:
        class_minor = _FREE_CLASS
    else:
        # Create or reuse a per-client class
        if mac in _mac_class:
            class_minor = _mac_class[mac]
            _tc("class", "change", "dev", iface, "parent", f"{_MAJOR}:{_PAID_CLASS}",
                "classid", f"{_MAJOR}:{class_minor}", "htb",
                "rate", f"{rate_kbps}kbit", "ceil", f"{rate_kbps}kbit")
        else:
            class_minor = str(_next_class_minor)
            _next_class_minor += 1
            _tc("class", "add", "dev", iface, "parent", f"{_MAJOR}:{_PAID_CLASS}",
                "classid", f"{_MAJOR}:{class_minor}", "htb",
                "rate", f"{rate_kbps}kbit", "ceil", f"{rate_kbps}kbit")

    _mac_class[mac] = class_minor
    # Add/replace u32 filter matching source MAC → class
    # tc u32 filter on MAC: match at offset 8 (eth src MAC bytes 0-3) and 12 (bytes 4-5)
    mac_bytes = mac.replace(":", "")
    mac_hi = "0x" + mac_bytes[:8]
    mac_lo = "0x" + mac_bytes[8:].ljust(8, "0")
    # Delete existing filter for this MAC if any
    remove_filter(mac, iface)
    result = _tc("filter", "add", "dev", iface, "parent", f"{_MAJOR}:",
                 "protocol", "ip", "prio", "1", "u32",
                 "match", "u32", mac_hi, "0xffffffff", "at", "-14",
                 "match", "u16", "0x" + mac_bytes[8:12], "0xffff", "at", "-10",
                 "flowid", f"{_MAJOR}:{class_minor}")
    if result.returncode != 0:
        logger.warning("set_rate: filter add failed for MAC %s", mac)
        return False
    logger.info("set_rate: MAC %s → %d kbps (class %s)", mac, rate_kbps, class_minor)
    return True


def remove_filter(mac: str, iface: str = LAN_IFACE) -> None:
    """Remove tc u32 filter for *mac* from *iface* (best-effort)."""
    mac = mac.lower()
    # List filters and find handle for this MAC
    result = _tc("filter", "show", "dev", iface, "parent", f"{_MAJOR}:")
    handles = re.findall(r"filter .*?fh (\S+).*?" + mac.replace(":", ":"), result.stdout)
    for handle in handles:
        _tc("filter", "del", "dev", iface, "parent", f"{_MAJOR}:", "handle", handle,
            "prio", "1", "protocol", "ip", "u32")


class BandwidthManager:
    """High-level per-client bandwidth control."""

    def __init__(self, iface: str = LAN_IFACE) -> None:
        self._iface = iface

    def setup(self, wan_rate_kbps: int = 100_000) -> None:
        setup_qdisc(self._iface, wan_rate_kbps)

    def set_free(self, mac: str) -> None:
        set_rate(mac, FREE_RATE_KBPS, self._iface)

    def set_rate(self, mac: str, rate_kbps: int) -> None:
        set_rate(mac, rate_kbps, self._iface)

    def remove(self, mac: str) -> None:
        remove_filter(mac, self._iface)
        _mac_class.pop(mac.lower(), None)
