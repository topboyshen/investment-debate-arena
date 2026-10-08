#!/usr/bin/env python3
"""Export only fixed, aggregate operational fields. No request-controlled input.

Reads kernel counters, selected systemd properties and existing monitor results.
Never executes a health check, sends a notification, or reads service secrets.
"""
from __future__ import annotations

import datetime as dt
import grp
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import stat
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

OUTPUT_DIR = Path('/var/lib/project-portal')
SERVICES = {
    'sing-box': 'sing-box · 代理节点', 'mtg': 'mtg · Telegram 代理',
    'cloudflared': 'Cloudflare Tunnel', 'nginx': 'nginx · 网页入口',
    'netdata': 'Netdata · 资源监控', 'fail2ban': 'Fail2ban · 登录防护',
    'ssh': 'SSH · 远程连接', 'mini-hermes': 'mini-hermes',
    'mini-hermes-pi': 'pi 助手', 'signal-gate': 'Signal Gate · 研究与资讯收件',
    'signal-gate-review': 'Signal Gate 人审',
    'investment-debate-arena': '项目工作台 / Arena',
}
PROPERTIES = ('Id', 'LoadState', 'ActiveState', 'SubState', 'MemoryCurrent',
              'MemoryMax', 'CPUUsageNSec', 'TasksCurrent', 'NRestarts',
              'ExecMainStartTimestampMonotonic', 'ControlGroup')
CHECKS = (
    ('runtime', '业务健康检查', '/var/lib/business-health-monitor/runtime.json', 25 * 60),
    ('pi_requests', 'pi 请求结果', '/var/lib/business-health-monitor/pi-requests.json', 25 * 60),
    ('subscriptions', '订阅健康检查', '/var/lib/private/subscription-health-monitor/subscriptions.json', 45 * 60),
    ('config_drift', '配置一致性', '/var/lib/config-drift/state.json', 45 * 60),
    ('morning', '海外晨报看门狗', '/var/lib/business-health-monitor/morning.json', 27 * 3600),
)
# The pi collector queries the preceding 24 hours of completed requests. Its
# own updated_at is a collection timestamp, not a fresh business success.
PI_SAMPLE_WINDOW_SECONDS = 24 * 3600
VIX_PROBE_RECEIPT = Path('/var/lib/business-health-monitor/vix-source-probe.json')
VIX_IMPLEMENTATION_FILES = {
    'collector_sha256': Path('/opt/mini-hermes/app/mini_hermes/overseas_market.py'),
    'validator_sha256': Path('/opt/mini-hermes/app/mini_hermes/reporting.py'),
}
VIX_PROBE_LABELS = {
    'vix_source_valid': 'VIX 来源受控实测通过',
    'vix_source_fetch_failed': 'VIX 来源采集失败',
    'vix_source_quality_failed': 'VIX 来源未通过数值或时效校验',
    'vix_source_unverified': 'VIX 来源当前未验证',
}
PI_PROBE_RECEIPT = Path('/var/lib/business-health-monitor/pi-source-probe.json')
PI_IMPLEMENTATION_FILES = {
    'broker_sha256': Path('/opt/mini-hermes/app/mini_hermes/pi_channel/broker.py'),
    'research_sha256': Path('/opt/mini-hermes/app/mini_hermes/pi_channel/research_completion.mjs'),
    'client_sha256': Path('/opt/mini-hermes/app/mini_hermes/pi_channel/client.py'),
}
PI_AUTH_METADATA_PATH = Path('/var/lib/mini-hermes-pi/agent/auth.json')
PI_PROBE_LABELS = {
    'pi_probe_valid': 'pi 研究请求受控实测完成',
    'auth_required': 'pi 受控实测需要重新授权',
    'timeout': 'pi 受控实测超时',
    'rate_limited': 'pi 受控实测受到速率限制',
    'quota_exceeded': 'pi 受控实测额度不足',
    'upstream_error': 'pi 受控实测上游失败',
    'invalid_response': 'pi 受控实测响应无法核验',
    'probe_error': 'pi 受控实测当前未验证',
    'busy': 'pi 受控实测繁忙，未确认完成',
}
ISSUE_LABELS = {
    'arena_business_failures': '辩论场连续出现服务端错误',
    'arena_business_error_rate': '辩论场业务错误率偏高',
    'morning_data_quality': '海外晨报数据缺失或未通过时效校验',
    'subscription_mihomo_unverified': 'mihomo 节点尚未验证',
    'subscription_mihomo_unreachable': 'mihomo 节点 TCP 不可达',
}


def number(value, *, integer=False):
    if isinstance(value, bool):
        return None
    try:
        result = int(value) if integer else float(value)
        return result if math.isfinite(result) and 0 <= result < 2**63 else None
    except (ValueError, TypeError, OverflowError):
        return None


def iso(epoch):
    return dt.datetime.fromtimestamp(epoch, dt.timezone.utc).isoformat(timespec='seconds')


def epoch(value):
    if not isinstance(value, str) or len(value) > 64:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed.timestamp() if parsed.tzinfo else None
    except (ValueError, OverflowError):
        return None


def small_read(path, maximum=131072, *, root_owned=False):
    fd = os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    try:
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_size > maximum:
            raise ValueError('invalid source')
        if root_owned and (info.st_uid != 0 or stat.S_IMODE(info.st_mode) & 0o022):
            raise ValueError('untrusted source')
        with os.fdopen(fd, 'rb', closefd=False) as stream:
            data = stream.read(maximum + 1)
        if len(data) > maximum:
            raise ValueError('oversized source')
        return data.decode('utf-8')
    finally:
        os.close(fd)


def load_json(path):
    try:
        value = json.loads(small_read(path))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError, UnicodeError):
        return {}


def unique_json_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate field')
        result[key] = value
    return result


def current_implementation(paths):
    # Fixed implementation paths only. A receipt cannot choose which files
    # are read, and neither hashes nor source paths enter public JSON.
    return {key: hashlib.sha256(small_read(path, maximum=1024 * 1024, root_owned=True).encode('utf-8')).hexdigest()
            for key, path in paths.items()}


def current_vix_implementation():
    return current_implementation(VIX_IMPLEMENTATION_FILES)


def vix_source_validation(now):
    result = {'scope': 'vix_source', 'status': 'unverified',
              'code': 'vix_source_unverified', 'label': VIX_PROBE_LABELS['vix_source_unverified'],
              'checked_at': None, 'expires_at': None, 'source_as_of': None}
    try:
        data = json.loads(small_read(VIX_PROBE_RECEIPT, maximum=16384, root_owned=True),
                          object_pairs_hook=unique_json_object)
        fields = {'version', 'scope', 'asset_code', 'status', 'code', 'source_id', 'source_as_of',
                  'checked_at', 'expires_at', 'ttl_seconds', 'implementation'}
        if (not isinstance(data, dict) or set(data) != fields
                or type(data['version']) is not int or data['version'] != 1
                or data['scope'] != 'vix_source' or data['asset_code'] != 'VIX'
                or not all(isinstance(data[key], str) for key in ('status', 'code', 'source_id'))
                or data['status'] not in {'pass', 'fail', 'error', 'unverified'}
                or data['source_id'] not in {'cboe', 'source_unknown'}
                or type(data['ttl_seconds']) is not int or not 1 <= data['ttl_seconds'] <= 3600):
            return result
        status_codes = {'pass': {'vix_source_valid'},
                        'fail': {'vix_source_fetch_failed', 'vix_source_quality_failed'},
                        'error': {'vix_source_probe_error', 'vix_source_implementation_changed'},
                        'unverified': {'vix_source_unverified'}}
        if data['code'] not in status_codes[data['status']]:
            return result
        checked, expires = epoch(data['checked_at']), epoch(data['expires_at'])
        source = epoch(data['source_as_of']) if data['source_as_of'] is not None else None
        if (checked is None or expires is None or checked > now + 60
                or not checked < expires <= checked + data['ttl_seconds']
                or expires <= now
                or (data['source_as_of'] is not None and (source is None or source > now + 60))):
            return result
        bindings = data['implementation']
        if (not isinstance(bindings, dict) or set(bindings) != set(VIX_IMPLEMENTATION_FILES)
                or not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                           for value in bindings.values())
                or bindings != current_vix_implementation()):
            return result
        if (data['status'] == 'pass' and (data['source_id'] != 'cboe' or source is None
                or source > checked + 60 or expires > source + 24 * 3600)):
            return result
        # Accepted collector errors are still unverified observations. Any
        # successful source check applies only to VIX, never to the saved report.
        projected_status = data['status'] if data['status'] in {'pass', 'fail'} else 'unverified'
        if data['source_id'] != 'cboe' and not (data['status'] == 'fail' and data['code'] == 'vix_source_fetch_failed'):
            projected_status = 'unverified'
        code = data['code'] if data['code'] in VIX_PROBE_LABELS else 'vix_source_unverified'
        if projected_status == 'unverified':
            code = 'vix_source_unverified'
        result.update(status=projected_status, code=code, label=VIX_PROBE_LABELS[code],
                      checked_at=iso(checked), expires_at=iso(expires),
                      source_as_of=iso(source) if source is not None else None)
        return result
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        return result


def current_pi_auth_metadata():
    # Metadata binding only: never open, read, hash or publish authentication.
    info = PI_AUTH_METADATA_PATH.lstat()
    if not stat.S_ISREG(info.st_mode):
        raise ValueError('invalid authentication metadata')
    return {'inode': info.st_ino, 'mtime_ns': info.st_mtime_ns, 'size': info.st_size}


def pi_controlled_validation(now):
    result = {'scope': 'pi_research_completion', 'model': 'xai/grok-4.6', 'status': 'unverified',
              'code': 'probe_error', 'label': PI_PROBE_LABELS['probe_error'],
              'checked_at': None, 'expires_at': None}
    try:
        data = json.loads(small_read(PI_PROBE_RECEIPT, maximum=16384, root_owned=True),
                          object_pairs_hook=unique_json_object)
        fields = {'version', 'scope', 'model', 'status', 'code', 'checked_at', 'expires_at',
                  'ttl_seconds', 'implementation', 'binding_auth'}
        if (not isinstance(data, dict) or set(data) != fields
                or type(data['version']) is not int or data['version'] != 1
                or data['scope'] != 'pi_research_completion' or data['model'] != 'xai/grok-4.6'
                or not all(isinstance(data[key], str) for key in ('status', 'code'))
                or data['status'] not in {'pass', 'fail', 'error'}
                or type(data['ttl_seconds']) is not int or not 1 <= data['ttl_seconds'] <= 3600):
            return result
        status_codes = {'pass': {'pi_probe_valid'},
                        'fail': {'auth_required', 'timeout', 'rate_limited', 'quota_exceeded',
                                 'upstream_error', 'invalid_response'},
                        'error': {'probe_error', 'busy'}}
        if data['code'] not in status_codes[data['status']]:
            return result
        checked, expires = epoch(data['checked_at']), epoch(data['expires_at'])
        if (checked is None or expires is None or checked > now + 60
                or not checked < expires <= checked + data['ttl_seconds'] or expires <= now):
            return result
        bindings = data['implementation']
        if (not isinstance(bindings, dict) or set(bindings) != set(PI_IMPLEMENTATION_FILES)
                or not all(isinstance(value, str) and re.fullmatch(r'[0-9a-f]{64}', value)
                           for value in bindings.values())
                or bindings != current_implementation(PI_IMPLEMENTATION_FILES)):
            return result
        authentication = data['binding_auth']
        if (not isinstance(authentication, dict) or set(authentication) != {'inode', 'mtime_ns', 'size'}
                or not all(type(value) is int and 0 <= value < 2**63 for value in authentication.values())
                or authentication['inode'] == 0 or authentication != current_pi_auth_metadata()):
            return result
        result.update(status=data['status'] if data['status'] in {'pass', 'fail'} else 'unverified',
                      code=data['code'], label=PI_PROBE_LABELS[data['code']],
                      checked_at=iso(checked), expires_at=iso(expires))
        return result
    except (OSError, ValueError, TypeError, UnicodeError, OverflowError):
        return result


def command(args):
    # Fixed commands only; stderr may contain paths so it never enters JSON.
    try:
        result = subprocess.run(args, capture_output=True, timeout=8, check=False,
                                env={'PATH': '/usr/sbin:/usr/bin:/sbin:/bin', 'LC_ALL': 'C'})
        if result.returncode or len(result.stdout) > 524288:
            return ''
        return result.stdout.decode('utf-8', errors='replace')
    except (OSError, subprocess.TimeoutExpired):
        return ''


def properties(raw):
    return dict(line.split('=', 1) for line in raw.splitlines() if '=' in line)


def collect_services(now, uptime):
    raw = command(['systemctl', 'show', '--no-pager',
                   '--property=' + ','.join(PROPERTIES), *[key + '.service' for key in SERVICES]])
    by_id = {item.get('Id'): item for item in map(properties, raw.strip().split('\n\n'))}
    result = []
    for key, label in SERVICES.items():
        data = by_id.get(key + '.service', {})
        active = data.get('ActiveState')
        sub = data.get('SubState')
        started = number(data.get('ExecMainStartTimestampMonotonic'))
        age = uptime - started / 1e6 if started and uptime is not None else None
        if age is not None and age < 0:
            age = None
        peak = None
        cgroup = data.get('ControlGroup', '')
        if re.fullmatch(r'/system\.slice/[a-zA-Z0-9_.@-]+\.service', cgroup):
            try:
                peak = number(small_read(Path('/sys/fs/cgroup') / cgroup.lstrip('/') / 'memory.peak'), integer=True)
            except (OSError, ValueError):
                pass
        result.append({
            'id': key, 'label': label,
            'active_state': active if active in {'active', 'inactive', 'failed', 'activating', 'deactivating', 'reloading'} else 'unknown',
            'sub_state': sub if sub in {'running', 'dead', 'failed', 'exited', 'start', 'stop', 'auto-restart', 'reload'} else 'unknown',
            'memory_bytes': number(data.get('MemoryCurrent'), integer=True),
            'memory_peak_bytes': peak,
            'memory_limit_bytes': number(data.get('MemoryMax'), integer=True),
            'memory_limit_unlimited': data.get('MemoryMax') == 'infinity',
            'cpu_seconds': (number(data.get('CPUUsageNSec')) / 1e9) if number(data.get('CPUUsageNSec')) is not None else None,
            'tasks': number(data.get('TasksCurrent'), integer=True),
            'restarts': number(data.get('NRestarts'), integer=True),
            'started_at': iso(now - age) if age is not None else None,
            'uptime_seconds': round(age) if age is not None and active == 'active' else None,
        })
    return result


def project_check(key, label, data, now, max_age):
    checked = epoch(data.get('updated_at'))
    state = data.get('last_status') if key == 'config_drift' else data.get('status')
    status = {'clear': 'ok', 'ok': 'ok', 'pending': 'warning', 'alert': 'error',
              'issue': 'error', 'problem': 'error', 'notified': 'error', 'drift': 'error'}.get(state, 'unknown')
    issues = []
    pi_evidence = None
    if key == 'pi_requests':
        # Runtime process health is not pi request health. Only expose fixed
        # timestamps, never request hashes, incident IDs or notification bodies.
        streak, success = data.get('failure_streak'), data.get('last_success_us')
        last_result = data.get('watermark_us')
        incident = data.get('incident')
        latest_allowed_us = int((now + 60) * 1_000_000)
        valid = (data.get('version') == 1 and type(streak) is int and 0 <= streak <= 1000000
                 and type(success) is int and 0 <= success <= latest_allowed_us
                 and type(last_result) is int and success <= last_result <= latest_allowed_us
                 and (incident is None or isinstance(incident, dict)))
        last_success_at = iso(success / 1_000_000) if valid and success else None
        last_result_at = iso(last_result / 1_000_000) if valid and last_result else None
        recent_success = bool(valid and success and now - success / 1_000_000 <= PI_SAMPLE_WINDOW_SECONDS)
        recent_result = bool(valid and last_result and now - last_result / 1_000_000 <= PI_SAMPLE_WINDOW_SECONDS)
        sample_status = ('unverified' if not valid or not last_result else
                         'recent_success' if recent_success else
                         'recent_without_success' if recent_result else 'idle')
        pi_evidence = {'last_success_at': last_success_at, 'last_result_at': last_result_at,
                       'sample_status': sample_status,
                       'sample_window_seconds': PI_SAMPLE_WINDOW_SECONDS}
        if not valid or (incident is not None) != (streak >= 2):
            status, issues = 'unknown', ['pi 请求状态记录不可核验']
        elif incident is not None:
            status, issues = 'error', ['pi 请求连续失败，尚无后续成功证据']
        elif streak:
            status, issues = 'warning', ['pi 最近一次请求失败，尚未达到连续失败阈值']
        elif recent_success:
            status = 'ok'
        elif recent_result:
            status, issues = 'unknown', [f'近 {PI_SAMPLE_WINDOW_SECONDS // 3600} 小时有结束请求，但无成功证据；当前可用性未验证']
        elif last_result:
            status, issues = 'unknown', [f'近 {PI_SAMPLE_WINDOW_SECONDS // 3600} 小时无已完成请求样本；当前可用性未验证']
        else:
            status, issues = 'unknown', ['尚无已完成的 pi 请求证据']
    pending = data.get('pending_codes', {})
    codes = [code for code in pending if isinstance(code, str)] if isinstance(pending, dict) else []
    # The collector removes recovered codes from these current-state lists.
    # Once an issue has been notified, pending_codes is empty while the issue
    # remains active. Never infer current issues from retained attempt history.
    if state in {'pending', 'issue'}:
        for field in ('notified_codes', 'uncertain_codes'):
            values = data.get(field)
            if isinstance(values, list):
                codes.extend(code for code in values if isinstance(code, str))
    codes = list(dict.fromkeys(codes))
    if codes:
        issues = [ISSUE_LABELS.get(code, '检测到一项异常（详见私有告警）') for code in codes[:20]]
        if status == 'ok':
            status = 'warning'
    if key == 'config_drift' and status != 'error' and (number(data.get('pending_count')) or 0) > 0:
        status = 'warning'
    if key == 'config_drift' and status in {'warning', 'error'}:
        issues = ['配置与基线不一致，具体内容不公开']
    if checked is None or checked > now + 60:
        status = 'unknown'
    elif now - checked > max_age:
        status = 'stale'
    result = {'id': key, 'label': label, 'status': status,
              'checked_at': iso(checked) if checked is not None else None, 'issues': issues}
    if pi_evidence is not None:
        result.update(pi_evidence)
    return result


def collect_checks(now):
    cadence = {'runtime': 900, 'pi_requests': 900, 'subscriptions': 1800, 'config_drift': 1800, 'morning': 86400}
    checks = [{**project_check(key, label, load_json(path), now, age), 'source_interval_seconds': cadence[key]}
              for key, label, path, age in CHECKS]
    for check in checks:
        if check['id'] == 'morning':
            check['source_validation'] = vix_source_validation(now)
        elif check['id'] == 'pi_requests':
            controlled = pi_controlled_validation(now)
            check['controlled_validation'] = controlled
            if controlled['status'] == 'fail':
                check['status'] = 'error'
                check['issues'] = [*check['issues'], controlled['label']]
    return checks


def cpu_ticks(raw):
    values = [int(v) for v in raw.splitlines()[0].split()[1:9]]
    return sum(values), values[3] + (values[4] if len(values) > 4 else 0)


def rates(current, previous):
    output = {'cpu_percent': None, 'network_rx_bytes_per_second': None, 'network_tx_bytes_per_second': None}
    span = current.get('monotonic', 0) - previous.get('monotonic', 0)
    if (not 1 <= span <= 180 or not current.get('boot_id')
            or current.get('boot_id') != previous.get('boot_id')):
        return output
    total = current.get('cpu_total', 0) - previous.get('cpu_total', 0)
    idle = current.get('cpu_idle', 0) - previous.get('cpu_idle', 0)
    if total > 0 and 0 <= idle <= total:
        output['cpu_percent'] = round(100 * (total - idle) / total, 2)
    if current.get('interfaces') and current.get('interfaces') == previous.get('interfaces'):
        for name in ('rx', 'tx'):
            before, after = previous.get(name), current.get(name)
            if number(before) is not None and number(after) is not None and after >= before:
                output['network_' + name + '_bytes_per_second'] = round((after - before) / span, 2)
    return output


def collect_host(previous):
    host = {key: None for key in ('uptime_seconds', 'cpu_percent', 'cpu_count', 'memory_total_bytes',
             'memory_available_bytes', 'swap_total_bytes', 'swap_free_bytes', 'disk_total_bytes',
             'disk_used_bytes', 'network_rx_bytes', 'network_tx_bytes',
             'network_rx_bytes_per_second', 'network_tx_bytes_per_second')}
    private = {'monotonic': time.monotonic()}
    try:
        host['uptime_seconds'] = float(small_read('/proc/uptime').split()[0])
        host['cpu_count'] = os.cpu_count()
        host['load'] = list(os.getloadavg())
        private['boot_id'] = small_read('/proc/sys/kernel/random/boot_id').strip()
        private['cpu_total'], private['cpu_idle'] = cpu_ticks(small_read('/proc/stat'))
        memory = {line.split(':')[0]: int(line.split()[1]) * 1024 for line in small_read('/proc/meminfo').splitlines() if len(line.split()) >= 3 and line.split()[2] == 'kB'}
        for dest, source in (('memory_total_bytes', 'MemTotal'), ('memory_available_bytes', 'MemAvailable'),
                             ('swap_total_bytes', 'SwapTotal'), ('swap_free_bytes', 'SwapFree')):
            host[dest] = memory.get(source)
        disk = os.statvfs('/')
        host['disk_total_bytes'] = disk.f_blocks * disk.f_frsize
        host['disk_used_bytes'] = (disk.f_blocks - disk.f_bfree) * disk.f_frsize
    except (OSError, ValueError, IndexError):
        pass
    try:
        # Hardware/virtual-NIC uplinks only: no loopback, bridges, veth or tunnel
        # duplicates. Interface identifiers remain private in the sampler state.
        devices = [entry for entry in Path('/sys/class/net').iterdir() if (entry / 'device').exists()]
        private['interfaces'] = sorted(entry.name for entry in devices)
        if devices:
            for direction in ('rx', 'tx'):
                count = sum(int(small_read(entry / 'statistics' / (direction + '_bytes'))) for entry in devices)
                private[direction] = count
                host['network_' + direction + '_bytes'] = count
    except (OSError, ValueError):
        pass
    host.update(rates(private, previous))
    return host, private


def listener_rows(raws):
    observed = {}
    successful = bool(raws) and all(raw is not None for raw in raws)
    for raw in raws:
        if raw is None:
            continue
        for line in raw.splitlines()[1:]:
            parts = line.split()
            if len(parts) < 4 or parts[3] != '0A':
                continue
            try:
                address, port_text = parts[1].split(':')
                port = int(port_text, 16)
            except ValueError:
                continue
            try:
                packed = b''.join(bytes.fromhex(address[i:i+8])[::-1] for i in range(0, len(address), 8))
                ip = ipaddress.ip_address(packed)
                scope = ('loopback' if ip.is_loopback else 'public' if ip.is_unspecified or ip.is_global
                         else 'private' if ip.is_private else 'unknown')
            except ValueError:
                scope = 'unknown'
            observed.setdefault(port, set()).add(scope)
    result = []
    for key, label, port in (('sing-box', 'sing-box', 8443), ('mtg', 'mtg', 9443),
                              ('nginx', '网页源站', 18765), ('netdata', 'Netdata 源站', 19999)):
        scopes = observed.get(port, set())
        result.append({'id': key, 'label': label, 'transport': 'TCP', 'port': port,
                       'scope': next((s for s in ('public', 'unknown', 'private', 'loopback') if s in scopes), 'unknown'),
                       'state': 'listening' if scopes else ('not_listening' if successful else 'unknown')})
    return result


def collect_listeners():
    rows = []
    for path in ('/proc/net/tcp', '/proc/net/tcp6'):
        try:
            rows.append(small_read(path, 1048576))
        except (OSError, ValueError):
            rows.append(None)
    return listener_rows(rows)


def subscription_projection(message, checked_at, now):
    """Parse only explicitly named aggregate fields, never a URL/log message."""
    checked = epoch(checked_at)
    if checked is None or not 0 <= now - checked <= 45 * 60:
        return []
    fields = dict(re.findall(r'\b([a-z][a-z0-9_]*)=([A-Za-z0-9_.-]+)', message))
    rows = []
    for key, label in (('iphone', 'iPhone / sing-box'), ('shadowrocket', '小火箭'), ('mihomo', 'mihomo')):
        prefix = 'sub_' + key + '_'
        okay = fields.get(prefix + 'ok')
        download = fields.get(prefix + 'download')
        nodes = fields.get(prefix + 'nodes', 'unknown')
        fmt = fields.get(prefix + 'format')
        fmt = fmt if fmt in {'sing-box-json', 'base64-proxy-uri', 'clash-yaml'} else None
        rows.append({'id': key, 'label': label,
                     'overall': 'ok' if okay == 'true' else 'error' if okay == 'false' else 'unknown',
                     'download': download if download in {'ok', 'error'} else ('ok' if okay == 'true' else 'unknown'),
                     'format': 'ok' if fmt and (okay == 'true' or download == 'ok') else 'unknown',
                     'format_name': fmt,
                     'certificate_days': number(fields.get(prefix + 'cert_days')),
                     'nodes': nodes if nodes in {'reachable', 'unreachable', 'unverified'} else 'unknown',
                     'check': 'tcp_only' if fields.get(prefix + 'check') == 'tcp_only' else 'unknown',
                     'endpoints': number(fields.get(prefix + 'endpoints'), integer=True),
                     'reachable': number(fields.get(prefix + 'reachable'), integer=True),
                     'checked_at': checked_at})
    return rows


def collect_subscriptions(now):
    raw = command(['journalctl', '-u', 'subscription-health-monitor.service', '--since', '45 minutes ago',
                   '--no-pager', '-o', 'json', '-n', '12', '--grep=business_health mode=subscriptions'])
    candidates = []
    for line in raw.splitlines():
        try:
            row = json.loads(line)
            message = row.get('MESSAGE', '')
            if not isinstance(message, str) or not message.startswith('business_health mode=subscriptions '):
                continue
            checked = int(row['__REALTIME_TIMESTAMP']) / 1e6
            candidates.append((checked, message))
        except (ValueError, TypeError, KeyError):
            continue
    if not candidates:
        return []
    checked, message = max(candidates, key=lambda entry: entry[0])
    return subscription_projection(message, iso(checked), now)


def mtg_projection(raw, now):
    mapping = {'mtg_client_connections': 'client_connections',
               'mtg_telegram_connections': 'telegram_connections',
               'mtg_concurrency_limited': 'concurrency_limited',
               'mtg_replay_attacks': 'replay_attacks', 'mtg_domain_fronting': 'domain_fronting'}
    result = {'collected_at': iso(now)}
    for line in raw.splitlines():
        match = re.fullmatch(r'(mtg_[a-z_]+)(?:\{(.*?)\})?\s+([0-9.eE+\-]+)(?:\s+\d+)?', line)
        if not match:
            continue
        name, labels, value = match.groups()
        numeric = number(value)
        if numeric is None:
            continue
        dest = mapping.get(name)
        if name == 'mtg_telegram_traffic':
            direction = re.search(r'(?:^|,)\s*direction="(to_client|from_client)"(?:,|$)', labels or '')
            if direction:
                dest = 'traffic_' + direction.group(1) + '_bytes'
        if dest:
            result[dest] = result.get(dest, 0) + numeric
    return result


def collect_mtg(now):
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *_args, **_kwargs):
            return None
    try:
        # Ignore proxy environment and disallow redirects. The unit also limits
        # IP access to localhost. Neither labels nor raw responses are exported.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        with opener.open('http://127.0.0.1:19091/metrics', timeout=3) as response:
            raw = response.read(524289)
            if len(raw) > 524288:
                return {}
            return mtg_projection(raw.decode('utf-8'), now)
    except (OSError, ValueError, UnicodeError, urllib.error.URLError):
        return {}


def atomic_json(path, value, mode, gid):
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise ValueError('unsafe output')
    descriptor, temp = tempfile.mkstemp(prefix='.ops-', dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        os.fchown(descriptor, os.getuid(), gid)
        with os.fdopen(descriptor, 'w', encoding='utf-8') as stream:
            json.dump(value, stream, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
            stream.write('\n')
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def main():
    now = time.time()
    if OUTPUT_DIR.is_symlink() or not OUTPUT_DIR.is_dir():
        raise ValueError('unsafe output directory')
    previous = load_json(OUTPUT_DIR / 'ops-private.json')
    host, private = collect_host(previous)
    result = {'schema_version': 1, 'exported_at': iso(now), 'interval_seconds': 60,
              'host': host, 'services': collect_services(now, host['uptime_seconds']),
              'checks': collect_checks(now),
              'network': {'listening_services': collect_listeners(), 'subscriptions': collect_subscriptions(now),
                          'mtg': collect_mtg(now)}}
    atomic_json(OUTPUT_DIR / 'ops.json', result, 0o640, grp.getgrnam('www-data').gr_gid)
    atomic_json(OUTPUT_DIR / 'ops-private.json', private, 0o600, grp.getgrnam('www-data').gr_gid)
    print('ops_export status=ok services=' + str(len(result['services'])))


if __name__ == '__main__':
    main()
