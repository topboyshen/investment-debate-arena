import hashlib
import datetime as dt
import importlib.util
import json
import os
from pathlib import Path
from types import SimpleNamespace
import sqlite3
import stat
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location(
    "report_export", Path(__file__).resolve().parents[1] / "scripts/export_reports.py")
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)


class ReportExportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.db = self.root / "memory.db"
        self.gate = self.root / "out"
        self.gate.mkdir()
        (self.gate / "delivery").mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def database(self, records=None, *, wal=False):
        connection = sqlite3.connect(self.db)
        if wal:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA wal_autocheckpoint=0")
        connection.execute("CREATE TABLE market_reports (report_date TEXT, report_text TEXT, created_at TEXT, updated_at TEXT)")
        connection.execute("CREATE TABLE private_chats (body TEXT)")
        connection.execute("INSERT INTO private_chats VALUES ('DO_NOT_EXPORT_PRIVATE_CHAT')")
        for report_date, body in records or [("2026-09-19", "已保存晨报")]:
            connection.execute("INSERT INTO market_reports VALUES (?, ?, ?, ?)",
                               (report_date, body, "2026-09-19T08:00:00+08:00", "2026-09-19T08:01:00+08:00"))
        connection.commit()
        return connection

    def report(self, *, date="2026-09-21", body="真实日报\n", issues=None, status="confirmed"):
        raw = body.encode("utf-8")
        path = self.gate / ("daily-" + date + ".md")
        path.write_bytes(raw)
        receipt = {
            "schema_version": 1, "report_date": date, "status": status,
            "content_sha256": hashlib.sha256(raw).hexdigest(),
            "issues": issues or [],
            "generated_at": "2026-09-21T08:15:00+08:00",
            "updated_at": "2026-09-21T08:15:10+08:00",
            "confirmed_at": "2026-09-21T08:15:10+08:00",
            "parts": [{"index": 1, "status": "confirmed", "message_id": 17}],
        }
        target = self.gate / "delivery" / (date + ".json")
        target.write_text(json.dumps(receipt), encoding="utf-8")
        return path, target, receipt

    def test_live_wal_saved_report_is_not_send_confirmation(self):
        connection = self.database(wal=True)
        try:
            self.assertTrue(Path(str(self.db) + "-wal").exists())
            payload = exporter.build_export(self.db, self.gate)
            record = payload["reports"][0]
            self.assertEqual(record["delivery_status"], "unknown")
            self.assertEqual(record["time_label"], "首次保存")
            self.assertEqual(record["report_date"], "2026-09-19")
            self.assertEqual(payload["sources"][0]["state"], "ok")
            self.assertIn("周日、周一", payload["sources"][0]["note"])
            self.assertNotIn("DO_NOT_EXPORT_PRIVATE_CHAT", json.dumps(payload))
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM market_reports").fetchone()[0], 1)
        finally:
            connection.close()

    def test_confirmed_delivery_does_not_hide_quality_issues(self):
        self.report(issues=["jd:stale", "nng8:invalid"])
        records, source = exporter.load_gate(self.gate)
        self.assertEqual(records[0]["delivery_status"], "confirmed")
        self.assertEqual(records[0]["quality_issues"], ["jd:stale", "nng8:invalid"])
        self.assertEqual(source["state"], "partial")

    def test_receipt_hash_compares_original_bytes(self):
        report, _, _ = self.report()
        report.write_bytes(report.read_bytes() + b"\n")
        record = exporter.load_gate(self.gate)[0][0]
        self.assertEqual(record["delivery_status"], "unverified")
        self.assertIn("portal:content_mismatch", record["quality_issues"])
        self.assertEqual(record["time_label"], "文件更新时间")

    def test_missing_invalid_and_partial_receipts_never_confirm(self):
        _, path, receipt = self.report()
        for replacement in (None, "{broken", {**receipt, "report_date": "2026-09-20"},
                            {**receipt, "schema_version": 2}, {**receipt, "parts": []},
                            {**receipt, "parts": [{"index": 0, "status": "unknown", "message_id": None}]}):
            with self.subTest(replacement=replacement):
                if replacement is None:
                    path.unlink(missing_ok=True)
                else:
                    path.write_text(replacement if isinstance(replacement, str) else json.dumps(replacement))
                record = exporter.load_gate(self.gate)[0][0]
                self.assertEqual(record["delivery_status"], "unverified")

    def test_report_html_is_preserved_as_text_not_escaped_or_executed(self):
        body = '<script>window.evil=1</script><img src=x onerror="evil()">'
        self.report(body=body)
        payload = exporter.build_export(self.db, self.gate)
        self.assertEqual(payload["reports"][0]["text"], body)
        self.assertEqual(json.loads(json.dumps(payload))["reports"][0]["text"], body)

    def test_confirmation_proof_requires_timestamp_sequence_and_unique_message_ids(self):
        _, path, receipt = self.report()
        alterations = [
            {"confirmed_at": None}, {"confirmed_at": "2026-09-21T08:15:10"},
            {"schema_version": True},
            {"parts": [{"index": 0, "status": "confirmed", "message_id": 17}]},
            {"parts": [{"index": True, "status": "confirmed", "message_id": 17}]},
            {"parts": [{"index": 1, "status": "confirmed", "message_id": True}]},
            {"parts": [{"index": 1, "status": "confirmed", "message_id": 17},
                       {"index": 2, "status": "confirmed", "message_id": 17}]},
        ]
        for alteration in alterations:
            with self.subTest(alteration=alteration):
                path.write_text(json.dumps({**receipt, **alteration}))
                self.assertEqual(exporter.load_gate(self.gate)[0][0]["delivery_status"], "unverified")
        encoded = json.dumps(receipt)
        for malformed in (encoded[:-1] + ',"status":"confirmed"}',
                          encoded[:-1] + ',"extra":NaN}', "[" * 2000 + "]" * 2000):
            path.write_text(malformed)
            self.assertEqual(exporter.load_gate(self.gate)[0][0]["delivery_status"], "unverified")

    def test_symlinked_report_receipt_database_and_directory_are_rejected(self):
        report, receipt, _ = self.report()
        report_raw = report.read_bytes()
        report.unlink()
        target = self.root / "elsewhere.md"
        target.write_bytes(report_raw)
        report.symlink_to(target)
        self.assertEqual(exporter.load_gate(self.gate)[0], [])
        report.unlink()
        report.write_bytes(report_raw)
        receipt_raw = receipt.read_bytes()
        receipt.unlink()
        target_receipt = self.root / "elsewhere.json"
        target_receipt.write_bytes(receipt_raw)
        receipt.symlink_to(target_receipt)
        self.assertEqual(exporter.load_gate(self.gate)[0][0]["delivery_status"], "unverified")
        self.database().close()
        linked = self.root / "linked.db"
        linked.symlink_to(self.db)
        self.assertEqual(exporter.load_hermes(linked)[0], [])
        linked_directory = self.root / "linked-out"
        linked_directory.symlink_to(self.gate, target_is_directory=True)
        self.assertEqual(exporter.load_gate(linked_directory)[0], [])

    def test_invalid_dates_oversized_bodies_and_unrelated_files_are_excluded(self):
        self.database([
            ("2026-09-19", "正常"), ("2026-99-99", "无效日期"),
            ("2026-09-18", "x" * (exporter.MAX_REPORT_BYTES + 1)),
        ]).close()
        records, source = exporter.load_hermes(self.db)
        self.assertEqual(len(records), 1)
        self.assertEqual(source["state"], "partial")
        self.report()
        (self.gate / "daily-2026-09-20.md").write_bytes(b"x" * (exporter.MAX_REPORT_BYTES + 1))
        (self.gate / "daily-2026-02-30.md").write_text("bad date")
        (self.gate / "credentials.txt").write_text("NEVER_INCLUDE_THIS")
        (self.gate / "daily-2026-09-19.md.bak").write_text("NEVER_INCLUDE_THIS")
        records, source = exporter.load_gate(self.gate)
        self.assertEqual(len(records), 1)
        self.assertEqual(source["state"], "partial")
        self.assertNotIn("NEVER_INCLUDE_THIS", json.dumps(records))

    def test_receipt_size_issue_type_and_naive_time_fail_honestly(self):
        _, path, receipt = self.report()
        path.write_text("x" * (exporter.MAX_RECEIPT_BYTES + 1))
        self.assertEqual(exporter.load_gate(self.gate)[0][0]["delivery_status"], "unverified")
        path.write_text(json.dumps({**receipt, "issues": ["<script>"]}))
        self.assertEqual(exporter.load_gate(self.gate)[0][0]["delivery_status"], "unverified")
        path.write_text(json.dumps({**receipt, "generated_at": "2026-09-21T08:15:00"}))
        self.assertEqual(exporter.load_gate(self.gate)[0][0]["time_label"], "文件更新时间")

    def test_source_failure_preserves_other_source_without_private_errors(self):
        self.db.write_bytes(b"not sqlite")
        self.report()
        payload = exporter.build_export(self.db, self.gate)
        self.assertEqual(len(payload["reports"]), 1)
        self.assertEqual(payload["sources"][0]["state"], "unavailable")
        self.assertEqual(payload["sources"][1]["state"], "ok")
        self.assertNotIn(str(self.root), json.dumps(payload))
        self.assertNotIn("sqlite", json.dumps(payload))

    def test_empty_sources_are_explicit_not_healthy(self):
        payload = exporter.build_export(self.db, self.gate)
        self.assertEqual(payload["reports"], [])
        self.assertTrue(all(item["state"] == "unavailable" for item in payload["sources"]))

    def test_history_is_bounded(self):
        dates = [("2026-08-%02d" % day, "normal") for day in range(1, 32)]
        self.database(dates).close()
        records, _ = exporter.load_hermes(self.db)
        self.assertEqual(len(records), 30)
        self.assertEqual(records[-1]["report_date"], "2026-08-02")
        for day in range(1, 32):
            self.report(date="2026-08-%02d" % day)
        self.assertEqual(len(exporter.load_gate(self.gate)[0]), 30)

    def test_atomic_output_permissions_and_failure_preserves_previous_snapshot(self):
        destination = self.root / "reports.json"
        payload = exporter.build_export(self.db, self.gate)
        exporter.write_export(payload, destination, os.getgid())
        self.assertEqual(stat.S_IMODE(destination.stat().st_mode), 0o640)
        self.assertEqual(json.loads(destination.read_text()), payload)
        previous = destination.read_bytes()
        with mock.patch.object(exporter.os, "replace", side_effect=OSError("synthetic")):
            with self.assertRaises(OSError):
                exporter.write_export({"changed": True}, destination, os.getgid())
        self.assertEqual(destination.read_bytes(), previous)
        self.assertEqual(list(self.root.glob(".reports-*")), [])

    def input_snapshot(self, **changes):
        self.now = dt.datetime(2026, 9, 21, 12, 0, tzinfo=dt.timezone.utc)
        self.input_path = self.root / "input-status.json"
        self.input_value = {"schema_version": 1, "report_date": "2026-09-21", "state": "clear",
                            "checked_at": self.now.isoformat(), "quality_issues": [], **changes}
        self.input_path.write_text(json.dumps(self.input_value))
        self.input_path.chmod(0o600)
        return self.input_path

    def test_morning_issues_and_current_clear_are_independent_and_no_writes(self):
        report, receipt, _ = self.report(issues=["jd:stale", "nng8:invalid"])
        before = (report.read_bytes(), receipt.read_bytes(), report.stat().st_mtime_ns, receipt.stat().st_mtime_ns)
        path = self.input_snapshot()
        with mock.patch.object(exporter.pwd, "getpwnam", return_value=SimpleNamespace(pw_uid=os.getuid())):
            payload = exporter.build_export(self.db, self.gate, path, now=self.now)
        quality = payload["signal_gate_quality"]
        self.assertEqual(quality["sent_report"]["state"], "issues")
        self.assertEqual(quality["sent_report"]["delivery_status"], "confirmed")
        self.assertEqual(quality["sent_report"]["quality_issues"], ["jd:stale", "nng8:invalid"])
        self.assertEqual(quality["current_inputs"]["state"], "clear")
        self.assertEqual(quality["current_inputs"]["checked_at"], self.now.isoformat())
        self.assertEqual(before, (report.read_bytes(), receipt.read_bytes(), report.stat().st_mtime_ns, receipt.stat().st_mtime_ns))

    def test_old_report_cannot_impersonate_todays_report(self):
        self.report(date="2026-09-20")
        self.input_snapshot()
        quality = exporter.sent_report_quality(exporter.load_gate(self.gate)[0], self.now)
        self.assertEqual(quality["state"], "not_recorded")
        self.assertEqual(quality["delivery_status"], "unknown")

    def test_hash_mismatch_missing_receipt_and_missing_time_do_not_turn_green(self):
        report, receipt, value = self.report()
        self.input_snapshot()
        for changed in ({**value, "content_sha256": "0" * 64},
                        {**value, "generated_at": None},
                        {**value, "generated_at": "2026-09-22T08:15:00+08:00"},
                        {**value, "status": "pending"}):
            receipt.write_text(json.dumps(changed))
            quality = exporter.sent_report_quality(exporter.load_gate(self.gate)[0], self.now)
            self.assertEqual(quality["state"], "unverified")
        receipt.unlink()
        self.assertEqual(exporter.sent_report_quality(exporter.load_gate(self.gate)[0], self.now)["state"], "unverified")

    def test_current_input_freshness_is_not_export_time(self):
        self.input_snapshot()
        for changed, expected in (({"checked_at": (self.now-dt.timedelta(minutes=16)).isoformat()}, "stale"),
                                  ({"checked_at": (self.now+dt.timedelta(seconds=61)).isoformat()}, "unknown"),
                                  ({"checked_at": "2026-09-20T20:00:00+08:00", "report_date": "2026-09-20"}, "stale"),
                                  ({"report_date": "2026-09-20"}, "unknown"),
                                  ({"checked_at": "2026-09-21T12:00:00"}, "unknown")):
            with self.subTest(changed=changed):
                self.input_path.write_text(json.dumps({**self.input_value, **changed}))
                self.assertEqual(exporter.load_current_inputs(self.input_path, self.now, os.getuid())["state"], expected)

    def test_current_inputs_private_shape_identity_and_permissions_fail_closed(self):
        self.input_snapshot()
        for changed in ({"schema_version": True}, {"state": "clear", "quality_issues": ["jd:stale"]},
                        {"state": "issues"}, {"quality_issues": ["unsafe:INTERNAL"]}, {"quality_issues": {}},
                        {"checked_at": None}):
            self.input_path.write_text(json.dumps({**self.input_value, **changed}))
            self.assertEqual(exporter.load_current_inputs(self.input_path, self.now, os.getuid())["state"], "unknown")
        self.input_path.write_text(json.dumps(self.input_value))
        self.assertEqual(exporter.load_current_inputs(self.input_path, self.now, os.getuid()+1)["state"], "unknown")
        self.input_path.chmod(0o644)
        self.assertEqual(exporter.load_current_inputs(self.input_path, self.now, os.getuid())["state"], "unknown")
        self.input_path.unlink()
        self.assertEqual(exporter.load_current_inputs(self.input_path, self.now, os.getuid())["state"], "unknown")

    def test_current_input_snapshot_drops_extra_fields_and_rejects_symlinks(self):
        self.input_snapshot(private_body="NEVER_EXPORT", content_sha256="NEVER_EXPORT", local_path="NEVER_EXPORT")
        result = exporter.load_current_inputs(self.input_path, self.now, os.getuid())
        self.assertEqual(result["state"], "clear")
        self.assertNotIn("NEVER_EXPORT", json.dumps(result))
        target = self.root / "link.json"
        target.symlink_to(self.input_path)
        self.assertEqual(exporter.load_current_inputs(target, self.now, os.getuid())["state"], "unknown")

    def test_portal_export_keeps_raw_inbox_inaccessible(self):
        unit = (Path(__file__).resolve().parents[1] / "systemd/project-portal-export.service").read_text()
        self.assertIn("Wants=project-portal-inputs.service", unit)
        self.assertIn("After=project-portal-inputs.service", unit)
        self.assertIn("CapabilityBoundingSet=CAP_DAC_READ_SEARCH\n", unit)
        line = next(line for line in unit.splitlines() if line.startswith("InaccessiblePaths="))
        self.assertIn("/opt/signal-gate/inbox", line)
        self.assertIn("/opt/signal-gate/secrets.env", line)

    def test_receipt_confirmation_must_be_chronological_and_not_future(self):
        _, path, receipt = self.report()
        self.input_snapshot()
        for changed in ({"confirmed_at": "2026-09-22T08:16:00+08:00", "updated_at": "2026-09-22T08:16:00+08:00"},
                        {"confirmed_at": "2026-09-21T08:14:00+08:00"},
                        {"updated_at": "2026-09-21T08:15:00+08:00"},
                        {"confirmed_at": "2026-09-21T08:15:10"}):
            path.write_text(json.dumps({**receipt, **changed}))
            records, _ = exporter.load_gate(self.gate, now=self.now)
            self.assertEqual(records[0]["delivery_status"], "unverified")
            self.assertEqual(exporter.sent_report_quality(records, self.now)["state"], "unverified")


if __name__ == "__main__":
    unittest.main()
