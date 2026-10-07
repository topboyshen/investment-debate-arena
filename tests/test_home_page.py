"""Execute the public home summary against offline fixtures, never real feeds."""

from datetime import datetime, timedelta, timezone
from html.parser import HTMLParser
import http.client
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))
from home_page import HOME_PAGE
from portal_pages import HOME_PAGE as PORTAL_HOME_PAGE
from server import Handler, SECURITY_HEADERS


SCRIPT = HOME_PAGE.split("<script>", 1)[1].split("</script>", 1)[0]
SERVICE_IDS = (
    "sing-box", "mtg", "cloudflared", "nginx", "netdata", "fail2ban", "ssh",
    "mini-hermes", "mini-hermes-pi", "signal-gate", "signal-gate-review",
    "investment-debate-arena",
)
CHECK_AGES = {"runtime": 1500, "pi_requests": 1500, "subscriptions": 2700,
              "config_drift": 2700, "morning": 97200}

NODE_RUNNER = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
let now=Date.parse(input.now);
class Clock extends Date {
 constructor(...args){super(...(args.length?args:[now]));}
 static now(){return now;}
}
const context={Date:Clock,Number,Object,Array,String,Math,Intl,Set};
if(input.mode==='pure'){
 vm.runInNewContext(input.script,context);
 process.stdout.write(JSON.stringify(context[input.function](input.snapshot,now)));
}else{
 const ids={},timers=[],requests=[],calls={};
 class Element {
  constructor(tag){this.tag=tag;this._text='';this.className='';this.children=[];this.handlers={};this.attrs={};this.disabled=false;}
  set textContent(value){this._text=String(value);this.children=[];}
  get textContent(){return this._text+this.children.map(x=>x.textContent).join(' ');}
  append(...values){this.children.push(...values);}
  replaceChildren(...values){this._text='';this.children=[...values];}
  setAttribute(key,value){this.attrs[key]=String(value);}
  addEventListener(name,fn){this.handlers[name]=fn;}
 }
 for(const match of input.html.matchAll(/\bid="([^"]+)"/g))ids[match[1]]=new Element('div');
 const created=[];
 context.document={getElementById:id=>ids[id]||null,createElement:tag=>{created.push(tag);return new Element(tag);}};
 Object.assign(context,{
  AbortController,setTimeout,clearTimeout,
  setInterval:(fn,ms)=>{timers.push({fn,ms});return timers.length;},
  fetch:async(url,options)=>{
   const name=url==='/reports/data.json'?'reports':url==='/ops/data.json'?'ops':null;
   if(!name)throw new Error('unexpected fetch URL: '+url);
   calls[name]=(calls[name]||0)+1;
   requests.push({url,method:options.method||'GET',credentials:options.credentials,
                  cache:options.cache,headers:options.headers});
   const behavior=(input.behavior||{})[name]||{};
   if(behavior.fail||(behavior.fail_second&&calls[name]>1))throw new Error('synthetic failure');
   return {ok:behavior.status?behavior.status===200:true,status:behavior.status||200,
     headers:{get:()=>behavior.content_type||'application/json; charset=utf-8'},
     json:async()=>{if(behavior.invalid_json)throw new Error('synthetic invalid JSON');return input[name];}};
  }
 });
 vm.runInNewContext(input.script,context);
 setTimeout(async()=>{
  try{
   if(input.refresh)await ids.refresh.handlers.click();
   if(input.advance_ms){now+=input.advance_ms;for(const timer of timers)if(timer.ms===15000)timer.fn();}
   const elements={};for(const [id,node] of Object.entries(ids))elements[id]={text:node.textContent,className:node.className,disabled:node.disabled};
   process.stdout.write(JSON.stringify({elements,requests,timers:timers.map(timer=>timer.ms),created}));
  }catch(error){process.stderr.write(error.stack);process.exitCode=1;}
 },20);
}
"""


class HomeSummaryTests(unittest.TestCase):
    NOW = datetime(2026, 9, 22, 7, 30, tzinfo=timezone.utc)

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise RuntimeError("Node is required: home renderer checks must not silently skip")

    def reports_fixture(self):
        return {"schema_version": 1, "exported_at": self.NOW.isoformat(),
                "sources": [{"id": "overseas", "label": "海外市场晨报", "state": "ok",
                             "latest_report_date": "2026-09-22"},
                            {"id": "signal_gate", "label": "Signal Gate 日报", "state": "ok",
                             "latest_report_date": "2026-09-22"}]}

    def ops_fixture(self):
        checks = [{"id": key, "status": "ok", "issues": [],
                   "checked_at": self.NOW.isoformat()} for key in CHECK_AGES]
        next(row for row in checks if row["id"] == "pi_requests").update(
            sample_status="recent_success", sample_window_seconds=86400,
            last_success_at=(self.NOW - timedelta(minutes=1)).isoformat())
        return {"schema_version": 1, "exported_at": self.NOW.isoformat(),
                "services": [{"id": key, "active_state": "active", "sub_state": "running"}
                             for key in SERVICE_IDS],
                "checks": checks}

    def execute(self, **options):
        payload = {"script": SCRIPT, "html": HOME_PAGE, "now": self.NOW.isoformat(), **options}
        result = subprocess.run([self.node, "-e", NODE_RUNNER], input=json.dumps(payload),
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def summary(self, function, snapshot, **options):
        return self.execute(mode="pure", function=function, snapshot=snapshot, **options)

    def browser(self, **options):
        return self.execute(mode="browser", reports=self.reports_fixture(),
                            ops=self.ops_fixture(), **options)

    def test_complete_snapshot_reports_actual_scope_and_assistant_state(self):
        reports = self.summary("summarizeReports", self.reports_fixture())
        ops = self.summary("summarizeOps", self.ops_fixture())
        self.assertEqual(reports["state"], "ready")
        self.assertEqual(reports["items"]["overseas"]["date"], "2026-09-22")
        self.assertEqual(ops["state"], "ok")
        self.assertEqual((ops["active"], ops["total"]), (12, 12))
        self.assertEqual((ops["serviceIssues"], ops["checkIssues"], ops["unknown"]), (0, 0, 0))
        self.assertEqual(ops["assistant"], "ok")

    def test_latest_retained_date_does_not_claim_today_or_delivery(self):
        data = self.reports_fixture()
        data["sources"][0]["latest_report_date"] = "2026-09-19"
        data["sources"][1]["latest_report_date"] = "2026-09-21"
        result = self.summary("summarizeReports", data)
        self.assertEqual(result["state"], "ready")
        self.assertEqual(result["items"]["overseas"]["date"], "2026-09-19")
        rendered = self.execute(mode="browser", reports=data, ops=self.ops_fixture())
        self.assertIn("不代表已发送", rendered["elements"]["reports-status"]["text"])
        self.assertIn("不保证当日有新报告", rendered["elements"]["reports-meta"]["text"])
        self.assertNotIn("已发送", rendered["elements"]["report-overseas"]["text"])

    def test_missing_duplicate_and_malformed_sources_are_not_ready(self):
        fixtures = []
        for rows in ([], None, {}, [self.reports_fixture()["sources"][0]],
                     self.reports_fixture()["sources"] * 2,
                     [None, self.reports_fixture()["sources"][1]]):
            fixtures.append({**self.reports_fixture(), "sources": rows})
        for change in ({"state": "unavailable"}, {"state": "unknown"},
                       {"state": "partial"}, {"latest_report_date": None},
                       {"latest_report_date": "2026-09-23"}, {"latest_report_date": "2026-02-30"}):
            data = self.reports_fixture()
            data["sources"][0].update(change)
            fixtures.append(data)
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertNotEqual(self.summary("summarizeReports", fixture)["state"], "ready")

    def test_partial_source_remains_partial_with_an_existing_report(self):
        data = self.reports_fixture()
        data["sources"][0]["state"] = "partial"
        result = self.summary("summarizeReports", data)
        self.assertEqual(result["state"], "partial")
        self.assertEqual(result["items"]["overseas"]["date"], "2026-09-22")

    def test_missing_duplicate_and_malformed_monitored_rows_cannot_be_green(self):
        fixtures = []
        for collection in ("services", "checks"):
            for rows in ([], None, {}, [None], self.ops_fixture()[collection][:-1],
                         self.ops_fixture()[collection] + [self.ops_fixture()[collection][0]]):
                data = self.ops_fixture()
                data[collection] = rows
                fixtures.append(data)
        data = self.ops_fixture()
        data["services"] = [row for row in data["services"] if row["id"] != "signal-gate"]
        fixtures.append(data)
        for fixture in fixtures:
            with self.subTest(fixture=fixture):
                self.assertNotEqual(self.summary("summarizeOps", fixture)["state"], "ok")

    def test_unknown_service_fields_do_not_count_as_running(self):
        for change in ({"active_state": "unknown"}, {"sub_state": "unknown"},
                       {"active_state": None}, {"sub_state": None}):
            data = self.ops_fixture()
            data["services"][0].update(change)
            with self.subTest(change=change):
                result = self.summary("summarizeOps", data)
                self.assertEqual(result["state"], "unknown")
                self.assertEqual(result["active"], 11)
                self.assertEqual(result["unknown"], 1)

    def test_service_and_check_failures_count_separately(self):
        data = self.ops_fixture()
        data["services"][0].update(active_state="failed", sub_state="failed")
        data["checks"][0].update(status="error", issues=["public aggregate issue"])
        result = self.summary("summarizeOps", data)
        self.assertEqual(result["state"], "warning")
        self.assertEqual((result["active"], result["serviceIssues"], result["checkIssues"]), (11, 1, 1))
        self.assertEqual(result["assistant"], "ok")
        for key in ("mini-hermes", "mini-hermes-pi"):
            data = self.ops_fixture()
            next(row for row in data["services"] if row["id"] == key).update(active_state="failed", sub_state="failed")
            self.assertEqual(self.summary("summarizeOps", data)["assistant"], "warning")

    def test_invalid_checks_and_contradictory_clear_never_turn_green(self):
        for change in ({"status": "unknown"}, {"status": "stale"}, {"status": "other"},
                       {"issues": None}, {"issues": [None]}, {"issues": {}},
                       {"checked_at": None}, {"checked_at": "2026-09-22T15:30:00"},
                       {"checked_at": (self.NOW + timedelta(seconds=61)).isoformat()},
                       {"status": "ok", "issues": ["must not hide this"]}):
            data = self.ops_fixture()
            data["checks"][0].update(change)
            with self.subTest(change=change):
                self.assertNotEqual(self.summary("summarizeOps", data)["state"], "ok")

    def test_old_pi_snapshot_cannot_claim_current_request_health(self):
        for change in ({"sample_status": "idle"},
                       {"last_success_at": (self.NOW - timedelta(hours=25)).isoformat()},
                       {"sample_window_seconds": None}):
            data = self.ops_fixture()
            pi = next(row for row in data["checks"] if row["id"] == "pi_requests")
            pi.update(change)
            with self.subTest(change=change):
                result = self.summary("summarizeOps", data)
                self.assertEqual(result["state"], "unknown")
                self.assertEqual(result["unknown"], 1)
        data = self.ops_fixture()
        next(row for row in data["checks"] if row["id"] == "pi_requests").pop("last_success_at")
        self.assertEqual(self.summary("summarizeOps", data)["state"], "unknown")

    def test_fresh_export_cannot_refresh_the_underlying_check_timestamp(self):
        for key, max_age in CHECK_AGES.items():
            data = self.ops_fixture()
            row = next(row for row in data["checks"] if row["id"] == key)
            row["checked_at"] = (self.NOW - timedelta(seconds=max_age + 1)).isoformat()
            with self.subTest(check=key):
                result = self.summary("summarizeOps", data)
                self.assertEqual(result["state"], "unknown")
                self.assertEqual(result["unknown"], 1)

    def test_missing_future_and_timezone_free_export_times_fail_closed(self):
        for function, factory in (("summarizeReports", self.reports_fixture),
                                  ("summarizeOps", self.ops_fixture)):
            fixtures = [None, [], {}, "bad", {**factory(), "schema_version": 2}]
            for stamp in (None, "", "bad", "2026-09-22T15:30:00",
                          (self.NOW + timedelta(seconds=61)).isoformat()):
                data = factory()
                data["exported_at"] = stamp
                fixtures.append(data)
            missing = factory()
            del missing["exported_at"]
            fixtures.append(missing)
            for fixture in fixtures:
                with self.subTest(function=function, fixture=fixture):
                    self.assertEqual(self.summary(function, fixture)["state"], "unknown")

    def test_snapshot_age_becomes_stale_with_correct_independent_limits(self):
        for function, factory, limit in (("summarizeReports", self.reports_fixture, 1800),
                                         ("summarizeOps", self.ops_fixture, 180)):
            data = factory()
            data["exported_at"] = (self.NOW - timedelta(seconds=limit + 1)).isoformat()
            with self.subTest(function=function):
                result = self.summary(function, data)
                self.assertEqual(result["state"], "stale")
                if function == "summarizeOps":
                    self.assertEqual(result["assistant"], "stale")

    def test_calendar_normalization_cannot_turn_invalid_times_into_fresh_data(self):
        cases = (("2026-03-02T12:00:00Z", "2026-02-30T12:00:00Z"),
                 ("2026-09-22T00:00:00Z", "2026-09-21T24:00:00Z"))
        for now, invalid in cases:
            for function, factory in (("summarizeReports", self.reports_fixture),
                                      ("summarizeOps", self.ops_fixture)):
                data = factory()
                data["exported_at"] = invalid
                with self.subTest(function=function, invalid=invalid):
                    self.assertEqual(self.summary(function, data, now=now)["state"], "unknown")
            data = self.ops_fixture()
            data["exported_at"] = now
            for check in data["checks"]:
                check["checked_at"] = now
            next(check for check in data["checks"] if check["id"] == "pi_requests")["last_success_at"] = now
            data["checks"][0]["checked_at"] = invalid
            with self.subTest(check_timestamp=invalid):
                result = self.summary("summarizeOps", data, now=now)
                self.assertEqual(result["state"], "unknown")
                self.assertEqual(result["unknown"], 1)

    def test_public_fetch_is_get_omit_no_store_and_only_two_feeds(self):
        result = self.browser()
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual({row["url"] for row in result["requests"]}, {"/reports/data.json", "/ops/data.json"})
        for row in result["requests"]:
            self.assertEqual(row["method"], "GET")
            self.assertEqual(row["credentials"], "omit")
            self.assertEqual(row["cache"], "no-store")
            self.assertEqual(row["headers"], {"Accept": "application/json"})
        self.assertEqual(set(result["timers"]), {15000, 60000})
        self.assertFalse(result["elements"]["refresh"]["disabled"])
        self.assertIn("12 / 12 项已监测服务", result["elements"]["ops-count"]["text"])
        self.assertIn("不等于整机全部服务或业务成功", result["elements"]["ops-meta"]["text"])

    def test_browser_rechecks_staleness_without_fetching_new_payload(self):
        result = self.browser(advance_ms=181000)
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual(result["elements"]["ops-status"]["className"], "status stale")
        self.assertEqual(result["elements"]["assistant-status"]["className"], "status stale")
        self.assertEqual(result["elements"]["reports-status"]["className"], "status ready")
        result = self.browser(advance_ms=1801000)
        self.assertEqual(len(result["requests"]), 2)
        self.assertEqual(result["elements"]["reports-status"]["className"], "status stale")

    def test_fetch_failures_are_independent_and_never_leave_a_green_badge(self):
        for endpoint in ("reports", "ops"):
            for failure in ({"fail": True}, {"status": 401}, {"status": 503},
                            {"content_type": "text/html"}, {"invalid_json": True}):
                with self.subTest(endpoint=endpoint, failure=failure):
                    result = self.browser(behavior={endpoint: failure})
                    elements = result["elements"]
                    self.assertEqual(elements[endpoint + "-status"]["className"], "status unknown")
                    if endpoint == "reports":
                        self.assertEqual(elements["ops-status"]["className"], "status ok")
                        self.assertEqual(elements["assistant-status"]["className"], "status ok")
                    else:
                        self.assertEqual(elements["reports-status"]["className"], "status ready")
                        self.assertEqual(elements["assistant-status"]["className"], "status unknown")

    def test_failed_refresh_downgrades_only_the_failed_feed(self):
        for endpoint in ("reports", "ops"):
            result = self.browser(refresh=True, behavior={endpoint: {"fail_second": True}})
            with self.subTest(endpoint=endpoint):
                self.assertEqual(len(result["requests"]), 4)
                self.assertEqual(result["elements"][endpoint + "-status"]["className"], "status unknown")
                other = "ops" if endpoint == "reports" else "reports"
                self.assertEqual(result["elements"][other + "-status"]["className"],
                                 "status ok" if other == "ops" else "status ready")
                self.assertFalse(result["elements"]["refresh"]["disabled"])

    def test_untrusted_source_labels_and_issue_text_cannot_inject_markup(self):
        reports, ops = self.reports_fixture(), self.ops_fixture()
        payload = '<img src=x onerror="evil()"><script>evil()</script>'
        reports["sources"][0].update(label=payload, note=payload)
        ops["services"][0]["label"] = payload
        ops["checks"][0].update(label=payload, issues=[payload])
        result = self.execute(mode="browser", reports=reports, ops=ops)
        self.assertNotIn("img", result["created"])
        self.assertNotIn("script", result["created"])
        # This summary uses fixed labels, not arbitrary upstream display names.
        self.assertNotIn(payload, " ".join(row["text"] for row in result["elements"].values()))
        self.assertEqual(result["elements"]["ops-status"]["className"], "status warning")
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(",
                          "document.write", "Authorization", "localStorage", "method:'POST'"):
            self.assertNotIn(forbidden, SCRIPT)


class HomeRoutesTests(unittest.TestCase):
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
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        connection.request(method, path)
        result = connection.getresponse()
        value = result.status, dict(result.getheaders()), result.read()
        connection.close()
        return value

    def test_home_is_public_hardened_and_same_page_as_compatibility_export(self):
        self.assertEqual(PORTAL_HOME_PAGE, HOME_PAGE)
        for method in ("GET", "HEAD"):
            with self.subTest(method=method):
                status, headers, body = self.request(method, "/")
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
                self.assertEqual(headers["Cache-Control"], "no-store")
                self.assertEqual(int(headers["Content-Length"]), len(HOME_PAGE.encode()))
                self.assertNotIn("WWW-Authenticate", headers)
                for name in SECURITY_HEADERS:
                    self.assertIn(name, headers)
                self.assertEqual(body, b"" if method == "HEAD" else HOME_PAGE.encode())

    def test_home_adds_no_backend_data_management_or_source_file_route(self):
        for path in ("/reports/data.json", "/ops/data.json", "/ops/config", "/ops/restart",
                     "/app/home_page.py", "/.env", "/api/ops", "/reports/resend"):
            for method in ("GET", "HEAD", "POST"):
                with self.subTest(path=path, method=method):
                    self.assertEqual(self.request(method, path)[0], 404)
        self.assertEqual(self.request("POST", "/")[0], 404)

    def test_card_hierarchy_links_and_scope_are_explicit(self):
        class Elements(HTMLParser):
            def __init__(self):
                super().__init__()
                self.cards, self.links = [], []

            def handle_starttag(self, tag, attrs):
                values = dict(attrs)
                if tag == "article":
                    self.cards.append(values.get("id"))
                if tag == "a":
                    self.links.append(values)

        parsed = Elements()
        parsed.feed(HOME_PAGE)
        self.assertEqual(parsed.cards, ["reports-card", "assistant-card", "ops-card", "arena-card"])
        allowed = {"#main", "/", "/reports/", "/reports/?source=overseas", "/reports/?source=signal_gate",
                   "/ops/", "/netdata/", "/arena/", "https://t.me/lucyjie_clawdbot"}
        self.assertEqual({link["href"] for link in parsed.links}, allowed)
        external = next(link for link in parsed.links if link["href"].startswith("https://"))
        self.assertEqual(external["target"], "_blank")
        self.assertEqual(set(external["rel"].split()), {"noopener", "noreferrer"})
        self.assertIn("当前收录 DediRock 本机项目", HOME_PAGE)
        self.assertIn("nnG8 研究项目与完整研究附件尚未接入此站", HOME_PAGE)
        self.assertIn("进程运行不等于消息收发成功", HOME_PAGE)
        self.assertIn("未读取的状态不代表正常", HOME_PAGE)
        self.assertIn('href="/favicon.svg?v=1"', HOME_PAGE)
        self.assertRegex(HOME_PAGE, r"@media\(max-width:680px\).*\.grid\{grid-template-columns:1fr")


if __name__ == "__main__":
    unittest.main()
