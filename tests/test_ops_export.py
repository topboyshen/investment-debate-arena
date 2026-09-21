"""Public operations data contracts; no network or live systemd dependencies."""
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "ops_export", Path(__file__).resolve().parents[1] / "scripts/export_ops.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)

NOW = 1800516600
CHECKED = exporter.iso(NOW - 10)
SECRET = "PRIVATE_SENTINEL_DO_NOT_EXPORT"
TCP_HEADER = "  sl  local_address rem_address   st\n"


def tcp_line(address, port, state="0A"):
    return " 0: %s:%04X 00000000:0000 %s 0 0 0\n" % (address, port, state)


class OpsExportTests(unittest.TestCase):
    def check(self, data, key="runtime", max_age=1500):
        return exporter.project_check(key, "Fixed label", data, NOW, max_age)

    def test_check_projection_exports_only_fixed_labels_not_private_details(self):
        data = {"status": "clear", "updated_at": CHECKED,
                "pending_codes": {"arena_business_failures": 2, SECRET: 3},
                "details": [SECRET, "https://private.example/sub?token=" + SECRET],
                "message": "198.51.100.84 " + SECRET, "token": SECRET}
        result = self.check(data)
        self.assertEqual(result["status"], "warning")
        self.assertIn(exporter.ISSUE_LABELS["arena_business_failures"], result["issues"])
        self.assertEqual(len(result["issues"]), 2)
        self.assertEqual(set(result), {"id", "label", "status", "checked_at", "issues"})
        encoded = json.dumps(result)
        for raw in (SECRET, "198.51.100.84", "private.example", "token"):
            self.assertNotIn(raw, encoded)

    def test_check_state_and_freshness_do_not_misrepresent_missing_evidence(self):
        for data, expected in (
            ({}, "unknown"),
            ({"status": "clear", "updated_at": CHECKED}, "ok"),
            ({"status": "pending", "updated_at": CHECKED}, "warning"),
            ({"status": "alert", "updated_at": CHECKED}, "error"),
            ({"status": "issue", "updated_at": CHECKED}, "error"),
            ({"status": "unexpected", "updated_at": CHECKED}, "unknown"),
            ({"status": "clear", "updated_at": "2026-09-21T15:00:00"}, "unknown"),
            ({"status": "clear", "updated_at": exporter.iso(NOW + 120)}, "unknown"),
            ({"status": "clear", "updated_at": exporter.iso(NOW - 1501)}, "stale"),
        ):
            with self.subTest(data=data):
                self.assertEqual(self.check(data)["status"], expected)

    def test_drift_pending_count_overrides_previous_clear_state(self):
        result = self.check({"last_status": "clear", "updated_at": CHECKED,
                             "pending_count": 1, "pending_details": [SECRET]}, key="config_drift")
        self.assertEqual(result["status"], "warning")
        self.assertTrue(result["issues"])
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(self.check({"last_status": "clear", "updated_at": CHECKED,
                                    "pending_count": 0}, key="config_drift")["status"], "ok")
        self.assertEqual(self.check({"last_status": "drift", "updated_at": CHECKED,
                                    "pending_count": 1}, key="config_drift")["status"], "error")

    def test_service_fields_are_fixed_and_missing_service_is_unknown(self):
        raw = "\n".join(("Id=sing-box.service", "LoadState=loaded", "ActiveState=active",
                          "SubState=running", "MemoryCurrent=1048576", "MemoryMax=infinity",
                          "CPUUsageNSec=2500000000", "TasksCurrent=3", "NRestarts=1",
                          "ExecMainStartTimestampMonotonic=10000000",
                          "ControlGroup=/system.slice/../" + SECRET,
                          "Description=" + SECRET, "Environment=" + SECRET))
        with mock.patch.object(exporter, "command", return_value=raw), \
             mock.patch.object(exporter, "small_read", side_effect=AssertionError("must not read arbitrary cgroup")):
            rows = exporter.collect_services(NOW, 40)
        singbox = next(row for row in rows if row["id"] == "sing-box")
        self.assertEqual(singbox["active_state"], "active")
        self.assertEqual(singbox["memory_bytes"], 1048576)
        self.assertEqual(singbox["cpu_seconds"], 2.5)
        self.assertTrue(singbox["memory_limit_unlimited"])
        self.assertIsNone(singbox["memory_limit_bytes"])
        self.assertEqual(singbox["uptime_seconds"], 30)
        absent = next(row for row in rows if row["id"] == "mtg")
        self.assertEqual(absent["active_state"], "unknown")
        self.assertIsNone(absent["memory_bytes"])
        self.assertNotIn(SECRET, json.dumps(rows))
        self.assertNotIn("ControlGroup", json.dumps(rows))

    def test_invalid_service_numbers_and_enums_are_not_public_text(self):
        raw = "\n".join(("Id=mtg.service", "ActiveState=" + SECRET, "SubState=" + SECRET,
                          "MemoryCurrent=-1", "MemoryMax=18446744073709551615",
                          "CPUUsageNSec=NaN", "TasksCurrent=bad", "NRestarts=-1"))
        with mock.patch.object(exporter, "command", return_value=raw):
            row = next(item for item in exporter.collect_services(NOW, None) if item["id"] == "mtg")
        self.assertEqual(row["active_state"], "unknown")
        self.assertEqual(row["sub_state"], "unknown")
        for field in ("memory_bytes", "memory_limit_bytes", "cpu_seconds", "tasks", "restarts", "started_at"):
            self.assertIsNone(row[field])
        self.assertNotIn(SECRET, json.dumps(row))

    def test_rates_use_same_boot_window_and_same_network_interfaces(self):
        before = {"monotonic": 100, "boot_id": "boot-A", "cpu_total": 1000,
                  "cpu_idle": 600, "interfaces": ["eth0"], "rx": 1000, "tx": 2000}
        after = {**before, "monotonic": 160, "cpu_total": 1200, "cpu_idle": 700,
                 "rx": 7000, "tx": 5000}
        result = exporter.rates(after, before)
        self.assertEqual(result, {"cpu_percent": 50, "network_rx_bytes_per_second": 100,
                                  "network_tx_bytes_per_second": 50})
        for change in ({"boot_id": "boot-B"}, {"monotonic": 100}, {"monotonic": 1000}, {"boot_id": ""}):
            with self.subTest(change=change):
                self.assertTrue(all(value is None for value in exporter.rates({**after, **change}, before).values()))
        changed_device = exporter.rates({**after, "interfaces": ["eth1"]}, before)
        self.assertEqual(changed_device["cpu_percent"], 50)
        self.assertIsNone(changed_device["network_rx_bytes_per_second"])
        self.assertIsNone(changed_device["network_tx_bytes_per_second"])

    def test_rates_reset_regressing_counters_instead_of_negative_usage(self):
        before = {"monotonic": 100, "boot_id": "boot-A", "cpu_total": 1000,
                  "cpu_idle": 600, "interfaces": ["eth0"], "rx": 1000, "tx": 2000}
        after = {**before, "monotonic": 160, "cpu_total": 900, "cpu_idle": 500,
                 "rx": 100, "tx": 200}
        self.assertTrue(all(value is None for value in exporter.rates(after, before).values()))

    def test_subscriptions_project_aggregate_fields_without_urls_or_identifiers(self):
        message = ("business_health mode=subscriptions status=clear "
                   "sub_iphone_ok=true sub_shadowrocket_ok=true sub_mihomo_download=ok "
                   "sub_mihomo_nodes=reachable sub_mihomo_check=tcp_only "
                   "sub_mihomo_endpoints=1 sub_mihomo_reachable=1 "
                   "url=https://private.example/sub?token=" + SECRET + " ip=198.51.100.84")
        result = exporter.subscription_projection(message, CHECKED, NOW)
        self.assertEqual(len(result), 3)
        mihomo = next(row for row in result if row["id"] == "mihomo")
        self.assertEqual(mihomo["download"], "ok")
        self.assertEqual(mihomo["nodes"], "reachable")
        self.assertEqual(mihomo["check"], "tcp_only")
        self.assertEqual(mihomo["endpoints"], 1)
        self.assertEqual(mihomo["reachable"], 1)
        for raw in (SECRET, "198.51.100.84", "private.example", "https://"):
            self.assertNotIn(raw, json.dumps(result))

    def test_subscription_unverified_and_expired_data_are_not_success(self):
        result = exporter.subscription_projection(
            "sub_mihomo_download=ok sub_mihomo_nodes=unverified sub_mihomo_check=tcp_only "
            "sub_mihomo_endpoints=0 sub_mihomo_reachable=0", CHECKED, NOW)
        mihomo = next(row for row in result if row["id"] == "mihomo")
        self.assertEqual(mihomo["nodes"], "unverified")
        self.assertEqual(mihomo["check"], "tcp_only")
        failed = exporter.subscription_projection("sub_iphone_ok=false", CHECKED, NOW)[0]
        self.assertEqual(failed["overall"], "error")
        self.assertNotEqual(failed["download"], "ok")
        self.assertNotEqual(failed["format"], "ok")
        for timestamp in (None, "invalid", exporter.iso(NOW - 2701), exporter.iso(NOW + 1)):
            with self.subTest(timestamp=timestamp):
                self.assertEqual(exporter.subscription_projection("sub_mihomo_ok=true", timestamp, NOW), [])

    def test_subscription_journal_order_cannot_select_an_older_result(self):
        old = json.dumps({'MESSAGE': 'business_health mode=subscriptions sub_mihomo_ok=false',
                          '__REALTIME_TIMESTAMP': str((NOW - 60) * 1000000)})
        new = json.dumps({'MESSAGE': 'business_health mode=subscriptions sub_mihomo_ok=true',
                          '__REALTIME_TIMESTAMP': str((NOW - 10) * 1000000)})
        for rows in ((old, new), (new, old)):
            with mock.patch.object(exporter, 'command', return_value='\n'.join(rows)):
                latest = next(row for row in exporter.collect_subscriptions(NOW) if row['id'] == 'mihomo')
            self.assertEqual(latest['overall'], 'ok')
            self.assertEqual(latest['checked_at'], CHECKED)

    def test_listeners_are_fixed_ports_scope_only_and_ignore_established(self):
        raw = TCP_HEADER + tcp_line("00000000", 8443) + tcp_line("0100007F", 19999)
        raw += tcp_line("00000000", 9443, "01") + tcp_line("00000000", 52022)
        rows = exporter.listener_rows([raw, TCP_HEADER])
        self.assertEqual({row["port"] for row in rows}, {8443, 9443, 18765, 19999})
        by_id = {row["id"]: row for row in rows}
        self.assertEqual(by_id["sing-box"]["scope"], "public")
        self.assertEqual(by_id["netdata"]["scope"], "loopback")
        self.assertEqual(by_id["mtg"]["state"], "not_listening")
        self.assertNotIn("0100007F", json.dumps(rows))
        self.assertNotIn("local_address", json.dumps(rows))

    def test_explicit_bound_addresses_are_classified_without_publishing_them(self):
        # Linux proc IPv4 is little endian; IPv6 reverses each 32-bit word.
        fixtures = (("08080808", "public"), ("0100000A", "private"),
                    ("00000000000000000000000001000000", "loopback"),
                    ("60480020000060480000000088880000", "public"))
        for address, scope in fixtures:
            with self.subTest(scope=scope, family=len(address)):
                rows = exporter.listener_rows([TCP_HEADER + tcp_line(address, 8443), TCP_HEADER])
                row = next(row for row in rows if row["id"] == "sing-box")
                self.assertEqual(row["scope"], scope)
                self.assertEqual(row["state"], "listening")
                self.assertNotIn(address, json.dumps(rows))

    def test_unreadable_listener_family_cannot_prove_absence(self):
        self.assertTrue(all(row["state"] == "unknown" for row in exporter.listener_rows([None, None])))
        self.assertTrue(all(row["state"] == "unknown" for row in exporter.listener_rows([TCP_HEADER, None])))
        raw = TCP_HEADER + tcp_line("00000000", 8443)
        self.assertEqual(next(row for row in exporter.listener_rows([raw, None])
                              if row["id"] == "sing-box")["state"], "listening")

    def test_small_read_refuses_symlinks_and_oversized_input(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            source = root / "data"
            source.write_text("plain")
            self.assertEqual(exporter.small_read(source), "plain")
            linked = root / "link"
            linked.symlink_to(source)
            with self.assertRaises(OSError):
                exporter.small_read(linked)
            self.assertEqual(exporter.load_json(linked), {})
            with self.assertRaises(ValueError):
                exporter.small_read(source, maximum=2)
            source.write_text("[1,2]")
            self.assertEqual(exporter.load_json(source), {})

    def test_mtg_aggregates_connections_and_directional_traffic_not_raw_labels(self):
        raw = '\n'.join((
            '# HELP mtg_client_connections client IP should remain private',
            'mtg_client_connections{ip="198.51.100.84",fixture="' + SECRET + '"} 2',
            'mtg_client_connections{ip="198.51.100.85"} 3',
            'mtg_telegram_connections{dc="1"} 1',
            'mtg_telegram_connections{dc="2"} 4',
            'mtg_telegram_traffic{dc="1",direction="to_client"} 1024',
            'mtg_telegram_traffic{direction="to_client",dc="2"} 2048',
            'mtg_telegram_traffic{direction="from_client",ip="198.51.100.84"} 100',
            'mtg_telegram_traffic{direction="from_client"} 200',
            'mtg_replay_attacks 7', 'mtg_concurrency_limited 8', 'mtg_domain_fronting 9',
            'mtg_secret_connections{key="' + SECRET + '"} 999',
            'mtg_telegram_traffic{direction="unknown"} 999',
            'mtg_client_connections -2', 'mtg_client_connections NaN',
        ))
        result = exporter.mtg_projection(raw, NOW)
        self.assertEqual(result, {"collected_at": exporter.iso(NOW), "client_connections": 5,
                                  "telegram_connections": 5, "traffic_to_client_bytes": 3072,
                                  "traffic_from_client_bytes": 300, "replay_attacks": 7,
                                  "concurrency_limited": 8, "domain_fronting": 9})
        for prohibited in (SECRET, "198.51.100.84", "198.51.100.85", "secret_connections"):
            self.assertNotIn(prohibited, json.dumps(result))
        self.assertEqual(exporter.mtg_projection("unrecognized text " + SECRET, NOW),
                         {"collected_at": exporter.iso(NOW)})

    def test_public_private_modes_and_replace_failure_preserve_snapshot(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            public = root / "ops.json"
            private = root / "ops-private.json"
            exporter.atomic_json(public, {"public": 1}, 0o640, os.getgid())
            exporter.atomic_json(private, {"private": SECRET}, 0o600, os.getgid())
            self.assertEqual(stat.S_IMODE(public.stat().st_mode), 0o640)
            self.assertEqual(stat.S_IMODE(private.stat().st_mode), 0o600)
            before = public.read_bytes()
            with mock.patch.object(exporter.os, "replace", side_effect=OSError("synthetic")):
                with self.assertRaises(OSError):
                    exporter.atomic_json(public, {"public": 2}, 0o640, os.getgid())
            self.assertEqual(public.read_bytes(), before)
            self.assertEqual(list(root.glob(".ops-*")), [])


if __name__ == "__main__":
    unittest.main()
