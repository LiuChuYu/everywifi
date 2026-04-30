"""
Tests for WiFi auth manager and bandwidth module.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from src.wifi.auth import AuthManager, Session
from src.wifi.bandwidth import BandwidthManager


class TestSession(unittest.TestCase):
    def test_not_expired_fresh(self):
        s = Session("aa:bb:cc:dd:ee:ff", "free")
        self.assertFalse(s.expired)

    def test_expired(self):
        import time
        s = Session("aa:bb:cc:dd:ee:ff", "free")
        s.last_seen = time.time() - 7200  # 2 hours ago
        self.assertTrue(s.expired)


class TestAuthManager(unittest.TestCase):
    def setUp(self):
        # Patch nft to avoid actual system calls
        patcher = patch("src.wifi.auth._nft")
        self._mock_nft = patcher.start()
        self.addCleanup(patcher.stop)
        self.auth = AuthManager()

    def test_add_free(self):
        self.auth.add_free("aa:bb:cc:dd:ee:ff")
        self.assertTrue(self.auth.is_authenticated("aa:bb:cc:dd:ee:ff"))
        sessions = self.auth.get_sessions()
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["tier"], "free")

    def test_case_insensitive_mac(self):
        self.auth.add_free("AA:BB:CC:DD:EE:FF")
        self.assertTrue(self.auth.is_authenticated("aa:bb:cc:dd:ee:ff"))

    def test_tick_removes_expired(self):
        import time
        self.auth.add_free("aa:bb:cc:dd:ee:ff")
        self.auth._sessions["aa:bb:cc:dd:ee:ff"].last_seen = time.time() - 7200
        self.auth.tick()
        self.assertFalse(self.auth.is_authenticated("aa:bb:cc:dd:ee:ff"))

    def test_confirm_payment_no_ledger(self):
        result = self.auth.confirm_payment("aa:bb:cc:dd:ee:ff", "abc123")
        self.assertIsNone(result)

    def test_confirm_payment_with_ledger(self):
        """Verify payment confirmation when ledger has a pending send."""
        mock_ledger = MagicMock()
        mock_conn = MagicMock()
        mock_row = MagicMock()
        # 5 EWF = 5 * 10^30
        mock_row.__getitem__ = lambda self, k: str(5 * 10 ** 30) if k == "amount" else None
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        mock_ledger._conn = mock_conn
        mock_ledger.pending_for.return_value = []

        self.auth.set_ledger(mock_ledger)
        result = self.auth.confirm_payment("aa:bb:cc:dd:ee:ff", "deadbeef")
        self.assertIsNotNone(result)
        # 5 EWF * 10 MB/EWF = 50 MB
        self.assertEqual(result, 50 * 1024 * 1024)

    def test_double_spend_blocked(self):
        mock_ledger = MagicMock()
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, k: str(1 * 10 ** 30)
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        mock_ledger._conn = mock_conn
        mock_ledger.pending_for.return_value = []
        self.auth.set_ledger(mock_ledger)

        result1 = self.auth.confirm_payment("aa:bb:cc:dd:ee:ff", "deaddead")
        result2 = self.auth.confirm_payment("aa:bb:cc:dd:ee:ff", "deaddead")
        self.assertIsNotNone(result1)
        self.assertIsNone(result2)  # second attempt blocked

    def test_deduct_traffic_downgrade(self):
        """When quota exhausted, client should be downgraded to free."""
        mock_ledger = MagicMock()
        mock_conn = MagicMock()
        mock_row = MagicMock()
        mock_row.__getitem__ = lambda self, k: str(1 * 10 ** 30)
        mock_conn.execute.return_value.fetchone.return_value = mock_row
        mock_ledger._conn = mock_conn
        mock_ledger.pending_for.return_value = []
        self.auth.set_ledger(mock_ledger)
        self.auth.add_free("dd:ee:ff:00:11:22")
        self.auth.confirm_payment("dd:ee:ff:00:11:22", "cafebabe")

        session = self.auth._sessions.get("dd:ee:ff:00:11:22")
        self.assertIsNotNone(session)
        # Deduct entire quota
        self.auth.deduct_traffic("dd:ee:ff:00:11:22", session.quota_bytes + 1)
        # Should be back to free
        self.assertEqual(self.auth._sessions["dd:ee:ff:00:11:22"].tier, "free")


class TestBandwidthManager(unittest.TestCase):
    def test_instantiation(self):
        """BandwidthManager should instantiate without running tc."""
        bm = BandwidthManager(iface="br-lan")
        self.assertIsNotNone(bm)


if __name__ == "__main__":
    unittest.main()
