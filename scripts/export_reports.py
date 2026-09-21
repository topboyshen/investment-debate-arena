#!/usr/bin/env python3
"""Publish a bounded, read-only report snapshot; never generate or send reports."""

from __future__ import annotations

import datetime as dt
import grp
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import stat
import sys
import tempfile

HERMES_DB = Path("/opt/mini-hermes/data/memory.db")
GATE_OUT = Path("/opt/signal-gate/out")
OUTPUT = Path("/var/lib/project-portal/reports.json")
REPORT_LIMIT = 30
MAX_REPORT_BYTES = 256 * 1024
MAX_RECEIPT_BYTES = 32 * 1024
DATE_RE = re.compile(r"\d{4}-\d{2}-\d{2}\Z")
REPORT_RE = re.compile(r"daily-(\d{4}-\d{2}-\d{2})\.md\Z")
ISSUE_RE = re.compile(r"[a-zA-Z0-9_.-]{1,40}:[a-zA-Z0-9_.-]{1,60}\Z")


def utcnow() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def valid_date(value: object) -> bool:
    if not isinstance(value, str) or not DATE_RE.fullmatch(value):
        return False
    try:
        dt.date.fromisoformat(value)
        return True
    except ValueError:
        return False


def timestamp(value: object) -> str | None:
    if not isinstance(value, str) or len(value) > 48:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.isoformat() if parsed.tzinfo is not None else None
    except ValueError:
        return None


def real_directory(path: Path) -> None:
    # Reject symlinks in every parent as well as at the final component.
    absolute = path.absolute()
    for part in reversed((absolute, *absolute.parents)):
        info = part.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ValueError("unsafe directory")


def bounded_read(path: Path, limit: int) -> tuple[bytes, os.stat_result]:
    real_directory(path.parent)
    descriptor = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(descriptor)
        if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
            raise ValueError("unsafe source")
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            content = handle.read(limit + 1)
        if len(content) > limit:
            raise ValueError("oversized source")
        return content, info
    finally:
        os.close(descriptor)


def source_status(source: str, label: str, records: list[dict], invalid: bool,
                  note: str) -> dict:
    return {
        "id": source, "label": label,
        "state": "unavailable" if not records else ("partial" if invalid else "ok"),
        "latest_report_date": records[0]["report_date"] if records else None,
        "note": note,
    }


def unique_object(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON field")
        result[key] = value
    return result


def invalid_constant(value: str) -> None:
    raise ValueError("invalid JSON constant")


def load_hermes(path: Path = HERMES_DB) -> tuple[list[dict], dict]:
    records: list[dict] = []
    invalid = False
    note = "仅确认晨报已保存，不代表已发送。周日、周一通常不生成新的海外晨报。"
    try:
        real_directory(path.parent)
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode):
            raise ValueError("unsafe database")
        # mode=ro sees live WAL records; immutable=1 must not be used here.
        connection = sqlite3.connect(path.absolute().as_uri() + "?mode=ro", uri=True,
                                     timeout=1)
        try:
            after = path.lstat()
            if (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
                raise ValueError("database replaced")
            connection.execute("PRAGMA query_only=ON")
            rows = connection.execute(
                "SELECT report_date, report_text, created_at, updated_at "
                "FROM market_reports ORDER BY report_date DESC LIMIT 30"
            )
            for report_date, body, created, updated in rows:
                if (not valid_date(report_date) or not isinstance(body, str)
                        or not body.strip() or len(body.encode("utf-8")) > MAX_REPORT_BYTES):
                    invalid = True
                    continue
                issues = []
                if timestamp(created) is None or timestamp(updated) is None:
                    issues.append("portal:time_unverified")
                    invalid = True
                records.append({
                    "id": "overseas:" + report_date, "source": "overseas",
                    "title": "海外市场晨报", "report_date": report_date,
                    "generated_at": timestamp(created), "updated_at": timestamp(updated),
                    "time_label": "首次保存", "delivery_status": "unknown",
                    "quality_issues": issues, "text": body,
                })
        finally:
            connection.close()
    except (OSError, sqlite3.Error, ValueError, UnicodeError):
        invalid = True
    if not records:
        note = "暂时无法读取可核验的海外晨报；不会用生成时间冒充投递确认。"
    elif invalid:
        note += " 部分记录无法核验，已跳过或标明。"
    return records, source_status("overseas", "海外市场晨报", records, invalid, note)


def receipt_metadata(path: Path, report_date: str, raw: bytes) -> tuple[str, list[str], str | None, str | None]:
    try:
        receipt_raw, _ = bounded_read(path, MAX_RECEIPT_BYTES)
        receipt = json.loads(receipt_raw, object_pairs_hook=unique_object,
                             parse_constant=invalid_constant)
        if (not isinstance(receipt, dict) or type(receipt.get("schema_version")) is not int
                or receipt.get("schema_version") != 1
                or receipt.get("report_date") != report_date):
            raise ValueError("invalid receipt")
        issues = receipt.get("issues", [])
        if (not isinstance(issues, list) or len(issues) > 40
                or any(not isinstance(code, str) or not ISSUE_RE.fullmatch(code) for code in issues)):
            raise ValueError("invalid issues")
        digest = receipt.get("content_sha256")
        if (not isinstance(digest, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", digest)
                or digest.lower() != hashlib.sha256(raw).hexdigest()):
            return "unverified", list(dict.fromkeys(issues + ["portal:content_mismatch"])), None, None
        status = receipt.get("status")
        if status not in {"confirmed", "failed", "unknown", "pending", "blocked"}:
            raise ValueError("invalid status")
        if status == "confirmed":
            parts = receipt.get("parts")
            if (timestamp(receipt.get("confirmed_at")) is None
                    or not isinstance(parts, list) or not parts or len(parts) > 100
                    or any(not isinstance(part, dict) or part.get("status") != "confirmed"
                           or type(part.get("index")) is not int
                           or type(part.get("message_id")) is not int
                           or part["message_id"] <= 0 for part in parts)
                    or [part["index"] for part in parts] != list(range(1, len(parts) + 1))
                    or len({part["message_id"] for part in parts}) != len(parts)):
                return "unverified", list(dict.fromkeys(issues + ["portal:receipt_unverified"])), None, None
        return status, list(dict.fromkeys(issues)), timestamp(receipt.get("generated_at")), timestamp(receipt.get("updated_at"))
    except (OSError, ValueError, UnicodeError, TypeError, RecursionError):
        return "unverified", ["portal:receipt_unverified"], None, None


def load_gate(directory: Path = GATE_OUT) -> tuple[list[dict], dict]:
    records: list[dict] = []
    invalid = False
    note = "仅展示本机已有日报；发送确认与来源数据质量分别列示。"
    try:
        real_directory(directory)
        names = []
        for path in directory.iterdir():
            match = REPORT_RE.fullmatch(path.name)
            if not match:
                continue
            if not valid_date(match[1]):
                invalid = True
                continue
            names.append((match[1], path))
        for report_date, path in sorted(names, reverse=True)[:REPORT_LIMIT]:
            try:
                raw, info = bounded_read(path, MAX_REPORT_BYTES)
                body = raw.decode("utf-8")
                if not body.strip():
                    raise ValueError("empty report")
                status, issues, generated, updated = receipt_metadata(
                    directory / "delivery" / (report_date + ".json"), report_date, raw)
                modified = dt.datetime.fromtimestamp(info.st_mtime, dt.timezone.utc).isoformat()
                records.append({
                    "id": "signal_gate:" + report_date, "source": "signal_gate",
                    "title": "A 股联动日报", "report_date": report_date,
                    "generated_at": generated or modified,
                    "updated_at": updated or modified,
                    "time_label": "生成时间" if generated else "文件更新时间",
                    "delivery_status": status, "quality_issues": issues, "text": body,
                })
            except (OSError, ValueError, UnicodeError):
                invalid = True
    except (OSError, ValueError):
        invalid = True
    if records and (records[0]["quality_issues"] or records[0]["delivery_status"] != "confirmed"):
        invalid = True
        note += " 最新日报有待核验项；已发送不代表资料完整。"
    if not records:
        note = "暂时无法读取可核验的 A 股联动日报；不会生成、补发或替代原始日报。"
    elif invalid:
        note += " 部分记录或回执未通过核验。"
    return records, source_status("signal_gate", "A 股联动日报", records, invalid, note)


def build_export(hermes_db: Path = HERMES_DB, gate_out: Path = GATE_OUT) -> dict:
    overseas, overseas_status = load_hermes(hermes_db)
    gate, gate_status = load_gate(gate_out)
    return {"schema_version": 1, "exported_at": utcnow(),
            "reports": sorted(overseas + gate, key=lambda item: (item["report_date"], item["source"]), reverse=True),
            "sources": [overseas_status, gate_status]}


def write_export(payload: dict, destination: Path = OUTPUT, group_id: int | None = None) -> None:
    real_directory(destination.parent)
    group_id = grp.getgrnam("www-data").gr_gid if group_id is None else group_id
    content = (json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")
    descriptor, temporary = tempfile.mkstemp(prefix=".reports-", dir=destination.parent)
    try:
        os.fchmod(descriptor, 0o640)
        os.fchown(descriptor, os.getuid(), group_id)
        with os.fdopen(descriptor, "wb") as handle:
            descriptor = -1
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(destination.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if descriptor != -1:
            os.close(descriptor)
        if os.path.exists(temporary):
            os.unlink(temporary)


def main() -> int:
    if len(sys.argv) != 1 or os.geteuid() != 0:
        print("report_export status=blocked")
        return 2
    try:
        payload = build_export()
        write_export(payload)
    except (OSError, ValueError, KeyError):
        print("report_export status=failed")
        return 1
    summary = " ".join(source["id"] + "=" + source["state"] for source in payload["sources"])
    print("report_export reports=" + str(len(payload["reports"])) + " " + summary)
    return 0 if payload["reports"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
