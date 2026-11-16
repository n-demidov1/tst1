"""Тесты без выхода в интернет: поднимаем локальный HTTP-сервер."""

import contextlib
import io
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from netspeed import cli, core

PAYLOAD = b"x" * 300_000  # больше CHUNK_SIZE, чтобы проверить чтение кусками


class _Handler(BaseHTTPRequestHandler):
    seen_headers: list = []

    def do_GET(self):
        _Handler.seen_headers.append(dict(self.headers))
        if self.path == "/missing":
            self.send_error(404)
            return
        body = b"" if self.path == "/empty" else PAYLOAD
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):  # не шуметь в выводе тестов
        pass


class LocalServerTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), _Handler)
        cls.base = f"http://127.0.0.1:{cls.server.server_address[1]}"
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        _Handler.seen_headers.clear()


class MathTests(unittest.TestCase):
    def test_mbps(self):
        # 1 250 000 байт = 10 000 000 бит; за 1 с это 10 Мбит/с
        self.assertAlmostEqual(core.mbps(1_250_000, 1.0), 10.0)
        self.assertAlmostEqual(core.mbps(1_250_000, 2.0), 5.0)

    def test_mbps_zero_time(self):
        self.assertEqual(core.mbps(100, 0), 0.0)

    def test_summary(self):
        s = core.Summary([core.RequestResult(1_000_000, 1.0), core.RequestResult(1_500_000, 3.0)])
        self.assertEqual(s.count, 2)
        self.assertEqual(s.total_bytes, 2_500_000)
        self.assertAlmostEqual(s.avg_seconds, 2.0)
        # 20 000 000 бит за 4 с = 5 Мбит/с (суммарные байты / суммарное время)
        self.assertAlmostEqual(s.speed_mbps, 5.0)

    def test_empty_summary(self):
        s = core.Summary([])
        self.assertEqual(s.avg_seconds, 0.0)
        self.assertEqual(s.speed_mbps, 0.0)


class MeasureTests(LocalServerTestCase):
    def test_downloads_full_body_n_times(self):
        calls = []
        summary = core.measure(f"{self.base}/file", count=10, on_result=lambda i, r: calls.append(i))
        self.assertEqual(summary.count, 10)
        self.assertEqual(summary.total_bytes, 10 * len(PAYLOAD))
        self.assertEqual(calls, list(range(1, 11)))
        self.assertEqual(len(_Handler.seen_headers), 10)
        self.assertTrue(all(r.seconds > 0 for r in summary.results))

    def test_sends_no_cache_and_identity(self):
        core.fetch_once(f"{self.base}/file")
        headers = {k.lower(): v for k, v in _Handler.seen_headers[0].items()}
        self.assertEqual(headers["cache-control"], "no-cache")
        self.assertEqual(headers["accept-encoding"], "identity")

    def test_count_must_be_positive(self):
        with self.assertRaises(ValueError):
            core.measure(f"{self.base}/file", count=0)


class CliTests(LocalServerTestCase):
    def run_cli(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_success_output(self):
        code, out, _ = self.run_cli(f"{self.base}/file", "-n", "3")
        self.assertEqual(code, 0)
        self.assertIn("Среднее время запроса", out)
        self.assertIn("Всего скачано", out)
        self.assertIn("Мбит/с", out)
        self.assertIn(str(3 * len(PAYLOAD)), out)

    def test_http_error(self):
        code, _, err = self.run_cli(f"{self.base}/missing", "-n", "1")
        self.assertEqual(code, 2)
        self.assertIn("404", err)

    def test_empty_body(self):
        code, _, err = self.run_cli(f"{self.base}/empty", "-n", "2")
        self.assertEqual(code, 3)
        self.assertIn("пустой", err)

    def test_connection_refused(self):
        # порт 1 на localhost почти наверняка закрыт
        code, _, err = self.run_cli("http://127.0.0.1:1/", "-n", "1", "-t", "2")
        self.assertEqual(code, 2)
        self.assertIn("Сетевая ошибка", err)

    def test_rejects_bad_url(self):
        with contextlib.redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit):
                cli.main(["ftp://example.com/x"])


if __name__ == "__main__":
    unittest.main()
