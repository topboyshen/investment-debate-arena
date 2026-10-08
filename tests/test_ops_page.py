"""Route boundaries and executable read-only renderer regression tests."""

import datetime
import http.client
import json
import re
import shutil
import subprocess
import sys
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from ops_page import OPS_PAGE
from portal_pages import HOME_PAGE
from server import Handler, SECURITY_HEADERS


class OpsRoutesTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        cls.server.daemon_threads = True
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=2)

    def request(self, method, path):
        c = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        c.request(method, path)
        r = c.getresponse()
        value = r.status, dict(r.getheaders()), r.read()
        c.close()
        return value

    def test_get_head_and_home_link(self):
        for method in ("GET", "HEAD"):
            with self.subTest(method=method):
                status, headers, body = self.request(method, "/ops/")
                self.assertEqual(status, 200)
                self.assertEqual(headers["Cache-Control"], "no-store")
                for name in SECURITY_HEADERS:
                    self.assertIn(name, headers)
                if method == "HEAD":
                    self.assertEqual(body, b"")
                else:
                    self.assertEqual(body.decode(), OPS_PAGE)
        self.assertIn('href="/ops/"', HOME_PAGE)
        self.assertIn("查看详细数据与状态", HOME_PAGE)
        self.assertNotIn("无需新增网页入口", HOME_PAGE)

    def test_canonical_redirect(self):
        for method in ("GET", "HEAD"):
            status, headers, body = self.request(method, "/ops")
            self.assertEqual(status, 308)
            self.assertEqual(headers["Location"], "/ops/")
            self.assertEqual(body, b"")

    def test_backend_never_serves_data_or_management(self):
        for path in ("/ops/data.json", "/ops/data.json?refresh=1", "/ops//data.json",
                     "/ops%2fdata.json", "/ops/../data.json", "/ops/restart",
                     "/ops/config", "/ops/logs", "/api/ops", "/ops/snapshot.json"):
            for method in ("GET", "HEAD", "POST"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(method, path)[0], 404)
        self.assertEqual(self.request("POST", "/ops/")[0], 404)

    def test_public_renderer_has_no_write_or_markup_sink(self):
        script = OPS_PAGE.split("<script>", 1)[1].split("</script>", 1)[0]
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(",
                          "document.write", "method:'POST'", "Authorization", "localStorage"):
            self.assertNotIn(forbidden, script)
        self.assertEqual(re.findall(r"fetch\('([^']+)'", script), ["/ops/data.json"])
        self.assertIn("credentials:'omit'", script)
        self.assertIn("setInterval(load,60000)", script)
        self.assertIn("age > 180", script)
        self.assertIn("controller.abort()", script)
        self.assertIn("memory_limit_unlimited === true", script)
        self.assertIn("不等于代理认证成功", OPS_PAGE)
        self.assertIn("不是今日或套餐用量", OPS_PAGE)


NODE_RUNNER = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
class Element {
 constructor(tag) {this.tag=tag;this.children=[];this._text='';this.className='';this.style={};this.handlers={};this.hidden=false;}
 set textContent(v) {this.children=[];this._text=String(v);}
 get textContent() {return this._text+this.children.map(x=>x.textContent).join(' ');}
 append(...values) {this.children.push(...values);}
 replaceChildren(...values) {this._text='';this.children=[...values];}
 addEventListener(name,fn) {this.handlers[name]=fn;}
 get firstChild() {return this.children[0]||null;}
}
const ids={},intervals=[],requests=[],timers=[];
let calls=0;
let now=Date.now();
class TestDate extends Date {static now(){return now;}}
const context={document:{getElementById:id=>ids[id]||(ids[id]=new Element('div')),createElement:tag=>new Element(tag)},
 Date:TestDate,Number,Object,Array,String,Math,AbortController,setTimeout,clearTimeout,
 setInterval:(fn,ms)=>{intervals.push(ms);timers.push({fn,ms});},
 fetch:async(url,opts)=>{requests.push({url,cache:opts.cache,credentials:opts.credentials});calls++;
  if(input.fail || (input.fail_second&&calls>1)) throw new Error('fetch failed');
  return {ok:true,json:async()=>input.snapshot};}
};
vm.runInNewContext(input.script,context);
setTimeout(async()=>{
 if(input.fail_second){await ids.refresh.handlers.click();}
 if(input.advance_ms){now+=input.advance_ms;for(const timer of timers)if(timer.ms===10000)timer.fn();}
 const elements={};for(const [key,n] of Object.entries(ids))elements[key]={text:n.textContent,hidden:n.hidden,className:n.className};
 const tags=[];function walk(n){tags.push(n.tag);for(const c of n.children)walk(c);}for(const n of Object.values(ids))walk(n);
 process.stdout.write(JSON.stringify({elements,requests,intervals,tags}));
},25);
"""


@unittest.skipUnless(shutil.which("node"), "Node is needed for executable UI regression tests")
class OpsRendererTests(unittest.TestCase):
    def probe_fixture(self, scope, status="pass"):
        now = datetime.datetime.now(datetime.timezone.utc)
        value = {"scope": scope, "status": status, "checked_at": now.isoformat(),
                 "expires_at": (now + datetime.timedelta(minutes=30)).isoformat()}
        if scope == "vix_source":
            value.update(code="vix_source_valid" if status == "pass" else "vix_source_quality_failed",
                         source_as_of=(now - datetime.timedelta(hours=12)).isoformat())
        else:
            value.update(model="xai/grok-4.6", code="pi_probe_valid" if status == "pass" else "auth_required")
        return value

    def idle_pi(self):
        return {"id": "pi_requests", "label": "pi 请求结果", "status": "unknown",
                "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "sample_status": "idle", "sample_window_seconds": 86400,
                "issues": ["近 24 小时无已完成请求样本；当前可用性未验证"]}

    def fixture(self):
        return {
            "schema_version": 1,
            "exported_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "interval_seconds": 60,
            "host": {"cpu_percent": 0, "cpu_count": 1, "load": [0, 0.1, 0.2],
                     "memory_total_bytes": 2048, "memory_available_bytes": 1024,
                     "disk_total_bytes": 100, "disk_used_bytes": 45},
            "services": [{"id": "sing-box", "label": "sing-box", "active_state": "active",
                          "sub_state": "running", "memory_bytes": 1024, "memory_limit_bytes": None,
                          "restarts": 0}],
            "checks": [{"id": "drift", "label": "配置一致性", "status": "ok", "issues": []}],
            "network": {"listening_services": [], "subscriptions": []},
        }

    def render(self, snapshot=None, **options):
        script = OPS_PAGE.split("<script>", 1)[1].split("</script>", 1)[0]
        payload = {"script": script, "snapshot": snapshot, **options}
        process = subprocess.run([shutil.which("node"), "-e", NODE_RUNNER],
                                 input=json.dumps(payload), capture_output=True, text=True, timeout=5)
        self.assertEqual(process.returncode, 0, process.stderr)
        return json.loads(process.stdout)

    def test_real_values_zero_and_null_are_distinct(self):
        result = self.render(self.fixture())
        self.assertIn("0.0%", result["elements"]["metrics"]["text"])
        self.assertIn("50.0%", result["elements"]["metrics"]["text"])
        self.assertIn("45.0%", result["elements"]["metrics"]["text"])
        self.assertIn("峰值 未采集", result["elements"]["services"]["text"])
        self.assertNotIn("无上限", result["elements"]["services"]["text"])
        self.assertEqual(result["elements"]["summary-title"]["text"], "服务与巡检未见异常")
        self.assertEqual(result["requests"], [{"url":"/ops/data.json", "cache":"no-store", "credentials":"omit"}])
        self.assertIn(60000, result["intervals"])

    def test_summary_denominator_is_monitored_services_not_entire_host(self):
        data = self.fixture()
        data["services"].append({"id": "signal-gate", "label": "Signal Gate · 研究与资讯收件",
                                 "active_state": "active", "sub_state": "running"})
        result = self.render(data)
        self.assertIn("2 / 2 个已监测服务运行中", result["elements"]["summary-copy"]["text"])
        self.assertIn("并非整机全部服务", result["elements"]["summary-copy"]["text"])
        self.assertIn("研究与资讯收件", result["elements"]["services"]["text"])

    def test_unknown_signal_gate_prevents_healthy_summary(self):
        data = self.fixture()
        data["services"].append({"id": "signal-gate", "label": "Signal Gate · 研究与资讯收件",
                                 "active_state": "unknown", "sub_state": "unknown"})
        result = self.render(data)
        self.assertIn("1 / 2 个已监测服务运行中", result["elements"]["summary-copy"]["text"])
        self.assertIn("1 项状态未验证", result["elements"]["summary-copy"]["text"])
        self.assertEqual(result["elements"]["summary-title"]["text"], "状态未完整验证")
        self.assertNotIn("ok", result["elements"]["summary-badge"]["className"].split())

    def test_explicit_unlimited_is_not_missing(self):
        data = self.fixture()
        data["services"][0]["memory_limit_unlimited"] = True
        self.assertIn("无上限", self.render(data)["elements"]["services"]["text"])

    def test_empty_collections_do_not_claim_health(self):
        data = self.fixture()
        data["services"] = []
        data["checks"] = []
        result = self.render(data)
        self.assertEqual(result["elements"]["summary-title"]["text"], "状态未完整验证")
        self.assertIn("未采集", result["elements"]["services"]["text"])
        self.assertIn("未采集", result["elements"]["checks"]["text"])

    def test_pi_idle_shows_real_evidence_time_not_collector_success(self):
        data = self.fixture()
        data["checks"].append({
            "id": "pi_requests", "label": "pi 请求结果", "status": "unknown",
            "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "last_success_at": "2026-09-15T09:15:58+00:00",
            "last_result_at": "2026-09-15T09:15:58+00:00",
            "sample_status": "idle", "sample_window_seconds": 86400,
            "issues": ["近 24 小时无已完成请求样本；当前可用性未验证"],
        })
        result = self.render(data)
        checks = result["elements"]["checks"]["text"]
        self.assertIn("空闲未验证", checks)
        self.assertIn("最近成功", checks)
        self.assertNotIn("最近成功 未采集", checks)
        self.assertIn("近期样本（24 小时）：无结束样本", checks)
        self.assertEqual(result["elements"]["summary-title"]["text"], "状态未完整验证")
        self.assertNotIn("ok", result["elements"]["summary-badge"]["className"].split())

    def test_vix_retest_pass_keeps_historical_report_problem(self):
        data = self.fixture()
        data["checks"].append({"id": "morning", "label": "海外晨报", "status": "error",
                               "issues": ["历史晨报缺 VIX"],
                               "source_validation": self.probe_fixture("vix_source")})
        result = self.render(data)
        checks = result["elements"]["checks"]["text"]
        self.assertIn("历史晨报缺 VIX", checks)
        self.assertIn("当次晨报质量记录", checks)
        self.assertIn("VIX 来源复测通过；不能证明整份已发报告完整", checks)
        self.assertIn("复测 ", checks)
        self.assertIn("来源数据时间", checks)
        self.assertEqual(result["elements"]["summary-title"]["text"], "需要关注")
        self.assertIn("1 项巡检需关注", result["elements"]["summary-copy"]["text"])

    def test_pi_controlled_pass_does_not_claim_real_business_success(self):
        data = self.fixture()
        pi = self.idle_pi()
        pi["controlled_validation"] = self.probe_fixture("pi_research_completion")
        data["checks"].append(pi)
        result = self.render(data)
        checks = result["elements"]["checks"]["text"]
        self.assertIn("近 24 小时无已完成请求样本", checks)
        self.assertIn("空闲未验证", checks)
        self.assertIn("Grok 4.6 单次模型完成", checks)
        self.assertIn("未验证工具与完整业务流程", checks)
        self.assertEqual(result["elements"]["summary-title"]["text"], "状态未完整验证")

    def test_pi_auth_failure_is_attention_while_idle_sample_remains_unknown(self):
        data = self.fixture()
        pi = self.idle_pi()
        pi["controlled_validation"] = self.probe_fixture("pi_research_completion", "fail")
        pi["controlled_validation"].update(label="RAW_SECRET", error="RAW_ERROR")
        data["checks"].append(pi)
        result = self.render(data)
        checks = result["elements"]["checks"]["text"]
        self.assertIn("Grok 授权已失效，需重新授权", checks)
        self.assertIn("近 24 小时无已完成请求样本", checks)
        self.assertIn("空闲未验证", checks)
        self.assertNotIn("RAW_", checks)
        self.assertIn("真实使用样本", checks)
        self.assertIn("pi 受控实测", checks)
        self.assertEqual(result["elements"]["summary-title"]["text"], "需要关注")
        self.assertIn("1 项巡检需关注", result["elements"]["summary-copy"]["text"])
        self.assertIn("1 项状态未验证", result["elements"]["summary-copy"]["text"])

    def test_probe_scope_model_and_time_fail_closed(self):
        now = datetime.datetime.now(datetime.timezone.utc)
        changes = ({"scope": "other"}, {"status": "other"}, {"code": "unknown_code"},
                   {"checked_at": (now + datetime.timedelta(minutes=2)).isoformat()},
                   {"checked_at": "2026-10-08T24:00:00Z"}, {"checked_at": "2026-10-08T12:00:00"},
                   {"expires_at": (now - datetime.timedelta(seconds=1)).isoformat()})
        for scope, field in (("vix_source", "source_validation"), ("pi_research_completion", "controlled_validation")):
            specific = ({"source_as_of": None}, {"source_as_of": "bad"},
                        {"source_as_of": (now + datetime.timedelta(minutes=2)).isoformat()},
                        {"source_as_of": (now - datetime.timedelta(hours=25)).isoformat()},
                        {"source_as_of": (now - datetime.timedelta(hours=23, minutes=45)).isoformat()},
                        {"status": "fail", "code": "vix_source_unverified"}) if scope == "vix_source" else ({"model": "other"}, {"status": "fail", "code": "probe_error"}, {"status": "fail", "code": "busy"})
            for change in (*changes, *specific, {"expires_at": (now + datetime.timedelta(hours=2)).isoformat()}):
                data = self.fixture()
                row = self.idle_pi() if scope == "pi_research_completion" else {"id": "morning", "status": "error", "issues": ["历史晨报缺 VIX"]}
                row[field] = {**self.probe_fixture(scope), **change}
                data["checks"].append(row)
                with self.subTest(scope=scope, change=change):
                    checks = self.render(data)["elements"]["checks"]["text"]
                    self.assertNotIn("复测通过", checks)
                    self.assertNotIn("受控实测通过", checks)
                    self.assertIn("复测未验证", checks)

    def test_probe_expiry_stale_snapshot_and_failed_refresh_remove_pass_badges(self):
        data = self.fixture()
        pi = self.idle_pi()
        pi["controlled_validation"] = self.probe_fixture("pi_research_completion")
        checked = datetime.datetime.fromisoformat(pi["controlled_validation"]["checked_at"])
        pi["controlled_validation"]["expires_at"] = (checked + datetime.timedelta(seconds=60)).isoformat()
        data["checks"].append(pi)
        data["checks"].append({"id": "morning", "status": "error", "issues": ["历史晨报缺 VIX"],
                               "source_validation": self.probe_fixture("vix_source")})
        for options in ({"advance_ms": 181000}, {"fail_second": True}):
            with self.subTest(options=options):
                checks = self.render(data, **options)["elements"]["checks"]["text"]
                self.assertNotIn("复测通过", checks)
                self.assertIn("历史晨报缺 VIX", checks)
                self.assertIn("近 24 小时无已完成请求样本", checks)
        checks = self.render(data, advance_ms=61000)["elements"]["checks"]["text"]
        self.assertNotIn("受控实测通过", checks)
        self.assertIn("VIX 来源复测通过", checks)

    def test_old_pi_snapshot_with_green_status_but_no_sample_proof_is_not_green(self):
        data = self.fixture()
        data["checks"].append({"id": "pi_requests", "label": "pi 请求结果",
                               "status": "ok", "issues": [],
                               "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()})
        result = self.render(data)
        self.assertEqual(result["elements"]["summary-title"]["text"], "状态未完整验证")
        self.assertIn("近期请求成功证据未验证", result["elements"]["checks"]["text"])
        self.assertNotIn("ok", result["elements"]["summary-badge"]["className"].split())

    def test_stale_snapshot_is_visibly_historical(self):
        data = self.fixture()
        data["exported_at"] = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=4)).isoformat()
        result = self.render(data)
        self.assertIn("历史状态", result["elements"]["banner"]["text"])
        self.assertFalse(result["elements"]["banner"]["hidden"])
        self.assertEqual(result["elements"]["summary-title"]["text"], "历史快照")

    def test_future_and_malformed_snapshots_fail_closed(self):
        future = self.fixture()
        future["exported_at"] = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=1)).isoformat()
        malformed = self.fixture()
        malformed["checks"][0]["issues"] = {"bad": "not an array"}
        for data in (None, {}, future, malformed, {**self.fixture(), "schema_version": 2}):
            with self.subTest(data=data):
                result = self.render(data)
                self.assertEqual(result["elements"]["summary-title"]["text"], "状态暂时未知")
                self.assertIn("没有用示例数据代替", result["elements"]["banner"]["text"])
                self.assertNotIn("services", result["elements"])

    def test_network_failure_has_unknown_state_then_preserves_prior_data(self):
        result = self.render(fail=True)
        self.assertEqual(result["elements"]["summary-title"]["text"], "状态暂时未知")
        result = self.render(self.fixture(), fail_second=True)
        self.assertEqual(len(result["requests"]), 2)
        self.assertIn("sing-box", result["elements"]["services"]["text"])
        self.assertIn("保留上次快照", result["elements"]["banner"]["text"])
        self.assertEqual(result["elements"]["summary-title"]["text"], "历史快照")

    def test_values_are_rendered_as_text_not_markup(self):
        data = self.fixture()
        payload = '<img src=x onerror="evil()"><script>evil()</script>'
        data["services"][0]["label"] = payload
        data["checks"][0]["issues"] = [payload]
        result = self.render(data)
        self.assertIn(payload, result["elements"]["services"]["text"])
        self.assertIn(payload, result["elements"]["checks"]["text"])
        self.assertNotIn("img", result["tags"])
        self.assertNotIn("script", result["tags"])

    def test_network_states_and_mtg_counters_keep_scope(self):
        data = self.fixture()
        data["checks"][0]["status"] = "stale"
        data["network"] = {
            "subscriptions": [{"id":"mihomo", "label":"mihomo", "download":"ok", "format":"ok",
                               "format_name":"clash-yaml", "nodes":"unverified", "check":"tcp_only",
                               "endpoints":0, "reachable":0, "certificate_days":20}],
            "mtg": {"client_connections":0, "telegram_connections":2, "traffic_to_client_bytes":2048,
                    "traffic_from_client_bytes":1024, "concurrency_limited":0, "replay_attacks":0,
                    "domain_fronting":1},
        }
        result = self.render(data)
        self.assertIn("数据过期", result["elements"]["checks"]["text"])
        self.assertIn("验证未完整", result["elements"]["subscriptions"]["text"])
        self.assertIn("Clash / mihomo YAML", result["elements"]["subscriptions"]["text"])
        self.assertIn("客户端 0", result["elements"]["mtg"]["text"])
        self.assertIn("不是计费数据", result["elements"]["mtg"]["text"])
        self.assertEqual(result["elements"]["summary-title"]["text"], "需要关注")

    def test_unattributed_subscription_failure_stays_failed(self):
        data = self.fixture()
        data["network"] = {
            "subscriptions": [{"id":"iphone", "label":"iPhone", "overall":"error", "download":"unknown", "format":"unknown", "nodes":"unknown"}],
            "listening_services": [{"id":"sing-box", "label":"sing-box", "scope":"public", "transport":"tcp", "port":8443, "state":"listening"}],
        }
        result = self.render(data)
        self.assertIn("检查异常", result["elements"]["subscriptions"]["text"])
        self.assertNotIn("验证未完整", result["elements"]["subscriptions"]["text"])
        self.assertIn("全部 / 公网地址监听", result["elements"]["listeners"]["text"])
        self.assertIn("防火墙已放行", result["elements"]["listeners"]["text"])


if __name__ == "__main__":
    unittest.main()
