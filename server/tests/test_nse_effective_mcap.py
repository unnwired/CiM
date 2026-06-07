import unittest

from nse_constituents import _effective_market_cap


class TestEffectiveMarketCap(unittest.TestCase):
    def test_issued_times_price(self):
        v = _effective_market_cap(None, 100.0, 1_000_000)
        self.assertEqual(v, 100_000_000.0)

    def test_crores_promoted_to_rupees(self):
        v = _effective_market_cap(5000.0, None, None)
        self.assertEqual(v, 50_000_000_000.0)

    def test_live_price_overrides_stored(self):
        v = _effective_market_cap(1.0, 50.0, 10, live_price=200.0)
        self.assertEqual(v, 2000.0)


if __name__ == "__main__":
    unittest.main()
