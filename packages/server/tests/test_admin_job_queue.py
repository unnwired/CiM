"""Unit tests for FIFO admin job queue."""
from __future__ import annotations

import sys
import threading
import time
import unittest
from pathlib import Path

from repo_paths import REPO_ROOT as ROOT

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
packages_root = ROOT / "packages"
if packages_root.is_dir() and str(packages_root) not in sys.path:
    sys.path.insert(0, str(packages_root))

from server import admin_job_queue as ajq  # noqa: E402


class TestAdminJobQueue(unittest.TestCase):
    def setUp(self):
        self.running = False
        ajq.reset_for_tests()
        ajq.configure(is_running_fn=lambda: self.running)

    def tearDown(self):
        ajq.reset_for_tests()

    def test_start_when_idle(self):
        started = []

        def starter():
            started.append(1)
            self.running = True

        result = ajq.submit("ohlcv", starter, label="Update", source="manual")
        self.assertEqual(result["status"], "started")
        self.assertEqual(started, [1])
        self.assertEqual(ajq.snapshot(), [])

    def test_enqueue_when_busy(self):
        self.running = True
        result = ajq.submit(
            "ohlcv",
            lambda: None,
            label="Update",
            source="manual",
        )
        self.assertEqual(result["status"], "queued")
        self.assertEqual(result["position"], 1)
        self.assertEqual(len(ajq.snapshot()), 1)

    def test_coalesce_same_key(self):
        self.running = True
        first = ajq.submit("ohlcv", lambda: None, label="A", source="manual")
        second = ajq.submit("ohlcv", lambda: None, label="B", source="scheduled")
        self.assertTrue(second.get("coalesced"))
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(len(ajq.snapshot()), 1)
        self.assertEqual(ajq.snapshot()[0]["label"], "B")

    def test_fifo_order_different_keys(self):
        self.running = True
        ajq.submit("ohlcv", lambda: None, label="OHLCV", source="manual")
        ajq.submit("filter_rebuild", lambda: None, label="Filter", source="scheduled")
        snap = ajq.snapshot()
        self.assertEqual([e["key"] for e in snap], ["ohlcv", "filter_rebuild"])

    def test_on_job_idle_pumps_next(self):
        order = []
        self.running = True
        ajq.submit(
            "ohlcv",
            lambda: order.append("ohlcv"),
            label="OHLCV",
            source="manual",
        )
        ajq.submit(
            "prices",
            lambda: order.append("prices"),
            label="Prices",
            source="manual",
        )
        self.running = False
        ajq.on_job_idle()
        self.assertEqual(order, ["ohlcv"])
        self.assertEqual(len(ajq.snapshot()), 1)
        self.assertEqual(ajq.snapshot()[0]["key"], "prices")

    def test_cancel_queued_and_clear(self):
        self.running = True
        a = ajq.submit("ohlcv", lambda: None, label="A", source="manual")
        b = ajq.submit("prices", lambda: None, label="B", source="manual")
        self.assertTrue(ajq.cancel_queued(a["id"]))
        snap = ajq.snapshot()
        self.assertEqual(len(snap), 1)
        self.assertEqual(snap[0]["id"], b["id"])
        self.assertEqual(ajq.clear_queue(), 1)
        self.assertEqual(ajq.snapshot(), [])

    def test_note_job_started_clears_reservation(self):
        gate = threading.Event()
        started = threading.Event()

        def starter():
            started.set()
            gate.wait(timeout=2)

        t = threading.Thread(
            target=lambda: ajq.submit("ohlcv", starter, label="X", source="manual"),
            daemon=True,
        )
        t.start()
        self.assertTrue(started.wait(timeout=2))
        self.assertTrue(ajq.slot_busy())
        self.running = True
        ajq.note_job_started()
        # Running flag owns the slot; reserved cleared.
        self.assertTrue(ajq.slot_busy())
        gate.set()
        t.join(timeout=2)


if __name__ == "__main__":
    unittest.main()
