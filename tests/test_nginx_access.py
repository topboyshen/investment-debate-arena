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

    def test_netdata_is_public_read_only_and_origin_stays_private(self):
        netdata = self.location("location ~ ^/netdata/(?<ndpath>.*)$")
        self.assertIn('auth_basic off;', netdata)
        self.assertNotIn('auth_basic_user_file', netdata)
        self.assertIn('if ($netdata_public_blocked) { return 404; }', netdata)
        self.assertIn('if ($http_upgrade != "") { return 404; }', netdata)
        self.assertIn('if ($request_method !~ "^(GET|HEAD)$") { return 405; }', netdata)
        self.assertIn('limit_except GET { deny all; }', netdata)
        self.assertIn('limit_req zone=netdata_cloud_per_ip burst=100 nodelay;', netdata)
        self.assertIn('Cache-Control "no-store, max-age=0" always;', netdata)
        self.assertIn('proxy_set_header Authorization "";', netdata)
        self.assertIn("listen 127.0.0.1:18765 default_server;", self.config)
        self.assertIn("listen [::1]:18765 default_server;", self.config)
        self.assertIn("include /etc/nginx/private-subscriptions.conf;", self.config)

    def test_netdata_api_allowlist_rejects_control_and_encoded_paths(self):
        start = self.config.index('map $uri $netdata_public_blocked {')
        rules = []
        for line in self.config[start:].splitlines()[1:]:
            if line == '}':
                break
            if line.strip().startswith('~'):
                pattern, value = line.strip().rstrip(';').rsplit(' ', 1)
                flags = re.I if pattern.startswith('~*') else 0
                rules.append((re.compile(pattern[2:] if flags else pattern[1:], flags), value))

        self.assertIn('map $args $netdata_registry_blocked {\n    default 1;\n    "action=hello" 0;', self.config)

        def blocked(path, args=''):
            value = next((value for regex, value in rules if regex.search(path)), '0')
            return args != 'action=hello' if value == '$netdata_registry_blocked' else value == '1'

        self.assertFalse(blocked('/netdata/api/v1/registry', 'action=hello'))
        for args in ('', 'action=access', 'action=hello&action=delete', 'action=%68ello'):
            self.assertTrue(blocked('/netdata/api/v1/registry', args))

        for path in ['/netdata/', '/netdata/v3/index.html', '/netdata/api/v1/info',
                     '/netdata/api/v1/charts', '/netdata/api/v2/data', '/netdata/api/v3/settings',
                     '/netdata/host/localhost/api/v1/data', '/netdata/node/local/v3/api/v3/contexts']:
            with self.subTest(path=path):
                self.assertFalse(blocked(path))
        for path in ['/netdata/netdata.conf', '/netdata/v3/netdata.conf',
                     '/netdata/mcp', '/netdata/sse', '/netdata/v3/mcp',
                     '/netdata/host/local/sse', '/netdata/node/local/v2/mcp',
                     '/netdata/netdata.conf?x', '/netdata/v3/netdata.conf?x',
                     '/netdata/api/v1/manage/health', '/netdata/host/localhost/api/v1/manage/health',
                     '/netdata/v2/api/v3/config', '/netdata/node/local/api/v3/function',
                     '/netdata/api/v1/registry', '/netdata/api/v3/claim', '/netdata/api/v3/bearer_get_token',
                     '/netdata/api/v3/rtc_offer', '/netdata/api/v3/future_control', '/netdata/debug',
                     '/netdata/v3/host/local/exit', '/netdata/mirror', '/netdata/%61pi/v1/manage']:
            with self.subTest(path=path):
                self.assertTrue(blocked(path))

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
