import http.client
import json
import sys
import threading
import unittest
from html.parser import HTMLParser
import xml.etree.ElementTree as ET
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from server import Handler, SECURITY_HEADERS
from portal_pages import HOME_PAGE, REPORTS_PAGE
from branding import FAVICON_SVG


class ServerTests(unittest.TestCase):
    def test_report_copy_matches_anonymous_access(self):
        self.assertNotIn("登录后阅读", HOME_PAGE + REPORTS_PAGE)
        self.assertNotIn("日报中心使用现有 Netdata 账号登录", HOME_PAGE)
        self.assertIn("公开阅读", REPORTS_PAGE)
        self.assertIn("credentials:'omit'", REPORTS_PAGE)
        self.assertIn("Netdata 监控也可免登录", HOME_PAGE)
        self.assertNotIn("独立登录", HOME_PAGE)

    def test_all_portal_pages_reference_the_same_favicon(self):
        class Icons(HTMLParser):
            def __init__(self):
                super().__init__()
                self.icons = []

            def handle_starttag(self, tag, attrs):
                attributes = dict(attrs)
                if tag == "link" and "icon" in attributes.get("rel", "").split():
                    self.icons.append(attributes)

        for path in ("/", "/reports/", "/ops/", "/arena/"):
            with self.subTest(path=path):
                status, _, body = self.request("GET", path)
                self.assertEqual(status, 200)
                parser = Icons()
                parser.feed(body.decode().split("</head>", 1)[0])
                self.assertEqual(len(parser.icons), 1)
                self.assertEqual(parser.icons[0]["href"], "/favicon.svg?v=1")
                self.assertEqual(parser.icons[0]["type"], "image/svg+xml")

    def test_favicon_is_static_svg_with_correct_get_and_head_headers(self):
        for path in ("/favicon.svg", "/favicon.svg?v=1"):
            with self.subTest(path=path):
                status, headers, body = self.request("GET", path)
                self.assertEqual(status, 200)
                self.assertEqual(body, FAVICON_SVG)
                self.assertEqual(headers["Content-Type"], "image/svg+xml")
                self.assertEqual(int(headers["Content-Length"]), len(body))
                self.assertEqual(headers["Cache-Control"], "public, max-age=3600")
                self.assert_security_headers(headers)
                head_status, head_headers, head_body = self.request("HEAD", path)
                self.assertEqual(head_status, 200)
                self.assertEqual(head_body, b"")
                for key in ("Content-Type", "Content-Length", "Cache-Control"):
                    self.assertEqual(head_headers[key], headers[key])
        svg = ET.fromstring(FAVICON_SVG)
        self.assertEqual(svg.attrib["viewBox"], "0 0 64 64")
        for element in svg.iter():
            self.assertIn(element.tag, {"{http://www.w3.org/2000/svg}" + tag for tag in ("svg", "rect", "path")})
            self.assertFalse(any("href" in attr or attr.startswith("on") for attr in element.attrib))

    def test_favicon_does_not_open_an_asset_directory_or_write_route(self):
        for method, path in (("POST", "/favicon.svg"), ("GET", "/favicon.svg/extra"),
                             ("GET", "/app/branding.py"), ("GET", "/.env")):
            with self.subTest(method=method, path=path):
                self.assertEqual(self.request(method, path)[0], 404)

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
        # nginx serves only the public snapshot; the backend has no data route.
        for path in ("/reports/data.json", "/reports/data.json?x=1", "/reports/../reports.json",
                     "/reports%2fdata.json", "/reports//data.json", "/reports.json", "/api/reports",
                     "/var/lib/project-portal/reports.json", "/.env", "/netdata.htpasswd"):
            with self.subTest(path=path):
                status, _, _ = self.request("GET", path)
                self.assertEqual(status, 404)
        status, _, body = self.request("GET", "/reports/")
        self.assertEqual(status, 200)
        self.assertNotIn("jd:stale\",\"nng8:invalid", body.decode())

    def test_head_matches_get_status_and_headers_without_body(self):
        for path in ("/", "/arena", "/arena/", "/reports", "/reports/", "/ops", "/ops/",
                     "/api/demo", "/arena/api/demo", "/healthz", "/readyz", "/favicon.svg",
                     "/no-such-path", "/reports/data.json", "/ops?x=1"):
            with self.subTest(path=path):
                get_status, get_headers, get_body = self.request("GET", path)
                head_status, head_headers, head_body = self.request("HEAD", path)
                self.assertEqual(head_status, get_status)
                self.assertEqual(head_body, b"")
                get_headers.pop("Date", None)
                head_headers.pop("Date", None)
                if path.endswith("api/demo") or path == "/readyz":
                    # Dynamic payload (generated_at); only the length may differ.
                    self.assertTrue(int(head_headers.pop("Content-Length")) > 0)
                    get_headers.pop("Content-Length")
                else:
                    self.assertEqual(int(get_headers["Content-Length"]), len(get_body))
                self.assertEqual(head_headers, get_headers)

    def test_canonical_page_redirects(self):
        for path in ("/arena", "/reports", "/ops"):
            status, headers, body = self.request("GET", path)
            self.assertEqual(status, 308)
            self.assertEqual(headers["Location"], path + "/")
            self.assertEqual(body, b"")

if __name__ == "__main__":
    unittest.main()
