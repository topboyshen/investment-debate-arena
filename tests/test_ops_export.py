"""Public operations data contracts; no network or live systemd dependencies."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import stat
import tempfile
import types
import unittest
from unittest import mock


SPEC = importlib.util.spec_from_file_location(
    "ops_export", Path(__file__).resolve().parents[1] / "scripts/export_ops.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)

NOW = 1800516600
CHECKED = exporter.iso(NOW - 10)
RECENT_REQUEST_US = (NOW - 60) * 1_000_000
OLD_REQUEST_US = (NOW - 25 * 3600) * 1_000_000
# Public, deterministic test material, never an operational credential. Keep a
# full-length sensitive-looking value so redaction cannot pass on a short stub.
SECRET = hashlib.sha256(b"ops export offline sensitive fixture v1").hexdigest()
TCP_HEADER = "  sl  local_address rem_address   st\n"


def tcp_line(address, port, state="0A"):
    return " 0: %s:%04X 00000000:0000 %s 0 0 0\n" % (address, port, state)


class OpsExportTests(unittest.TestCase):
    def check(self, data, key="runtime", max_age=1500):
        return exporter.project_check(key, "Fixed label", data, NOW, max_age)

    def test_pi_request_incident_is_not_hidden_by_clear_runtime(self):
        runtime = self.check({"status": "clear", "updated_at": CHECKED})
        pi = self.check({"version": 1, "updated_at": CHECKED, "failure_streak": 2,
                         "last_success_us": 0, "watermark_us": OLD_REQUEST_US,
                         "incident": {"id": SECRET, "alert_sent": True}}, key="pi_requests")
        self.assertEqual(runtime["status"], "ok")
        self.assertEqual(pi["status"], "error")
        self.assertEqual(pi["sample_status"], "idle")
        self.assertNotIn(SECRET, json.dumps(pi))
        self.assertIn('pi_requests', {row[0] for row in exporter.CHECKS})

    def test_pi_no_traffic_is_unverified_not_healthy(self):
        data = {"version": 1, "updated_at": CHECKED, "failure_streak": 0,
                "last_success_us": 0, "watermark_us": 0, "incident": None}
        self.assertEqual(self.check(data, key="pi_requests")["status"], "unknown")
        self.assertEqual(self.check(data, key="pi_requests")["sample_status"], "unverified")
        data.update(failure_streak=1)
        self.assertEqual(self.check(data, key="pi_requests")["status"], "warning")
        data.update(failure_streak=0, last_success_us=RECENT_REQUEST_US,
                    watermark_us=RECENT_REQUEST_US)
        self.assertEqual(self.check(data, key="pi_requests")["status"], "ok")
        data['updated_at'] = exporter.iso(NOW - 1501)
        self.assertEqual(self.check(data, key="pi_requests")["status"], "stale")

    def test_pi_sample_window_is_independent_of_collector_freshness(self):
        data = {"version": 1, "updated_at": CHECKED, "failure_streak": 0,
                "last_success_us": OLD_REQUEST_US, "watermark_us": OLD_REQUEST_US,
                "incident": None, "seen_requests": {SECRET: OLD_REQUEST_US},
                "notification_history": [{"id": SECRET}], "token": SECRET}
        result = self.check(data, key="pi_requests")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["sample_status"], "idle")
        self.assertEqual(result["sample_window_seconds"], 24 * 3600)
        self.assertEqual(result["checked_at"], CHECKED)
        self.assertEqual(result["last_success_at"], exporter.iso(OLD_REQUEST_US / 1_000_000))
        self.assertEqual(result["last_result_at"], result["last_success_at"])
        self.assertIn('近 24 小时无已完成请求样本', result["issues"][0])
        self.assertNotIn(SECRET, json.dumps(result))
        data["watermark_us"] = RECENT_REQUEST_US  # e.g. cancellation; no new success
        result = self.check(data, key="pi_requests")
        self.assertEqual(result["status"], "unknown")
        self.assertEqual(result["sample_status"], "recent_without_success")
        self.assertEqual(result["last_success_at"], exporter.iso(OLD_REQUEST_US / 1_000_000))
        self.assertEqual(result["last_result_at"], exporter.iso(RECENT_REQUEST_US / 1_000_000))
        data["last_success_us"] = RECENT_REQUEST_US
        self.assertEqual(self.check(data, key="pi_requests")["sample_status"], "recent_success")
        self.assertEqual(self.check(data, key="pi_requests")["status"], "ok")

    def test_pi_old_unresolved_failure_is_not_erased_by_idle_window(self):
        data = {"version": 1, "updated_at": CHECKED, "failure_streak": 2,
                "last_success_us": 0, "watermark_us": OLD_REQUEST_US,
                "incident": {"id": SECRET, "alert_sent": True}}
        result = self.check(data, key="pi_requests")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["sample_status"], "idle")
        data.update(failure_streak=1, incident=None)
        self.assertEqual(self.check(data, key="pi_requests")["status"], "warning")
        data.update(failure_streak=0, watermark_us=(NOW + 120) * 1_000_000)
        invalid = self.check(data, key="pi_requests")
        self.assertEqual(invalid["status"], "unknown")
        self.assertIsNone(invalid["last_result_at"])

    def test_check_projection_exports_only_fixed_labels_not_private_details(self):
        self.assertEqual(len(SECRET), 64)
        self.assertRegex(SECRET, r"^[0-9a-f]{64}$")
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

    def test_notified_morning_issue_remains_visible_without_pending_codes(self):
        data = {"status": "issue", "updated_at": CHECKED, "pending_codes": {},
                "notified_codes": ["morning_data_quality"], "uncertain_codes": [],
                "notification_attempts": [{"status": "confirmed", "codes": [SECRET],
                                            "message": SECRET}], "details": [SECRET]}
        result = self.check(data, key="morning")
        self.assertEqual(result["status"], "error")
        self.assertEqual(result["issues"], [exporter.ISSUE_LABELS["morning_data_quality"]])
        self.assertNotIn(SECRET, json.dumps(result))

    def test_current_notification_codes_are_deduplicated_and_private_values_redacted(self):
        data = {"status": "pending", "updated_at": CHECKED,
                "pending_codes": {"arena_business_failures": 1},
                "notified_codes": ["arena_business_failures", SECRET],
                "uncertain_codes": ["subscription_mihomo_unreachable", SECRET],
                "notification_attempts": [{"status": "unknown", "codes": ["old_issue"],
                                            "message": "https://private.example/" + SECRET}]}
        result = self.check(data)
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["issues"], [exporter.ISSUE_LABELS["arena_business_failures"],
                                           '检测到一项异常（详见私有告警）',
                                           exporter.ISSUE_LABELS["subscription_mihomo_unreachable"]])
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn("private.example", json.dumps(result))

    def test_recovered_check_does_not_resurrect_notification_history(self):
        data = {"status": "clear", "updated_at": CHECKED, "pending_codes": {},
                "notified_codes": ["morning_data_quality"],
                "uncertain_codes": ["arena_business_failures"],
                "notification_attempts": [{"status": "confirmed",
                                            "codes": ["morning_data_quality"]}]}
        result = self.check(data)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["issues"], [])

    def test_malformed_notification_code_lists_do_not_leak_or_raise(self):
        data = {"status": "issue", "updated_at": CHECKED, "pending_codes": {},
                "notified_codes": SECRET, "uncertain_codes": [None, {}, 1, "morning_data_quality"]}
        result = self.check(data)
        self.assertEqual(result["issues"], [exporter.ISSUE_LABELS["morning_data_quality"]])
        self.assertNotIn(SECRET, json.dumps(result))

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

    def test_signal_gate_receiving_core_is_monitored_with_observed_systemd_status(self):
        self.assertIn("signal-gate", exporter.SERVICES)
        for active, sub in (("active", "running"), ("failed", "failed"),
                            ("inactive", "dead")):
            with self.subTest(active=active):
                raw = "\n".join(("Id=signal-gate.service", "LoadState=loaded",
                                  "ActiveState=" + active, "SubState=" + sub,
                                  "MemoryCurrent=17825792", "TasksCurrent=2",
                                  "NRestarts=0"))
                with mock.patch.object(exporter, "command", return_value=raw) as command:
                    rows = exporter.collect_services(NOW, None)
                self.assertIn("signal-gate.service", command.call_args.args[0])
                core = next(row for row in rows if row["id"] == "signal-gate")
                self.assertEqual(core["active_state"], active)
                self.assertEqual(core["sub_state"], sub)
                self.assertEqual(core["memory_bytes"], 17825792)
                self.assertEqual(core["tasks"], 2)
                self.assertEqual(core["restarts"], 0)

    def test_unobserved_signal_gate_is_unknown_even_when_review_is_active(self):
        raw = "Id=signal-gate-review.service\nActiveState=active\nSubState=running"
        with mock.patch.object(exporter, "command", return_value=raw):
            rows = exporter.collect_services(NOW, None)
        core = next(row for row in rows if row["id"] == "signal-gate")
        review = next(row for row in rows if row["id"] == "signal-gate-review")
        self.assertEqual(core["active_state"], "unknown")
        self.assertEqual(core["sub_state"], "unknown")
        self.assertIsNone(core["memory_bytes"])
        self.assertEqual(review["active_state"], "active")

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


class ControlledValidationTests(unittest.TestCase):
    VIX_HASHES = {'collector_sha256': hashlib.sha256(b'vix collector').hexdigest(),
                  'validator_sha256': hashlib.sha256(b'vix validator').hexdigest()}
    PI_HASHES = {'broker_sha256': hashlib.sha256(b'pi broker').hexdigest(),
                 'research_sha256': hashlib.sha256(b'pi research').hexdigest(),
                 'client_sha256': hashlib.sha256(b'pi client').hexdigest()}
    AUTH_METADATA = {'inode': 54321, 'mtime_ns': 1800000000000000000, 'size': 2345}

    def vix_receipt(self, **updates):
        result = {'version': 1, 'scope': 'vix_source', 'asset_code': 'VIX',
                  'status': 'pass', 'code': 'vix_source_valid', 'source_id': 'cboe',
                  'checked_at': CHECKED, 'expires_at': exporter.iso(NOW + 3500),
                  'source_as_of': exporter.iso(NOW - 600), 'ttl_seconds': 3600,
                  'implementation': self.VIX_HASHES}
        return {**result, **updates}

    def pi_receipt(self, **updates):
        result = {'version': 1, 'scope': 'pi_research_completion', 'model': 'xai/grok-4.6',
                  'status': 'pass', 'code': 'pi_probe_valid', 'checked_at': CHECKED,
                  'expires_at': exporter.iso(NOW + 3500), 'ttl_seconds': 3600,
                  'implementation': self.PI_HASHES, 'binding_auth': self.AUTH_METADATA}
        return {**result, **updates}

    def vix(self, data=None, *, current=None):
        with mock.patch.object(exporter, 'small_read', return_value=json.dumps(data if data is not None else self.vix_receipt())), \
             mock.patch.object(exporter, 'current_vix_implementation', return_value=current or self.VIX_HASHES):
            return exporter.vix_source_validation(NOW)

    def pi(self, data=None, *, current=None, authentication=None):
        with mock.patch.object(exporter, 'small_read', return_value=json.dumps(data if data is not None else self.pi_receipt())), \
             mock.patch.object(exporter, 'current_implementation', return_value=current or self.PI_HASHES), \
             mock.patch.object(exporter, 'current_pi_auth_metadata', return_value=authentication or self.AUTH_METADATA):
            return exporter.pi_controlled_validation(NOW)

    def test_vix_pass_exports_only_fixed_scope_label_and_times(self):
        result = self.vix()
        self.assertEqual(result, {'scope': 'vix_source', 'status': 'pass', 'code': 'vix_source_valid',
                                 'label': exporter.VIX_PROBE_LABELS['vix_source_valid'],
                                 'checked_at': CHECKED, 'expires_at': exporter.iso(NOW + 3500),
                                 'source_as_of': exporter.iso(NOW - 600)})
        encoded = json.dumps(result)
        for private in ('implementation', 'collector_sha256', 'validator_sha256', '/opt/',
                        *self.VIX_HASHES.values()):
            self.assertNotIn(private, encoded)

    def test_vix_future_stale_and_extended_evidence_cannot_pass(self):
        for changes in ({'checked_at': exporter.iso(NOW + 61)},
                        {'source_as_of': exporter.iso(NOW + 61)},
                        {'source_as_of': exporter.iso(NOW - 25 * 3600)},
                        {'expires_at': exporter.iso(NOW)},
                        {'expires_at': CHECKED},
                        {'expires_at': exporter.iso(NOW + 3600)},
                        {'source_as_of': exporter.iso(NOW - 23.5 * 3600)},
                        {'checked_at': '2026-10-08T12:00:00'},
                        {'source_as_of': None}):
            with self.subTest(changes=changes):
                self.assertEqual(self.vix(self.vix_receipt(**changes))['status'], 'unverified')

    def test_vix_short_source_freshness_window_can_reduce_receipt_lifetime(self):
        result = self.vix(self.vix_receipt(source_as_of=exporter.iso(NOW - 86300),
                                          expires_at=exporter.iso(NOW + 99)))
        self.assertEqual(result['status'], 'pass')

    def test_vix_schema_types_scope_source_and_code_combinations_fail_closed(self):
        for changes in ({'version': True}, {'version': 2}, {'ttl_seconds': True},
                        {'ttl_seconds': 3601}, {'ttl_seconds': 0}, {'ttl_seconds': '3600'},
                        {'scope': 'entire_morning'}, {'asset_code': 'SPX'},
                        {'source_id': 'yahoo_finance'}, {'source_id': 'source_unknown'},
                        {'status': []}, {'code': {}}, {'status': 'pass', 'code': 'vix_source_fetch_failed'},
                        {'status': 'fail', 'code': 'vix_source_valid'}, {'source_as_of': []},
                        {'secret': SECRET}):
            with self.subTest(changes=changes):
                result = self.vix(self.vix_receipt(**changes))
                self.assertEqual(result['status'], 'unverified')
                self.assertNotIn(SECRET, json.dumps(result))
        self.assertEqual(self.vix([])['status'], 'unverified')

    def test_vix_implementation_change_missing_hash_and_wrong_hash_type_invalidate_evidence(self):
        wrong = {**self.VIX_HASHES, 'collector_sha256': 'a' * 64}
        for bindings in ({}, {'collector_sha256': self.VIX_HASHES['collector_sha256']},
                         {**self.VIX_HASHES, 'validator_sha256': []}, wrong,
                         {**self.VIX_HASHES, 'validator_sha256': 'bad'},
                         {**self.VIX_HASHES, 'private_path': SECRET}):
            with self.subTest(bindings=bindings):
                self.assertEqual(self.vix(self.vix_receipt(implementation=bindings))['status'], 'unverified')
        self.assertEqual(self.vix(current=wrong)['status'], 'unverified')

    def test_vix_fetch_failure_is_a_valid_fail_without_claiming_unknown_source_healthy(self):
        result = self.vix(self.vix_receipt(status='fail', code='vix_source_fetch_failed',
                                         source_id='source_unknown', source_as_of=None))
        self.assertEqual(result['status'], 'fail')
        self.assertEqual(result['code'], 'vix_source_fetch_failed')
        unknown = self.vix(self.vix_receipt(status='fail', code='vix_source_quality_failed',
                                          source_id='source_unknown'))
        self.assertEqual(unknown['status'], 'unverified')
        self.assertEqual(unknown['code'], 'vix_source_unverified')

    def test_vix_probe_error_and_unknown_source_are_unverified(self):
        for changes in ({'status': 'error', 'code': 'vix_source_probe_error'},
                        {'status': 'error', 'code': 'vix_source_implementation_changed'},
                        {'status': 'unverified', 'code': 'vix_source_unverified', 'source_id': 'source_unknown'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.vix(self.vix_receipt(**changes))['status'], 'unverified')

    def test_missing_unreadable_duplicate_or_malformed_receipt_is_unverified(self):
        for method in (exporter.vix_source_validation, exporter.pi_controlled_validation):
            for raw in ('not-json', '[1,2]', '{"version":1,"version":1}'):
                with self.subTest(method=method.__name__, raw=raw), \
                     mock.patch.object(exporter, 'small_read', return_value=raw):
                    self.assertEqual(method(NOW)['status'], 'unverified')
            with mock.patch.object(exporter, 'small_read', side_effect=OSError('private location ' + SECRET)):
                result = method(NOW)
            self.assertEqual(result['status'], 'unverified')
            self.assertNotIn(SECRET, json.dumps(result))

    def test_receipt_read_requires_root_ownership_no_group_other_write_and_bound_size(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'receipt.json'
            source.write_text('{}')
            for owner, mode, accepted in ((0, 0o640, True), (0, 0o600, True),
                                           (1000, 0o640, False), (0, 0o660, False),
                                           (0, 0o646, False)):
                with self.subTest(owner=owner, mode=mode), \
                     mock.patch.object(exporter.os, 'fstat', return_value=types.SimpleNamespace(
                         st_mode=stat.S_IFREG | mode, st_uid=owner, st_size=2)):
                    if accepted:
                        self.assertEqual(exporter.small_read(source, maximum=16384, root_owned=True), '{}')
                    else:
                        with self.assertRaises(ValueError):
                            exporter.small_read(source, maximum=16384, root_owned=True)
            linked = Path(directory) / 'linked.json'
            linked.symlink_to(source)
            with self.assertRaises(OSError):
                exporter.small_read(linked, maximum=16384, root_owned=True)
            with mock.patch.object(exporter.os, 'fstat', return_value=types.SimpleNamespace(
                    st_mode=stat.S_IFREG | 0o640, st_uid=0, st_size=16385)):
                with self.assertRaises(ValueError):
                    exporter.small_read(source, maximum=16384, root_owned=True)

    def test_current_implementation_reads_only_fixed_root_owned_source_files(self):
        with mock.patch.object(exporter, 'small_read', return_value='known implementation') as read:
            result = exporter.current_implementation(exporter.PI_IMPLEMENTATION_FILES)
        self.assertEqual(result, dict.fromkeys(self.PI_HASHES, hashlib.sha256(b'known implementation').hexdigest()))
        self.assertEqual([call.args[0] for call in read.call_args_list], list(exporter.PI_IMPLEMENTATION_FILES.values()))
        for call in read.call_args_list:
            self.assertEqual(call.kwargs, {'maximum': 1024 * 1024, 'root_owned': True})

    def test_pi_fresh_pass_is_bounded_and_redacts_implementation_and_authentication_metadata(self):
        result = self.pi()
        self.assertEqual(result['status'], 'pass')
        self.assertEqual(result['scope'], 'pi_research_completion')
        self.assertEqual(result['model'], 'xai/grok-4.6')
        self.assertEqual(result['checked_at'], CHECKED)
        self.assertEqual(result['expires_at'], exporter.iso(NOW + 3500))
        encoded = json.dumps(result)
        for private in ('binding_auth', 'inode', 'mtime_ns', 'implementation',
                        'broker_sha256', 'research_sha256', 'client_sha256', '/opt/',
                        *self.PI_HASHES.values(), str(self.AUTH_METADATA['inode'])):
            self.assertNotIn(private, encoded)

    def test_pi_failures_and_internal_errors_have_fixed_status_code_labels(self):
        for code in ('auth_required', 'timeout', 'rate_limited', 'quota_exceeded',
                     'upstream_error', 'invalid_response'):
            with self.subTest(code=code):
                result = self.pi(self.pi_receipt(status='fail', code=code))
                self.assertEqual(result['status'], 'fail')
                self.assertEqual(result['label'], exporter.PI_PROBE_LABELS[code])
        for code in ('probe_error', 'busy'):
            with self.subTest(code=code):
                result = self.pi(self.pi_receipt(status='error', code=code))
                self.assertEqual(result['status'], 'unverified')

    def test_pi_expired_future_and_extended_receipts_are_unverified(self):
        for changes in ({'checked_at': exporter.iso(NOW + 61)}, {'expires_at': exporter.iso(NOW)},
                        {'expires_at': CHECKED}, {'expires_at': exporter.iso(NOW + 3600)},
                        {'checked_at': '2026-10-08T12:00:00'}, {'ttl_seconds': 0},
                        {'ttl_seconds': 3601}, {'ttl_seconds': True}, {'ttl_seconds': '3600'}):
            with self.subTest(changes=changes):
                self.assertEqual(self.pi(self.pi_receipt(**changes))['status'], 'unverified')

    def test_pi_schema_model_scope_and_code_status_mismatch_are_unverified(self):
        for changes in ({'version': True}, {'version': 2}, {'scope': 'pi_entire_business'},
                        {'model': 'another_model'}, {'status': []}, {'code': {}},
                        {'code': SECRET}, {'status': 'pass', 'code': 'auth_required'},
                        {'status': 'fail', 'code': 'pi_probe_valid'},
                        {'status': 'error', 'code': 'auth_required'}, {'private_value': SECRET}):
            with self.subTest(changes=changes):
                result = self.pi(self.pi_receipt(**changes))
                self.assertEqual(result['status'], 'unverified')
                self.assertNotIn(SECRET, json.dumps(result))

    def test_pi_changed_implementation_and_authentication_make_prior_pass_unverified(self):
        changed = {**self.PI_HASHES, 'research_sha256': 'a' * 64}
        self.assertEqual(self.pi(current=changed)['status'], 'unverified')
        for field in self.AUTH_METADATA:
            with self.subTest(field=field):
                changed = {**self.AUTH_METADATA, field: self.AUTH_METADATA[field] + 1}
                self.assertEqual(self.pi(authentication=changed)['status'], 'unverified')

    def test_pi_invalid_private_bindings_fail_closed(self):
        for changes in ({'implementation': {}}, {'implementation': {**self.PI_HASHES, 'client_sha256': []}},
                        {'binding_auth': {}}, {'binding_auth': {**self.AUTH_METADATA, 'inode': True}},
                        {'binding_auth': {**self.AUTH_METADATA, 'mtime_ns': 'private'}},
                        {'binding_auth': {**self.AUTH_METADATA, 'size': -1}},
                        {'binding_auth': {**self.AUTH_METADATA, 'inode': 0}}):
            with self.subTest(changes=changes):
                self.assertEqual(self.pi(self.pi_receipt(**changes))['status'], 'unverified')

    def test_pi_authentication_binding_is_metadata_only_and_rejects_symlinks(self):
        regular = types.SimpleNamespace(st_mode=stat.S_IFREG | 0o600,
                                        st_ino=54321, st_mtime_ns=1800000000000000000, st_size=2345)
        with mock.patch.object(Path, 'lstat', return_value=regular) as metadata, \
             mock.patch.object(exporter.os, 'open', side_effect=AssertionError('auth must not be opened')):
            self.assertEqual(exporter.current_pi_auth_metadata(), self.AUTH_METADATA)
        metadata.assert_called_once()
        with mock.patch.object(Path, 'lstat', return_value=types.SimpleNamespace(st_mode=stat.S_IFLNK | 0o777)):
            with self.assertRaises(ValueError):
                exporter.current_pi_auth_metadata()

    def collect_with_validation(self, *, pi_status='pass', vix_status='pass'):
        business = {'version': 1, 'status': 'clear', 'updated_at': CHECKED, 'failure_streak': 0,
                    'last_success_us': OLD_REQUEST_US, 'watermark_us': OLD_REQUEST_US, 'incident': None}
        morning = {'status': 'issue', 'updated_at': CHECKED,
                   'notified_codes': ['morning_data_quality'], 'pending_codes': {}}
        pi = {'scope': 'pi_research_completion', 'model': 'xai/grok-4.6', 'status': pi_status,
              'code': 'auth_required' if pi_status == 'fail' else 'pi_probe_valid',
              'label': exporter.PI_PROBE_LABELS['auth_required'] if pi_status == 'fail' else exporter.PI_PROBE_LABELS['pi_probe_valid'],
              'checked_at': exporter.iso(NOW - 5), 'expires_at': exporter.iso(NOW + 300)}
        vix = {'scope': 'vix_source', 'status': vix_status, 'code': 'vix_source_valid',
               'label': exporter.VIX_PROBE_LABELS['vix_source_valid'], 'checked_at': exporter.iso(NOW - 5),
               'expires_at': exporter.iso(NOW + 300), 'source_as_of': exporter.iso(NOW - 600)}
        def load(path):
            if path.endswith('/pi-requests.json'):
                return business
            if path.endswith('/morning.json'):
                return morning
            return {'status': 'clear', 'updated_at': CHECKED}
        with mock.patch.object(exporter, 'load_json', side_effect=load), \
             mock.patch.object(exporter, 'pi_controlled_validation', return_value=pi), \
             mock.patch.object(exporter, 'vix_source_validation', return_value=vix):
            return exporter.collect_checks(NOW), business, morning

    def test_morning_source_pass_does_not_clear_saved_report_issue_or_replace_historical_time(self):
        checks, _, morning = self.collect_with_validation()
        row = next(check for check in checks if check['id'] == 'morning')
        original = exporter.project_check('morning', row['label'], morning, NOW, 27 * 3600)
        for field in original:
            self.assertEqual(row[field], original[field])
        self.assertEqual(row['status'], 'error')
        self.assertEqual(row['source_validation']['status'], 'pass')

    def test_pi_controlled_pass_never_fabricates_business_sample_success(self):
        checks, business, _ = self.collect_with_validation(pi_status='pass')
        row = next(check for check in checks if check['id'] == 'pi_requests')
        original = exporter.project_check('pi_requests', row['label'], business, NOW, 1500)
        for field in original:
            self.assertEqual(row[field], original[field])
        self.assertEqual(row['status'], 'unknown')
        self.assertEqual(row['sample_status'], 'idle')
        self.assertEqual(row['controlled_validation']['status'], 'pass')

    def test_pi_controlled_fail_raises_error_with_fixed_label_and_preserves_business_evidence(self):
        checks, business, _ = self.collect_with_validation(pi_status='fail')
        row = next(check for check in checks if check['id'] == 'pi_requests')
        original = exporter.project_check('pi_requests', row['label'], business, NOW, 1500)
        self.assertEqual(row['status'], 'error')
        self.assertEqual(row['issues'], original['issues'] + [exporter.PI_PROBE_LABELS['auth_required']])
        for field in ('checked_at', 'sample_status', 'last_success_at', 'last_result_at', 'sample_window_seconds'):
            self.assertEqual(row[field], original[field])
        self.assertEqual(business['watermark_us'], OLD_REQUEST_US)
        self.assertEqual(business['failure_streak'], 0)


if __name__ == "__main__":
    unittest.main()
