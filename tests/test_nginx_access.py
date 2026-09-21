import re
import unittest
from pathlib import Path


class NginxAccessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = (
            Path(__file__).resolve().parents[1]
            / "nginx"
            / "investment-debate-arena.conf"
        ).read_text()

    def location(self, header):
        # Current locations contain no nested blocks. Anchor the closing brace
        # to the location indentation so another location cannot satisfy a test.
        match = re.search(
            r"(?ms)^    " + re.escape(header) + r" \{\n(.*?)^    \}",
            self.config,
        )
        self.assertIsNotNone(match, header)
        return match.group(1)

    def test_arena_is_public_but_rate_limited(self):
        arena = self.location("location /")
        self.assertRegex(arena, r"(?m)^\s*auth_basic off;\s*$")
        self.assertNotIn("auth_basic_user_file", arena)
        self.assertIn("limit_req zone=arena_per_ip burst=10 nodelay;", arena)
        self.assertIn("limit_conn arena_conn_per_ip 5;", arena)
        self.assertIn("proxy_pass http://127.0.0.1:18766;", arena)

    def test_netdata_stays_protected_and_origin_stays_private(self):
        netdata = self.location("location ~ ^/netdata/(?<ndpath>.*)$")
        self.assertIn('auth_basic "Netdata Monitoring";', netdata)
        self.assertIn("auth_basic_user_file /etc/nginx/netdata.htpasswd;", netdata)
        self.assertNotIn("auth_basic off;", netdata)
        self.assertIn("listen 127.0.0.1:18765 default_server;", self.config)
        self.assertIn("listen [::1]:18765 default_server;", self.config)
        self.assertIn("include /etc/nginx/private-subscriptions.conf;", self.config)

    def test_reports_are_public_read_only_and_not_cached(self):
        for header in ("location = /reports/data.json", "location ^~ /reports/"):
            block = self.location(header)
            self.assertIn('auth_basic off;', block)
            self.assertNotIn('auth_basic_user_file', block)
            self.assertIn('limit_req zone=arena_per_ip burst=10 nodelay;', block)
            self.assertIn('X-Robots-Tag "noindex, noarchive" always;', block)
            self.assertIn('Cache-Control "no-store, max-age=0" always;', block)
            self.assertIn('CDN-Cache-Control "no-store" always;', block)
            self.assertIn("Strict-Transport-Security", block)
        data = self.location("location = /reports/data.json")
        self.assertIn("alias /var/lib/project-portal/reports.json;", data)
        self.assertIn("disable_symlinks on;", data)
        self.assertIn("limit_except GET { deny all; }", data)
        self.assertIn("default_type application/json;", data)
        self.assertEqual(self.config.count("/var/lib/project-portal"), 1)
        self.assertNotRegex(self.config, r"(?:alias|root)\s+/opt/(?:mini-hermes|signal-gate)")

    def test_exporter_has_no_network_or_business_writes(self):
        unit = (Path(__file__).resolve().parents[1] / "systemd/project-portal-export.service").read_text()
        self.assertIn("PrivateNetwork=yes", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ReadWritePaths=/var/lib/project-portal", unit)
        self.assertIn("ProtectHome=yes", unit)
        self.assertNotIn("OnFailure", unit)  # this refresh job sends no alerts


if __name__ == "__main__":
    unittest.main()
