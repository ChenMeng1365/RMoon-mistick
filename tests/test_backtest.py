# coding: utf-8
import unittest

from app.backtest import prize_level, run_backtest
from app.strategies import StrategyError
from tests.fixtures import make_draws

ACTUAL = {"c": "2003001", "d": "2003-02-23", "r": "01,02,03,04,05,06", "b": "07"}


class PrizeLevelTest(unittest.TestCase):
    def test_levels(self):
        cases = [
            ([1, 2, 3, 4, 5, 6], 7, 1),
            ([1, 2, 3, 4, 5, 6], 8, 2),
            ([1, 2, 3, 4, 5, 9], 7, 3),
            ([1, 2, 3, 4, 5, 9], 8, 4),
            ([1, 2, 3, 4, 9, 10], 7, 4),
            ([1, 2, 3, 4, 9, 10], 8, 5),
            ([1, 2, 3, 9, 10, 11], 7, 5),
            ([1, 2, 3, 9, 10, 11], 8, 0),
            ([1, 2, 9, 10, 11, 12], 7, 6),
            ([9, 10, 11, 12, 13, 14], 7, 6),
            ([1, 2, 9, 10, 11, 12], 8, 0),
        ]
        for reds, blue, expected in cases:
            self.assertEqual(prize_level(reds, blue, ACTUAL), expected, (reds, blue))


class BacktestTest(unittest.TestCase):
    def setUp(self):
        self.draws = make_draws(100)

    def test_random_backtest(self):
        result = run_backtest(self.draws, "random", {}, tickets_per_draw=2, start=60, seed=1)
        self.assertEqual(result["draws"], 40)
        self.assertEqual(result["tickets"], 80)
        self.assertEqual(result["cost"], 160)
        self.assertLessEqual(sum(item["count"] for item in result["levels"]), 80)
        self.assertLessEqual(sum(item["count"] for item in result["baseline"]["levels"]), 80)
        self.assertGreaterEqual(result["roi"], 0)
        self.assertIn("deltaRoi", result)

    def test_unknown_strategy(self):
        with self.assertRaises(StrategyError):
            run_backtest(self.draws, "nope", {}, 1, 60)

    def test_too_short(self):
        with self.assertRaises(StrategyError):
            run_backtest(self.draws[:30], "random", {}, 1, 30)


if __name__ == "__main__":
    unittest.main()