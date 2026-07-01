"""Tests for cooperative admin job cancellation."""

from __future__ import annotations

import unittest

from server.admin_job_control import (
    JobCancelled,
    clear_cancel,
    is_cancel_requested,
    request_cancel,
    sleep_interruptible,
)


class AdminJobControlTests(unittest.TestCase):
    def setUp(self):
        clear_cancel()

    def tearDown(self):
        clear_cancel()

    def test_request_and_check_cancel(self):
        self.assertFalse(is_cancel_requested())
        request_cancel()
        self.assertTrue(is_cancel_requested())

    def test_sleep_interruptible_raises_when_cancelled(self):
        request_cancel()
        with self.assertRaises(JobCancelled):
            sleep_interruptible(30)


if __name__ == "__main__":
    unittest.main()
