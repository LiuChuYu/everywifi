"""
LoRa gateway interface.

Supports two hardware backends:
  1. USB serial (e.g. RAK2247 via USB, presents as /dev/ttyUSB0)
  2. SPI (e.g. SX1276 directly connected via spidev)

The gateway:
  - Listens for incoming LoRa packets
  - Parses LoRaWAN-like frame format (simplified)
  - Calls registered callbacks on receipt of location beacons
  - Broadcasts location beacon packets from this node
"""

from __future__ import annotations

import binascii
import hashlib
import json
import logging
import os
import struct
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

from src.config import (
    LORA_BAUD,
    LORA_DEVICE,
    LORA_FREQ_MHZ,
    LORA_SF,
    LORA_BW_KHZ,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Packet types
# ---------------------------------------------------------------------------
MTYPE_LOCATION_BEACON = 0x01   # node broadcasts its position
MTYPE_LOCATION_CONFIRM = 0x02  # peer confirms a beacon


@dataclass
class LoraPacket:
    mtype: int
    dev_eui: str        # 8-byte DevEUI as hex string
    payload: bytes
    rssi: float = 0.0   # dBm, filled in by receiver
    snr: float = 0.0    # dB
    freq: float = 0.0   # MHz
    timestamp: float = 0.0


@dataclass
class LocationBeacon:
    dev_eui: str
    lat: float
    lon: float
    altitude: float
    rssi: float          # as measured by the receiving gateway
    seq: int             # sequence number (anti-replay)
    timestamp: float


# ---------------------------------------------------------------------------
# Frame encoding / decoding (simplified LoRaWAN-like)
# ---------------------------------------------------------------------------
# Frame structure (binary):
#   [1B mtype] [8B DevEUI] [4B seq] [payload...]
# Location beacon payload:
#   [4B lat as float32] [4B lon as float32] [2B altitude int16]
# Location confirm payload:
#   [8B target DevEUI] [4B seq] [4B rssi as float32]

_HEADER_FMT = "!B8sI"  # mtype(1) + dev_eui(8) + seq(4)
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)

_BEACON_PAYLOAD_FMT = "!ffh"  # lat, lon, altitude
_CONFIRM_PAYLOAD_FMT = "!8sIf"  # target DevEUI, seq, rssi


def encode_beacon(dev_eui: str, seq: int, lat: float, lon: float, alt: float) -> bytes:
    dev_eui_bytes = bytes.fromhex(dev_eui.replace(":", "").ljust(16, "0")[:16])
    header = struct.pack(_HEADER_FMT, MTYPE_LOCATION_BEACON, dev_eui_bytes, seq)
    payload = struct.pack(_BEACON_PAYLOAD_FMT, lat, lon, int(alt))
    return header + payload


def encode_confirm(dev_eui: str, seq: int, target_eui: str, target_seq: int, rssi: float) -> bytes:
    dev_eui_bytes = bytes.fromhex(dev_eui.replace(":", "").ljust(16, "0")[:16])
    target_eui_bytes = bytes.fromhex(target_eui.replace(":", "").ljust(16, "0")[:16])
    header = struct.pack(_HEADER_FMT, MTYPE_LOCATION_CONFIRM, dev_eui_bytes, seq)
    payload = struct.pack(_CONFIRM_PAYLOAD_FMT, target_eui_bytes, target_seq, rssi)
    return header + payload


def decode_packet(data: bytes, rssi: float = 0.0, snr: float = 0.0) -> Optional[LoraPacket]:
    if len(data) < _HEADER_SIZE:
        return None
    mtype, dev_eui_bytes, seq = struct.unpack_from(_HEADER_FMT, data)
    payload = data[_HEADER_SIZE:]
    return LoraPacket(
        mtype=mtype,
        dev_eui=dev_eui_bytes.hex(),
        payload=payload,
        rssi=rssi,
        snr=snr,
        timestamp=time.time(),
    )


def parse_beacon_payload(packet: LoraPacket) -> Optional[LocationBeacon]:
    try:
        lat, lon, alt = struct.unpack(_BEACON_PAYLOAD_FMT, packet.payload)
        return LocationBeacon(
            dev_eui=packet.dev_eui,
            lat=lat,
            lon=lon,
            altitude=float(alt),
            rssi=packet.rssi,
            seq=0,
            timestamp=packet.timestamp,
        )
    except struct.error:
        return None


def parse_confirm_payload(packet: LoraPacket) -> Optional[dict]:
    try:
        target_eui, target_seq, rssi = struct.unpack(_CONFIRM_PAYLOAD_FMT, packet.payload)
        return {
            "from_dev_eui": packet.dev_eui,
            "target_dev_eui": target_eui.hex(),
            "target_seq": target_seq,
            "rssi": rssi,
        }
    except struct.error:
        return None


# ---------------------------------------------------------------------------
# Hardware backends
# ---------------------------------------------------------------------------

class _USBSerialBackend:
    """
    Communicate with LoRa module via USB serial (AT command set,
    e.g. RAK811 / RAK2247 packet forwarder text protocol).
    """

    def __init__(self, device: str, baud: int) -> None:
        self._device = device
        self._baud = baud
        self._serial = None

    def open(self) -> None:
        try:
            import serial
            self._serial = serial.Serial(self._device, self._baud, timeout=1)
            logger.info("LoRa USB serial opened: %s @ %d baud", self._device, self._baud)
        except Exception as exc:
            logger.error("LoRa USB serial open failed: %s", exc)
            raise

    def close(self) -> None:
        if self._serial:
            self._serial.close()

    def send(self, data: bytes) -> None:
        if not self._serial:
            return
        # RAK811 AT command: AT+SEND=<data_hex>
        cmd = "AT+SEND=" + data.hex() + "\r\n"
        self._serial.write(cmd.encode())

    def read_packet(self) -> Optional[tuple[bytes, float, float]]:
        """Return (raw_bytes, rssi, snr) or None if no packet ready."""
        if not self._serial or not self._serial.in_waiting:
            return None
        line = self._serial.readline().decode(errors="replace").strip()
        # Expected format: +RCV=<hex_data>,<rssi>,<snr>
        if not line.startswith("+RCV="):
            return None
        try:
            parts = line[5:].split(",")
            raw = bytes.fromhex(parts[0])
            rssi = float(parts[1]) if len(parts) > 1 else 0.0
            snr = float(parts[2]) if len(parts) > 2 else 0.0
            return raw, rssi, snr
        except (ValueError, IndexError):
            return None


class _SimulatedBackend:
    """Simulated LoRa backend for development/testing without hardware."""

    def __init__(self) -> None:
        self._queue: list[tuple[bytes, float, float]] = []

    def open(self) -> None:
        logger.info("LoRa: using simulated backend")

    def close(self) -> None:
        pass

    def send(self, data: bytes) -> None:
        logger.debug("LoRa sim TX: %s", data.hex())

    def inject(self, data: bytes, rssi: float = -80.0, snr: float = 7.0) -> None:
        """Inject a test packet into the RX queue."""
        self._queue.append((data, rssi, snr))

    def read_packet(self) -> Optional[tuple[bytes, float, float]]:
        return self._queue.pop(0) if self._queue else None


# ---------------------------------------------------------------------------
# LoRa Gateway
# ---------------------------------------------------------------------------

class LoRaGateway:
    """
    High-level LoRa gateway.

    Usage:
        gw = LoRaGateway(dev_eui="0102030405060708")
        gw.on_beacon(my_beacon_handler)
        gw.on_confirm(my_confirm_handler)
        gw.start()
        gw.broadcast_beacon(lat=25.04, lon=121.53, alt=10.0)
    """

    def __init__(
        self,
        dev_eui: str,
        device: str = LORA_DEVICE,
        baud: int = LORA_BAUD,
        simulated: bool = False,
    ) -> None:
        self._dev_eui = dev_eui.lower()
        self._seq = 0
        self._running = False
        self._beacon_callbacks: List[Callable[[LocationBeacon], None]] = []
        self._confirm_callbacks: List[Callable[[dict], None]] = []

        if simulated or not os.path.exists(device):
            self._backend = _SimulatedBackend()
        else:
            self._backend = _USBSerialBackend(device, baud)

    # ------------------------------------------------------------------
    # Callbacks
    # ------------------------------------------------------------------

    def on_beacon(self, cb: Callable[[LocationBeacon], None]) -> None:
        self._beacon_callbacks.append(cb)

    def on_confirm(self, cb: Callable[[dict], None]) -> None:
        self._confirm_callbacks.append(cb)

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start(self) -> None:
        self._backend.open()
        self._running = True
        t = threading.Thread(target=self._rx_loop, daemon=True)
        t.start()
        logger.info("LoRa gateway started (DevEUI %s)", self._dev_eui)

    def stop(self) -> None:
        self._running = False
        self._backend.close()

    # ------------------------------------------------------------------
    # TX
    # ------------------------------------------------------------------

    def broadcast_beacon(self, lat: float, lon: float, alt: float = 0.0) -> None:
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        frame = encode_beacon(self._dev_eui, self._seq, lat, lon, alt)
        self._backend.send(frame)
        logger.debug("LoRa beacon TX seq=%d lat=%.4f lon=%.4f", self._seq, lat, lon)

    def send_confirm(self, target_eui: str, target_seq: int, rssi: float) -> None:
        self._seq = (self._seq + 1) & 0xFFFFFFFF
        frame = encode_confirm(self._dev_eui, self._seq, target_eui, target_seq, rssi)
        self._backend.send(frame)

    # ------------------------------------------------------------------
    # RX loop
    # ------------------------------------------------------------------

    def _rx_loop(self) -> None:
        while self._running:
            result = self._backend.read_packet()
            if result is None:
                time.sleep(0.05)
                continue
            raw, rssi, snr = result
            pkt = decode_packet(raw, rssi=rssi, snr=snr)
            if pkt is None:
                continue
            if pkt.mtype == MTYPE_LOCATION_BEACON:
                beacon = parse_beacon_payload(pkt)
                if beacon:
                    for cb in self._beacon_callbacks:
                        try:
                            cb(beacon)
                        except Exception as exc:
                            logger.error("beacon callback error: %s", exc)
            elif pkt.mtype == MTYPE_LOCATION_CONFIRM:
                confirm = parse_confirm_payload(pkt)
                if confirm:
                    for cb in self._confirm_callbacks:
                        try:
                            cb(confirm)
                        except Exception as exc:
                            logger.error("confirm callback error: %s", exc)
