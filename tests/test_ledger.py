"""
Tests for the Block-Lattice ledger.
"""

import os
import tempfile
import unittest

from src.ledger.ledger import (
    Block,
    BlockType,
    Ledger,
    GENESIS_ACCOUNT,
    compute_pow,
    verify_pow,
    generate_account,
    sign_block,
    WORK_THRESHOLD,
)


class TestPoW(unittest.TestCase):
    def test_compute_and_verify(self):
        block_hash = "a" * 64
        work = compute_pow(block_hash, threshold=0xFFF0000000000000)  # low threshold for speed
        self.assertTrue(verify_pow(block_hash, work, threshold=0xFFF0000000000000))

    def test_invalid_work(self):
        self.assertFalse(verify_pow("a" * 64, "00" * 8))


class TestBlock(unittest.TestCase):
    def test_hash_is_deterministic(self):
        b1 = Block(
            block_type=BlockType.OPEN,
            account="ewf_abc",
            previous="0" * 64,
            representative="ewf_abc",
            balance=1000,
            link="0" * 64,
        )
        b2 = Block(
            block_type=BlockType.OPEN,
            account="ewf_abc",
            previous="0" * 64,
            representative="ewf_abc",
            balance=1000,
            link="0" * 64,
        )
        self.assertEqual(b1.hash, b2.hash)

    def test_different_balance_different_hash(self):
        b1 = Block(BlockType.OPEN, "ewf_a", "0" * 64, "ewf_a", 100, "0" * 64)
        b2 = Block(BlockType.OPEN, "ewf_a", "0" * 64, "ewf_a", 200, "0" * 64)
        self.assertNotEqual(b1.hash, b2.hash)

    def test_to_dict_round_trip(self):
        b = Block(BlockType.SEND, "ewf_a", "0" * 64, "ewf_a", 50, "ewf_b")
        d = b.to_dict()
        b2 = Block.from_dict(d)
        self.assertEqual(b.hash, b2.hash)
        self.assertEqual(b.balance, b2.balance)


class TestLedger(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.mkdtemp()
        self._db = os.path.join(self._tmpdir, "test_ledger.db")
        self.ledger = Ledger(db_path=self._db)

    def tearDown(self):
        self.ledger.close()
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    def _make_account(self):
        private_key, address = generate_account()
        self.ledger.create_account(address, public_key="0" * 64)
        return private_key, address

    def test_create_account(self):
        _, addr = self._make_account()
        self.assertEqual(self.ledger.get_balance(addr), 0)

    def test_duplicate_account_returns_false(self):
        _, addr = self._make_account()
        result = self.ledger.create_account(addr, "0" * 64)
        self.assertFalse(result)

    def test_send_receive_flow(self):
        # Set up genesis-like sender with balance
        genesis_pk, genesis_addr = generate_account()
        self.ledger.create_account(genesis_addr, "0" * 64)

        # Manually insert an open block for genesis with balance
        open_block = Block(
            block_type=BlockType.OPEN,
            account=genesis_addr,
            previous="0" * 64,
            representative=genesis_addr,
            balance=1_000 * (10 ** 30),
            link="0" * 64,
        )
        open_block.work = compute_pow(open_block.hash, threshold=0xFFF0000000000000)
        open_block.signature = sign_block(open_block, genesis_pk)
        ok = self.ledger.process_block(open_block)
        self.assertTrue(ok)
        self.assertEqual(self.ledger.get_balance(genesis_addr), 1_000 * (10 ** 30))

        # Create receiver
        recv_pk, recv_addr = self._make_account()

        # Send 100 EWF
        send_block = self.ledger.send(
            genesis_addr,
            recv_addr,
            100 * (10 ** 30),
            genesis_pk,
        )
        self.assertIsNotNone(send_block)
        self.assertEqual(self.ledger.get_balance(genesis_addr), 900 * (10 ** 30))

        # Check pending
        pending = self.ledger.pending_for(recv_addr)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["amount"], 100 * (10 ** 30))

        # Receive
        recv_block = self.ledger.receive(
            recv_addr,
            send_block.hash,
            recv_pk,
        )
        self.assertIsNotNone(recv_block)
        self.assertEqual(self.ledger.get_balance(recv_addr), 100 * (10 ** 30))
        # Pending should be cleared
        self.assertEqual(self.ledger.pending_for(recv_addr), [])

    def test_send_insufficient_balance(self):
        pk, addr = self._make_account()
        result = self.ledger.send(addr, "ewf_nobody", 1, pk)
        self.assertIsNone(result)

    def test_account_chain(self):
        genesis_pk, genesis_addr = generate_account()
        self.ledger.create_account(genesis_addr, "0" * 64)
        open_block = Block(
            block_type=BlockType.OPEN,
            account=genesis_addr,
            previous="0" * 64,
            representative=genesis_addr,
            balance=500 * (10 ** 30),
            link="0" * 64,
        )
        open_block.work = compute_pow(open_block.hash, threshold=0xFFF0000000000000)
        open_block.signature = sign_block(open_block, genesis_pk)
        self.ledger.process_block(open_block)
        chain = self.ledger.account_chain(genesis_addr)
        self.assertGreaterEqual(len(chain), 1)

    def test_duplicate_block_ignored(self):
        genesis_pk, genesis_addr = generate_account()
        self.ledger.create_account(genesis_addr, "0" * 64)
        open_block = Block(
            block_type=BlockType.OPEN,
            account=genesis_addr,
            previous="0" * 64,
            representative=genesis_addr,
            balance=100 * (10 ** 30),
            link="0" * 64,
        )
        open_block.work = compute_pow(open_block.hash, threshold=0xFFF0000000000000)
        open_block.signature = sign_block(open_block, genesis_pk)
        self.assertTrue(self.ledger.process_block(open_block))
        # Second time should fail
        self.assertFalse(self.ledger.process_block(open_block))


if __name__ == "__main__":
    unittest.main()
