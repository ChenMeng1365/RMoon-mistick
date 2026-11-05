# coding: utf-8
import random
import unittest

from app.strategies import (
    StrategyEngine,
    StrategyError,
    normalize_filters,
)
from tests.fixtures import make_draws


class StrategyTest(unittest.TestCase):
    def setUp(self):
        self.draws = make_draws(200)

    def engine(self, strategy="random", filters=None, window=100):
        return StrategyEngine(self.draws, window=window, filters=filters, strategy=strategy)

    def assert_ticket_valid(self, ticket):
        self.assertEqual(len(ticket["r"]), 6)
        self.assertEqual(len(set(ticket["r"])), 6)
        self.assertTrue(all(1 <= n <= 33 for n in ticket["r"]))
        self.assertTrue(1 <= ticket["b"] <= 16)

    def test_random_generate(self):
        tickets = self.engine("random").generate(20, random.Random(1))
        self.assertEqual(len(tickets), 20)
        self.assertEqual(len({(tuple(t["r"]), t["b"]) for t in tickets}), 20)
        for ticket in tickets:
            self.assert_ticket_valid(ticket)

    def test_all_strategies(self):
        for strategy in ("hot", "cold", "omission", "avoid", "balanced"):
            engine = self.engine(strategy)
            tickets = engine.generate(3, random.Random(2))
            self.assertEqual(len(tickets), 3)
            for ticket in tickets:
                self.assert_ticket_valid(ticket)

    def test_balanced_filters(self):
        engine = self.engine("balanced")
        for ticket in engine.generate(10, random.Random(3)):
            reds = ticket["r"]
            odd = sum(1 for n in reds if n % 2)
            self.assertGreaterEqual(odd, 2)
            self.assertLessEqual(odd, 4)
            self.assertGreaterEqual(sum(reds), 80)
            self.assertLessEqual(sum(reds), 130)

    def test_include_exclude(self):
        engine = self.engine("custom", {"include": [1, 2, 3], "exclude": [4, 5]})
        for ticket in engine.generate(5, random.Random(4)):
            self.assertTrue({1, 2, 3}.issubset(set(ticket["r"])))
            self.assertFalse({4, 5} & set(ticket["r"]))

    def test_deterministic_seed(self):
        first = self.engine("hot").generate(5, random.Random(42))
        second = self.engine("hot").generate(5, random.Random(42))
        self.assertEqual(first, second)

    def test_invalid_filters(self):
        with self.assertRaises(StrategyError):
            normalize_filters({"sum_min": 150, "sum_max": 100}, "custom")
        with self.assertRaises(StrategyError):
            normalize_filters({"include": [1, 2, 3, 4, 5, 6, 7]}, "custom")
        with self.assertRaises(StrategyError):
            normalize_filters({"include": [1], "exclude": [1]}, "custom")

    def test_too_strict_filter(self):
        engine = self.engine("custom", {"include": [1, 2, 3, 4, 5, 6]})
        # 固定 6 个红球时仍可生成，但蓝球会随机
        tickets = engine.generate(2, random.Random(5))
        self.assertEqual(len(tickets), 2)
        self.assertEqual(tickets[0]["r"], [1, 2, 3, 4, 5, 6])


if __name__ == "__main__":
    unittest.main()