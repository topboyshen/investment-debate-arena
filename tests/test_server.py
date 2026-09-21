import http.client
import json
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from server import Handler, SECURITY_HEADERS


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.host, cls.port = cls.server.server_address

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection(self.host, self.port, timeout=3)
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        raw = response.read()
        result = response.status, dict(response.getheaders()), raw
        connection.close()
        return result

    def json_request(self, payload, *, content_type="application/json"):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        return self.request("POST", "/api/debate", body, {"Content-Type": content_type})

    def assert_security_headers(self, headers):
        lowered = {key.lower(): value for key, value in headers.items()}
        for name in SECURITY_HEADERS:
            self.assertIn(name.lower(), lowered)

    def test_health_ready_and_page_are_hardened(self):
        for path in ("/", "/healthz", "/readyz"):
            with self.subTest(path=path):
                status, headers, _ = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assert_security_headers(headers)
                self.assertNotIn("Python/", headers.get("Server", ""))
        status, _, body = self.request("GET", "/readyz")
        self.assertEqual(json.loads(body)["status"], "ready")

    def test_valid_request(self):
        status, headers, body = self.json_request({"ticker": "AAPL", "thesis": "审视服务收入韧性。"})
        self.assertEqual(status, 200)
        self.assert_security_headers(headers)
        result = json.loads(body)
        self.assertEqual(result["ticker"], "AAPL")

    def test_bad_inputs_fail_closed(self):
        cases = [
            ({}, 422),
            (None, 422),
            ({"ticker": None, "thesis": "观点"}, 422),
            ({"ticker": "AAPL", "thesis": ""}, 422),
            ({"ticker": "<SCRIPT>", "thesis": "观点"}, 422),
            ({"ticker": "AAPL", "thesis": "观点", "extra": True}, 422),
        ]
        for payload, expected in cases:
            with self.subTest(payload=payload):
                status, _, body = self.json_request(payload)
                self.assertEqual(status, expected)
                self.assertIn("error", json.loads(body))

    def test_media_type_size_and_malformed_json(self):
        status, _, _ = self.json_request({"ticker": "AAPL", "thesis": "观点"}, content_type="text/plain")
        self.assertEqual(status, 415)

        status, _, body = self.request(
            "POST",
            "/api/debate",
            b"{not-json}",
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 400)
        self.assertEqual(json.loads(body)["error"], "malformed JSON body")

        oversized = b"x" * 4097
        status, _, _ = self.request(
            "POST",
            "/api/debate",
            oversized,
            {"Content-Type": "application/json"},
        )
        self.assertEqual(status, 413)

    def test_head_and_options(self):
        status, headers, body = self.request("HEAD", "/")
        self.assertEqual(status, 200)
        self.assertEqual(body, b"")
        self.assert_security_headers(headers)

        status, headers, body = self.request("OPTIONS", "/")
        self.assertEqual(status, 204)
        self.assertEqual(body, b"")
        self.assertIn("POST", headers["Allow"])
        self.assert_security_headers(headers)

    def test_portal_routes_and_legacy_api(self):
        status, _, body = self.request("GET", "/")
        self.assertEqual(status, 200)
        self.assertIn("项目工作台", body.decode())
        self.assertIn('href="/reports/"', body.decode())
        self.assertNotIn("jd:stale", body.decode())
        status, _, body = self.request("GET", "/arena/")
        self.assertEqual(status, 200)
        self.assertIn("/arena/api/debate", body.decode())
        for path in ("/api/demo", "/arena/api/demo"):
            status, _, body = self.request("GET", path)
            self.assertEqual(status, 200)
            self.assertEqual(json.loads(body)["ticker"], "AAPL")
        body = json.dumps({"ticker": "AAPL", "thesis": "验证迁移后的演示接口。"})
        status, _, _ = self.request("POST", "/arena/api/debate", body.encode(), {"Content-Type": "application/json"})
        self.assertEqual(status, 200)

    def test_backend_cannot_serve_any_report_data(self):
        # nginx authenticates the shell; the backend has no data route at all.
        for path in ("/reports/data.json", "/reports/data.json?x=1", "/reports/../reports.json",
                     "/reports%2fdata.json", "/reports//data.json", "/reports.json", "/api/reports",
                     "/var/lib/project-portal/reports.json", "/.env", "/netdata.htpasswd"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)
        status, _, body = self.request("GET", "/reports/")
        self.assertEqual(status, 200)
        self.assertNotIn("jd:stale\",\"nng8:invalid", body.decode())

    def test_canonical_page_redirects(self):
        for path in ("/arena", "/reports"):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 308)
            self.assertEqual(headers["Location"], path + "/")
            self.assertEqual(body, b"")

if __name__ == "__main__":
    unittest.main()
