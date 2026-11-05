# coding: utf-8
import unittest

from app.analytics import (
    build_stats,
    chi2_sf,
    cooccurrence_stats,
    frequency_stats,
    omission_stats,
    shape_stats,
    sum_stats,
)
from tests.fixtures import make_draws


class ChiSquareTest(unittest.TestCase):
    def test_critical_value(self):
        # df=1, 95% 临界值 3.841，上尾概率应接近 0.05
        self.assertAlmostEqual(chi2_sf(3.841, 1), 0.05, places=3)

    def test_large_value(self):
        self.assertLess(chi2_sf(100, 10), 1e-10)


class AnalyticsTest(unittest.TestCase):
    def setUp(self):
        self.draws = make_draws(100)

    def test_frequency_totals(self):
        red, blue, red_chi, blue_chi = frequency_stats(self.draws)
        self.assertEqual(sum(red[1:]), 600)
        self.assertEqual(sum(blue[1:]), 100)
        self.assertEqual(red_chi["df"], 32)
        self.assertEqual(blue_chi["df"], 15)
        self.assertGreater(red_chi["p"], 0)

    def test_omission_simple(self):
        draws = [
            {"c": "2003001", "d": "2003-02-23", "r": "01,02,03,04,05,06", "b": "01"},
            {"c": "2003002", "d": "2003-02-24", "r": "01,07,08,09,10,11", "b": "02"},
            {"c": "2003003", "d": "2003-02-25", "r": "01,12,13,14,15,16", "b": "03"},
        ]
        red, blue = omission_stats(draws)
        self.assertEqual(red["current"][1], 0)
        self.assertEqual(red["current"][2], 2)
        self.assertEqual(red["avg"][2], 2)
        self.assertEqual(red["max"][2], 2)
        self.assertEqual(blue["current"][1], 2)

    def test_sum(self):
        result = sum_stats(self.draws)
        self.assertGreater(result["mean"], 0)
        self.assertEqual(sum(item["n"] for item in result["buckets"]), len(self.draws))

    def test_shape_distributions(self):
        result = shape_stats(self.draws)
        self.assertEqual(sum(item["n"] for item in result["odd"]), len(self.draws))
        self.assertEqual(sum(item["n"] for item in result["big"]), len(self.draws))
        self.assertEqual(sum(item["n"] for item in result["consecutive"]), len(self.draws))
        self.assertEqual(sum(result["tail"]["counts"]), len(self.draws) * 6)
        # 重号/邻号没有第一期，样本是 n-1
        self.assertEqual(sum(item["n"] for item in result["repeat"]), len(self.draws) - 1)
        self.assertEqual(sum(item["n"] for item in result["neighbor"]), len(self.draws) - 1)

    def test_cooccurrence_symmetric(self):
        result = cooccurrence_stats(self.draws)
        matrix = result["matrix"]
        for a in range(1, 34):
            for b in range(1, 34):
                self.assertEqual(matrix[a][b], matrix[b][a])
        self.assertTrue(result["top"])

    def test_build_stats(self):
        result = build_stats(self.draws, "30")
        self.assertEqual(result["n"], 30)
        self.assertEqual(result["range"]["last"], self.draws[-1]["c"])
        for key in ("red", "blue", "sum", "odd", "span", "ac", "cooccurrence", "blueShape"):
            self.assertIn(key, result)


if __name__ == "__main__":
    unittest.main()