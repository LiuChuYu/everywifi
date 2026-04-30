"""
Tests for P2P gossip protocol.
"""

import time
import unittest

from src.p2p.gossip import GossipNode, MSG_TYPE_PING, MSG_TYPE_BLOCK


class TestGossipNode(unittest.TestCase):
    def test_start_stop(self):
        node = GossipNode(bind_port=17777)
        node.start()
        time.sleep(0.1)
        node.stop()

    def test_mark_seen_deduplication(self):
        node = GossipNode(bind_port=17778)
        node._mark_seen("abc")
        node._mark_seen("abc")
        self.assertEqual(node._seen_order.count("abc"), 1)

    def test_add_remove_peer(self):
        node = GossipNode(bind_port=17779)
        node.add_peer("127.0.0.1", 7777, peer_id="test_peer")
        self.assertIn("test_peer", node.get_peers())
        node.remove_peer("test_peer")
        self.assertNotIn("test_peer", node.get_peers())

    def test_local_loopback_gossip(self):
        """Two local nodes gossip a block message."""
        received = []

        node_a = GossipNode(bind_port=17780, node_id="node_a")
        node_b = GossipNode(bind_port=17781, node_id="node_b")

        node_b.on_message(MSG_TYPE_BLOCK, lambda p: received.append(p))

        node_a.start()
        node_b.start()

        # A → B
        node_a.add_peer("127.0.0.1", 17781, peer_id="node_b")
        node_a.broadcast(MSG_TYPE_BLOCK, {"hash": "deadbeef", "test": True})

        time.sleep(0.5)

        node_a.stop()
        node_b.stop()

        self.assertEqual(len(received), 1)
        self.assertEqual(received[0]["hash"], "deadbeef")

    def test_seen_cache_eviction(self):
        from src.p2p.gossip import _SEEN_CACHE_SIZE
        node = GossipNode(bind_port=17782)
        for i in range(_SEEN_CACHE_SIZE + 5):
            node._mark_seen(f"msg{i}")
        # Cache should not grow beyond limit
        self.assertLessEqual(len(node._seen_order), _SEEN_CACHE_SIZE)


if __name__ == "__main__":
    unittest.main()
