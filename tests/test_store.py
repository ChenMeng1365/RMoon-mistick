# coding: utf-8
import json
import tempfile
import unittest
from pathlib import Path

from app.store import DrawStore, StoreError, normalize_draw
from tests.fixtures import make_draws


class NormalizeTest(unittest.TestCase):
    def test_valid(self):
        draw = normalize_draw({"c": "2026126", "d": "2026-11-03", "r": "9,1,3,5,7,2", "b": "16"})
        self.assertEqual(draw["r"], "01,02,03,05,07,09")
        self.assertEqual(draw["b"], "16")

    def test_bad_code(self):
        with self.assertRaises(StoreError):
            normalize_draw({"c": "126", "d": "2026-11-03", "r": "1,2,3,4,5,6", "b": "1"})

    def test_duplicate_red(self):
        with self.assertRaises(StoreError):
            normalize_draw({"c": "2026126", "d": "2026-11-03", "r": "1,1,3,4,5,6", "b": "1"})

    def test_blue_range(self):
        with self.assertRaises(StoreError):
            normalize_draw({"c": "2026126", "d": "2026-11-03", "r": "1,2,3,4,5,6", "b": "17"})


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = Path(self.tmp.name) / "draws.json"
        self.store = DrawStore(self.path)

    def tearDown(self):
        self.tmp.cleanup()

    def test_empty(self):
        self.assertEqual(self.store.count(), 0)
        self.assertEqual(self.store.meta()["count"], 0)

    def test_merge_and_reload(self):
        draws = make_draws(10)
        result = self.store.merge(draws)
        self.assertEqual(result["count"], 10)
        self.assertEqual(result["added"], 10)
        self.assertTrue(self.path.exists())

        reloaded = DrawStore(self.path)
        self.assertEqual(reloaded.count(), 10)
        self.assertEqual(reloaded.latest()["c"], draws[-1]["c"])

    def test_merge_dedup(self):
        draws = make_draws(5)
        self.store.merge(draws)
        changed = dict(draws[-1])
        changed["b"] = "01"
        result = self.store.merge([changed])
        self.assertEqual(result["count"], 5)
        self.assertEqual(result["added"], 0)
        self.assertEqual(result["accepted"], 1)
        self.assertEqual(self.store.latest()["b"], "01")

    def test_atomic_payload(self):
        self.store.merge(make_draws(3))
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(payload["count"], 3)
        self.assertEqual(len(payload["draws"]), 3)
        self.assertIn("t", payload)


if __name__ == "__main__":
    unittest.main()