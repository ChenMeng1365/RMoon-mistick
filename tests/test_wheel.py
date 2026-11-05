# coding: utf-8
import unittest

from app.strategies import StrategyError
from app.wheel import build_wheel


class WheelTest(unittest.TestCase):
    def test_pool_of_seven(self):
        result = build_wheel(list(range(1, 8)), 5)
        self.assertEqual(result["ticketCount"], 1)
        self.assertEqual(result["coverage"], 1.0)

    def test_pool_of_ten(self):
        result = build_wheel(list(range(1, 11)), 5)
        self.assertLess(result["ticketCount"], 210)
        self.assertEqual(result["coverage"], 1.0)
        for ticket in result["tickets"]:
            self.assertEqual(len(ticket), 6)

    def test_pool_too_small(self):
        with self.assertRaises(StrategyError):
            build_wheel([1, 2, 3, 4, 5, 6], 5)

    def test_bad_guarantee(self):
        with self.assertRaises(StrategyError):
            build_wheel(list(range(1, 9)), 4)


if __name__ == "__main__":
    unittest.main()