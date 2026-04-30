"""
Tests for LoRa gateway packet encoding/decoding and location verifier.
"""

import math
import time
import unittest

from src.lora.lora_gateway import (
    LoRaGateway,
    LocationBeacon,
    MTYPE_LOCATION_BEACON,
    MTYPE_LOCATION_CONFIRM,
    decode_packet,
    encode_beacon,
    encode_confirm,
    parse_beacon_payload,
    parse_confirm_payload,
)
from src.lora.location import LocationVerifier, haversine_m, fspl_dbm


class TestPacketCodec(unittest.TestCase):
    DEV_EUI = "0102030405060708"
    TARGET_EUI = "0807060504030201"

    def test_beacon_encode_decode(self):
        frame = encode_beacon(self.DEV_EUI, seq=1, lat=25.04, lon=121.53, alt=50.0)
        pkt = decode_packet(frame, rssi=-80.0, snr=7.0)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.mtype, MTYPE_LOCATION_BEACON)
        self.assertEqual(pkt.dev_eui, self.DEV_EUI.lower())
        beacon = parse_beacon_payload(pkt)
        self.assertIsNotNone(beacon)
        self.assertAlmostEqual(beacon.lat, 25.04, places=2)
        self.assertAlmostEqual(beacon.lon, 121.53, places=2)
        self.assertAlmostEqual(beacon.altitude, 50.0, places=0)

    def test_confirm_encode_decode(self):
        frame = encode_confirm(self.DEV_EUI, seq=2, target_eui=self.TARGET_EUI,
                               target_seq=1, rssi=-75.0)
        pkt = decode_packet(frame, rssi=-75.0)
        self.assertIsNotNone(pkt)
        self.assertEqual(pkt.mtype, MTYPE_LOCATION_CONFIRM)
        confirm = parse_confirm_payload(pkt)
        self.assertIsNotNone(confirm)
        self.assertEqual(confirm["from_dev_eui"], self.DEV_EUI.lower())
        self.assertEqual(confirm["target_dev_eui"], self.TARGET_EUI.lower())
        self.assertAlmostEqual(confirm["rssi"], -75.0, places=1)

    def test_short_frame_returns_none(self):
        self.assertIsNone(decode_packet(b"\x01"))

    def test_empty_frame_returns_none(self):
        self.assertIsNone(decode_packet(b""))


class TestLocation(unittest.TestCase):
    def test_haversine_zero(self):
        self.assertAlmostEqual(haversine_m(0, 0, 0, 0), 0.0, places=0)

    def test_haversine_known(self):
        # Taipei (25.04, 121.53) → Kaohsiung (22.63, 120.30) ≈ 295 km
        dist = haversine_m(25.04, 121.53, 22.63, 120.30)
        self.assertGreater(dist, 280_000)
        self.assertLess(dist, 320_000)

    def test_fspl_increases_with_distance(self):
        close = fspl_dbm(100, 868.0)
        far = fspl_dbm(5000, 868.0)
        self.assertGreater(close, far)

    def test_fspl_negative_received_power(self):
        rssi = fspl_dbm(1000, 868.0, tx_power_dbm=14.0)
        self.assertLess(rssi, 0)

    def test_simulated_verification(self):
        """End-to-end: inject beacons + confirms via simulated gateway."""
        confirmed_events = []

        gw = LoRaGateway(dev_eui="aabbccddeeff0011", simulated=True)
        verifier = LocationVerifier(
            gateway=gw,
            dev_eui="aabbccddeeff0011",
        )
        verifier.on_verified(
            lambda eui, lat, lon: confirmed_events.append((eui, lat, lon))
        )
        gw.start()

        # Simulate receiving 3 confirm packets for our own beacon (seq=1)
        for _ in range(3):
            frame = encode_confirm(
                dev_eui="1122334455667788",  # from a neighbour
                seq=99,
                target_eui="aabbccddeeff0011",
                target_seq=1,
                rssi=-80.0,
            )
            gw._backend.inject(frame, rssi=-80.0)

        # Give RX thread time to process
        time.sleep(0.3)
        gw.stop()

        self.assertEqual(len(confirmed_events), 1)


if __name__ == "__main__":
    unittest.main()
