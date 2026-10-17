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

    def test_canonical_redirects_are_absolute_https_without_port(self):
        # A relative `return 308 /x/;` makes nginx build http://host:18765/x/
        # from its own Tunnel-only listener; always emit https://$host/... .
        for path in ("/reports", "/ops", "/netdata"):
            with self.subTest(path=path):
                block = self.location("location = " + path)
                self.assertRegex(block, r"(?m)^\s*return 308 https://\$host" + re.escape(path) + r"/;\s*$")
        targets = re.findall(r"return 30[1278] (\S+);", self.config)
        self.assertGreaterEqual(len(targets), 4)
        for target in targets:
            with self.subTest(target=target):
                self.assertTrue(target.startswith("https://$host"), target)
                self.assertNotRegex(target, r"^https?://[^/]*:[0-9]+")

    def test_favicon_ico_redirects_to_shared_svg(self):
        block = self.location("location = /favicon.ico")
        self.assertRegex(block, r"(?m)^\s*return 308 https://\$host/favicon\.svg\?v=1;\s*$")

    def test_proxied_pages_send_a_single_cache_control(self):
        for header in ("location ^~ /ops/", "location ^~ /reports/"):
            with self.subTest(location=header):
                block = self.location(header)
                self.assertIn("proxy_hide_header Cache-Control;", block)
                self.assertEqual(len(re.findall(r"(?m)^\s*add_header Cache-Control ", block)), 1)
                self.assertIn('add_header Cache-Control "no-store, max-age=0" always;', block)

    def test_arena_log_records_path_only_and_redacts_private_paths(self):
        fmt = re.search(r"(?s)log_format arena_safe (.*?);\n", self.config).group(1)
        self.assertIn("uri=$arena_log_uri", fmt)
        for forbidden in ("$request_uri", "$request ", "$args", "$query_string", "$remote_addr",
                          "$binary_remote_addr", "$http_", "$realip", "$uri "):
            self.assertNotIn(forbidden, fmt + " ")
        body = re.search(r"(?s)map \$uri \$arena_log_uri \{\n(.*?)\n\}", self.config).group(1)
        rules = []
        for line in body.splitlines():
            line = line.strip().rstrip(";")
            if line.startswith('"~'):
                pattern, value = line[2:].split('" "', 1)
                rules.append((re.compile(pattern), value.rstrip('"')))
        self.assertIn("default $uri", body)

        def logged(uri):
            return next((value for regex, value in rules if regex.search(uri)), uri)

        for uri in ("/subscriptions/" + "A" * 43 + "/sb.json", "/subscriptions/x", "/subscriptions",
                    "/" + "a1" * 16 + "/sb.json", "/netdata/" + "b" * 24):
            with self.subTest(uri=uri):
                self.assertTrue(logged(uri).startswith(("/subscriptions/[redacted]", "[redacted")))
        for uri in ("/", "/ops/", "/reports/data.json", "/arena/api/debate", "/netdata/api/v1/info"):
            with self.subTest(uri=uri):
                self.assertEqual(logged(uri), uri)

    def test_private_subscription_locations_never_use_arena_log(self):
        private = Path("/etc/nginx/private-subscriptions.conf")
        try:
            text = private.read_text()
        except OSError:
            self.skipTest("private subscription file is root-only on the host")
        blocks = re.findall(r"(?ms)^location [^{]*\{\n(.*?)^\}", text)
        self.assertGreater(len(blocks), 0)
        for index, block in enumerate(blocks):
            with self.subTest(block=index):
                self.assertRegex(block, r"(?m)^\s*access_log (off|\S+ subscription_safe);")

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
        self.assertEqual(self.config.count("/var/lib/project-portal"), 2)
        self.assertNotRegex(self.config, r"(?:alias|root)\s+/opt/(?:mini-hermes|signal-gate)")

    def test_exporter_has_no_network_or_business_writes(self):
        unit = (Path(__file__).resolve().parents[1] / "systemd/project-portal-export.service").read_text()
        self.assertIn("PrivateNetwork=yes", unit)
        self.assertIn("ProtectSystem=strict", unit)
        self.assertIn("ReadWritePaths=/var/lib/project-portal", unit)
        self.assertIn("ProtectHome=yes", unit)
        self.assertNotIn("OnFailure", unit)  # this refresh job sends no alerts

    def test_ops_snapshot_is_exact_read_only_and_private_sampler_not_served(self):
        for header in ("location = /ops/data.json", "location ^~ /ops/"):
            block = self.location(header)
            self.assertIn('auth_basic off;', block)
            self.assertIn('limit_except GET { deny all; }', block)
            self.assertIn('Cache-Control "no-store, max-age=0" always;', block)
            self.assertIn('X-Robots-Tag "noindex, noarchive" always;', block)
        data = self.location('location = /ops/data.json')
        self.assertIn('alias /var/lib/project-portal/ops.json;', data)
        self.assertIn('disable_symlinks on;', data)
        self.assertNotIn('ops-private', self.config)
        unit = (Path(__file__).resolve().parents[1] / 'systemd/project-portal-ops.service').read_text()
        for guard in ('ProtectSystem=strict', 'ProtectHome=yes', 'IPAddressDeny=any',
                      'IPAddressAllow=localhost', 'ReadWritePaths=/var/lib/project-portal'):
            self.assertIn(guard, unit)
        self.assertNotIn('OnFailure', unit)


if __name__ == "__main__":
    unittest.main()
