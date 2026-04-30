"""
LoRa-based physical location verification.

Algorithm:
  1. This node receives a LocationBeacon from a neighbour.
  2. It checks RSSI plausibility (within RSSI_TOLERANCE_DBM of expected
     free-space path loss for the stated lat/lon distance).
  3. If plausible, it sends a LocationConfirm back to the sender.
  4. It tracks how many confirmations a given beacon has collected.
  5. Once MIN_LOCATION_CONFIRMATIONS is reached, it emits a
     'location_verified' event (used by main.py to reward tokens).

Optional GPS support:
  - If gpsd is running, we use real GPS coordinates.
  - If not, we use the last known position from a config file.
"""

from __future__ import annotations

import json
import logging
import math
import os
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional, Tuple

from src.config import (
    MIN_LOCATION_CONFIRMATIONS,
    RSSI_TOLERANCE_DBM,
)
from src.lora.lora_gateway import LocationBeacon, LoRaGateway

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# GPS helper
# ---------------------------------------------------------------------------

_GPS_CACHE_FILE = "/opt/everywifi/data/last_position.json"


def get_gps_position() -> Optional[Tuple[float, float, float]]:
    """
    Return (lat, lon, altitude) from gpsd, or from cache file.
    Returns None if no position available.
    """
    # Try gpsd first
    try:
        import socket
        s = socket.socket()
        s.settimeout(2)
        s.connect(("127.0.0.1", 2947))
        s.sendall(b'?WATCH={"enable":true,"json":true}\n')
        data = b""
        deadline = time.time() + 3
        while time.time() < deadline:
            chunk = s.recv(4096)
            if not chunk:
                break
            data += chunk
            for line in data.split(b"\n"):
                try:
                    obj = json.loads(line)
                    if obj.get("class") == "TPV" and "lat" in obj:
                        s.close()
                        return obj["lat"], obj["lon"], obj.get("alt", 0.0)
                except json.JSONDecodeError:
                    pass
        s.close()
    except Exception:
        pass

    # Fall back to cache
    if os.path.exists(_GPS_CACHE_FILE):
        try:
            with open(_GPS_CACHE_FILE) as f:
                d = json.load(f)
                return d["lat"], d["lon"], d.get("alt", 0.0)
        except Exception:
            pass
    return None


def save_position(lat: float, lon: float, alt: float = 0.0) -> None:
    os.makedirs(os.path.dirname(_GPS_CACHE_FILE), exist_ok=True)
    with open(_GPS_CACHE_FILE, "w") as f:
        json.dump({"lat": lat, "lon": lon, "alt": alt, "ts": time.time()}, f)


# ---------------------------------------------------------------------------
# Free-space path loss (FSPL) model for RSSI plausibility check
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Return distance in metres between two lat/lon points."""
    R = 6_371_000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


def fspl_dbm(distance_m: float, freq_mhz: float, tx_power_dbm: float = 14.0) -> float:
    """Estimated received power (dBm) via free-space path loss."""
    if distance_m < 1:
        distance_m = 1
    fspl = 20 * math.log10(distance_m) + 20 * math.log10(freq_mhz) + 32.44
    return tx_power_dbm - fspl


# ---------------------------------------------------------------------------
# Pending beacon tracker
# ---------------------------------------------------------------------------

@dataclass
class _PendingBeacon:
    beacon: LocationBeacon
    confirmations: List[dict] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)

    @property
    def confirmation_count(self) -> int:
        return len(self.confirmations)


# ---------------------------------------------------------------------------
# LocationVerifier
# ---------------------------------------------------------------------------

class LocationVerifier:
    """
    Receives LoRa beacons and confirms / tracks location verification.

    On receiving a beacon:
      1. Checks RSSI plausibility.
      2. Sends a confirm via the gateway.

    On receiving a confirm:
      1. Adds it to the pending beacon tracker.
      2. If threshold met, calls 'on_verified' callbacks.
    """

    def __init__(
        self,
        gateway: LoRaGateway,
        dev_eui: str,
        freq_mhz: float = 868.1,
    ) -> None:
        self._gw = gateway
        self._dev_eui = dev_eui
        self._freq_mhz = freq_mhz
        self._pending: Dict[str, _PendingBeacon] = {}  # key: dev_eui:seq
        self._verified_callbacks: List[Callable[[str, float, float], None]] = []

        gateway.on_beacon(self._handle_beacon)
        gateway.on_confirm(self._handle_confirm)

    def on_verified(self, cb: Callable[[str, float, float], None]) -> None:
        """Register callback(dev_eui, lat, lon) called when location verified."""
        self._verified_callbacks.append(cb)

    # ------------------------------------------------------------------
    # Beacon handler (run in gateway RX thread)
    # ------------------------------------------------------------------

    def _handle_beacon(self, beacon: LocationBeacon) -> None:
        if beacon.dev_eui == self._dev_eui:
            return  # ignore own beacons

        plausible = self._check_rssi_plausibility(beacon)
        if not plausible:
            logger.debug(
                "location: beacon from %s rejected (RSSI %.1f dBm implausible)",
                beacon.dev_eui,
                beacon.rssi,
            )
            return

        key = f"{beacon.dev_eui}:{beacon.seq}"
        if key not in self._pending:
            self._pending[key] = _PendingBeacon(beacon)

        # Send confirmation
        self._gw.send_confirm(
            target_eui=beacon.dev_eui,
            target_seq=beacon.seq,
            rssi=beacon.rssi,
        )
        logger.debug(
            "location: confirmed beacon from %s (RSSI %.1f dBm)",
            beacon.dev_eui,
            beacon.rssi,
        )

    # ------------------------------------------------------------------
    # Confirm handler (run in gateway RX thread)
    # ------------------------------------------------------------------

    def _handle_confirm(self, confirm: dict) -> None:
        # Find the matching pending beacon for THIS node's beacon
        # (confirms targeted at us)
        target_eui = confirm.get("target_dev_eui", "")
        if target_eui != self._dev_eui:
            # Forward-track: store confirm for others' beacons
            key = f"{target_eui}:{confirm.get('target_seq', 0)}"
            if key in self._pending:
                self._pending[key].confirmations.append(confirm)
                self._check_threshold(key)
            return

        # This is a confirmation of our own beacon
        key = f"{self._dev_eui}:{confirm.get('target_seq', 0)}"
        if key not in self._pending:
            # Create pending entry for our own beacon (no beacon object needed here)
            own_pos = get_gps_position() or (0.0, 0.0, 0.0)
            dummy_beacon = LocationBeacon(
                dev_eui=self._dev_eui,
                lat=own_pos[0],
                lon=own_pos[1],
                altitude=own_pos[2],
                rssi=0.0,
                seq=confirm.get("target_seq", 0),
                timestamp=time.time(),
            )
            self._pending[key] = _PendingBeacon(dummy_beacon)
        self._pending[key].confirmations.append(confirm)
        self._check_threshold(key)

    def _check_threshold(self, key: str) -> None:
        entry = self._pending.get(key)
        if entry and entry.confirmation_count >= MIN_LOCATION_CONFIRMATIONS:
            beacon = entry.beacon
            for cb in self._verified_callbacks:
                try:
                    cb(beacon.dev_eui, beacon.lat, beacon.lon)
                except Exception as exc:
                    logger.error("verified callback error: %s", exc)
            del self._pending[key]
            logger.info(
                "location: verified! DevEUI=%s lat=%.4f lon=%.4f (%d confirms)",
                beacon.dev_eui,
                beacon.lat,
                beacon.lon,
                entry.confirmation_count,
            )

    # ------------------------------------------------------------------
    # RSSI plausibility
    # ------------------------------------------------------------------

    def _check_rssi_plausibility(self, beacon: LocationBeacon) -> bool:
        """
        Return True if the received RSSI is plausibly within tolerance
        of what free-space path loss would predict given the stated distance.
        """
        own_pos = get_gps_position()
        if own_pos is None:
            # No own position — accept all beacons conservatively
            return True
        dist_m = haversine_m(own_pos[0], own_pos[1], beacon.lat, beacon.lon)
        expected_rssi = fspl_dbm(dist_m, self._freq_mhz)
        diff = abs(beacon.rssi - expected_rssi)
        return diff <= RSSI_TOLERANCE_DBM

    # ------------------------------------------------------------------
    # Periodic: prune stale pending beacons, broadcast own position
    # ------------------------------------------------------------------

    def tick(self, max_age_s: float = 60.0) -> None:
        """Call every few seconds to clean up and re-broadcast own beacon."""
        now = time.time()
        stale = [k for k, v in self._pending.items() if now - v.created_at > max_age_s]
        for k in stale:
            del self._pending[k]

    def broadcast_own_position(self) -> None:
        pos = get_gps_position()
        if pos:
            self._gw.broadcast_beacon(lat=pos[0], lon=pos[1], alt=pos[2])
        else:
            logger.debug("location: no GPS position to broadcast")
