# coding: utf-8
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from app.api import App
from app.config import Config
from app.server import create_server
from tests.fixtures import make_draws


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        root = Path(cls.tmp.name)
        data_file = root / "draws.json"
        draws = make_draws(100)
        data_file.write_text(
            json.dumps({"t": 1, "count": len(draws), "draws": draws}, ensure_ascii=False),
            encoding="utf-8",
        )
        cls.config = Config(
            host="127.0.0.1",
            port=0,
            data_file=str(data_file),
            static_dir=str(Path(__file__).resolve().parent.parent / "static"),
            log_dir=str(root / "logs"),
        )
        cls.app = App(cls.config)
        cls.server = create_server(cls.config, cls.app)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def request(self, path, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            body = response.read()
            content_type = response.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return response.status, json.loads(body.decode("utf-8"))
            return response.status, body.decode("utf-8", errors="replace")

    def test_health(self):
        status, data = self.request("/api/health")
        self.assertEqual(status, 200)
        self.assertTrue(data["ok"])
        self.assertEqual(data["draws"], 100)

    def test_meta_and_draws(self):
        status, data = self.request("/api/meta")
        self.assertEqual(status, 200)
        self.assertEqual(data["count"], 100)
        status, data = self.request("/api/draws?limit=5")
        self.assertEqual(status, 200)
        self.assertEqual(len(data["items"]), 5)
        self.assertEqual(data["items"][0]["c"], "2003100")

    def test_stats(self):
        status, data = self.request("/api/stats?window=30")
        self.assertEqual(status, 200)
        self.assertEqual(data["n"], 30)
        self.assertIn("cooccurrence", data)

    def test_generate(self):
        status, data = self.request(
            "/api/generate",
            method="POST",
            payload={"strategy": "hot", "count": 3, "params": {"window": 50}},
        )
        self.assertEqual(status, 200)
        self.assertEqual(len(data["tickets"]), 3)
        self.assertEqual(len(data["tickets"][0]["r"]), 6)

    def test_backtest(self):
        status, data = self.request(
            "/api/backtest",
            method="POST",
            payload={
                "strategy": "random",
                "params": {"window": 50},
                "ticketsPerDraw": 2,
                "start": 60,
                "seed": 1,
            },
        )
        self.assertEqual(status, 200)
        self.assertEqual(data["cost"], 160)
        self.assertEqual(data["tickets"], 80)

    def test_wheel(self):
        status, data = self.request(
            "/api/wheel",
            method="POST",
            payload={"pool": [1, 2, 3, 4, 5, 6, 7, 8], "guarantee": 5},
        )
        self.assertEqual(status, 200)
        self.assertGreaterEqual(data["ticketCount"], 1)
        self.assertEqual(data["coverage"], 1.0)

    def test_static_index(self):
        status, html = self.request("/")
        self.assertEqual(status, 200)
        self.assertIn("mistick", html)

    def test_unknown_api(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request("/api/nope")
        self.assertEqual(context.exception.code, 404)

    def test_invalid_strategy(self):
        with self.assertRaises(urllib.error.HTTPError) as context:
            self.request(
                "/api/generate",
                method="POST",
                payload={"strategy": "nope", "count": 1, "params": {}},
            )
        self.assertEqual(context.exception.code, 400)


if __name__ == "__main__":
    unittest.main()