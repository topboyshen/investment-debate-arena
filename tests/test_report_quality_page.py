"""Execute the actual report page against synthetic snapshots; never use network."""
from datetime import datetime, timedelta, timezone
import importlib.util
import json
from pathlib import Path
import re
import shutil
import subprocess
import unittest

SPEC = importlib.util.spec_from_file_location(
    "quality_portal_pages", Path(__file__).resolve().parents[1] / "app/portal_pages.py")
pages = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pages)

NODE_RUNNER = r"""
const fs=require('node:fs'),vm=require('node:vm');
const input=JSON.parse(fs.readFileSync(0,'utf8'));
const originalSnapshot=JSON.stringify(input.snapshot);
const ids={},timers=[],requests=[];let calls=0,now=Date.parse(input.now);
class Element {
 constructor(tag){this.tag=tag;this.children=[];this._text='';this.className='';this.handlers={};this.attrs={};this.dataset={};this.hidden=false;this.parentNode=null;}
 set id(value){this._id=value;ids[value]=this;} get id(){return this._id;}
 set textContent(value){this.children=[];this._text=String(value);} get textContent(){return this._text+this.children.map(x=>x.textContent).join(' ');}
 append(...values){for(const value of values){value.parentNode=this;this.children.push(value);}}
 replaceChildren(...values){this._text='';this.children=[];this.append(...values);}
 insertBefore(value,before){const index=this.children.indexOf(before);if(index<0)throw new Error('invalid insertion target');value.parentNode=this;this.children.splice(index,0,value);}
 setAttribute(name,value){this.attrs[name]=String(value);}
 addEventListener(name,fn){this.handlers[name]=fn;}
 querySelectorAll(selector){if(selector!=='button')throw new Error('unsupported selector');return this.children.filter(x=>x.tag==='button');}
 querySelector(selector){return this.children.find(x=>x.tag==='button'&&x.attrs['aria-pressed']==='true')||null;}
 focus(){}
}
const root=new Element('main');
for(const match of input.html.matchAll(/\bid="([^"]+)"/g)){if(!ids[match[1]]){const element=new Element('div');element.id=match[1];root.append(element);}}
for(const source of ['all','overseas','signal_gate']){const button=new Element('button');button.dataset.source=source;ids.filters.append(button);}
class Clock extends Date{constructor(...args){super(...(args.length?args:[now]));}static now(){return now;}}
const context={document:{getElementById:id=>ids[id]||null,createElement:tag=>new Element(tag)},
 Date:Clock,Number,Object,Array,String,Math,Intl,Set,URLSearchParams,location:{search:input.search||''},
 AbortController,setTimeout,clearTimeout,setInterval:(fn,ms)=>{timers.push({fn,ms});return timers.length;},
 fetch:async(url,options)=>{calls++;requests.push({url,credentials:options.credentials,cache:options.cache});
  if(input.fail||(input.fail_second&&calls>1))throw new Error('synthetic fetch failure');
  return {ok:input.http_status?input.http_status===200:true,status:input.http_status||200,
   headers:{get:()=>input.content_type||'application/json'},json:async()=>input.snapshot};}
};
vm.runInNewContext(input.script,context);
setTimeout(async()=>{
 try{
  if(input.select_last){const list=ids.list.querySelectorAll('button');if(list.length)list[list.length-1].handlers.click();}
  if(input.fail_second)await ids.refresh.handlers.click();
  const initialCurrent={text:ids['current-quality-state'].textContent,className:ids['current-quality'].className};
  if(input.advance_ms){now+=input.advance_ms;for(const timer of timers)timer.fn();}
  const elements={};for(const [id,n] of Object.entries(ids))elements[id]={text:n.textContent,className:n.className,hidden:n.hidden};
  const tags=[];function walk(n){tags.push(n.tag);for(const child of n.children)walk(child);}walk(root);
  process.stdout.write(JSON.stringify({elements,requests,timers:timers.map(t=>t.ms),tags,initialCurrent,snapshotUnchanged:JSON.stringify(input.snapshot)===originalSnapshot}));
 }catch(error){process.stderr.write(error.stack);process.exitCode=1;}
},25);
"""


class ReportQualityPageTests(unittest.TestCase):
    NOW = datetime(2026, 9, 21, 4, 0, tzinfo=timezone.utc)  # 12:00 Beijing.

    @classmethod
    def setUpClass(cls):
        cls.node = shutil.which("node")
        if not cls.node:
            raise RuntimeError("Node is required: report quality UI tests must not silently skip")

    def fixture(self):
        return {
            "schema_version": 1,
            "exported_at": self.NOW.isoformat(),
            "sources": [{"id": "signal_gate", "state": "ok", "latest_report_date": "2026-09-21"}],
            "reports": [{"id": "today", "source": "signal_gate", "report_date": "2026-09-21",
                         "text": "Original morning report", "quality_issues": ["nng8:missing"],
                         "delivery_status": "confirmed"},
                        {"id": "archive", "source": "signal_gate", "report_date": "2026-09-20",
                         "text": "Older archived report", "quality_issues": [], "delivery_status": "confirmed"}],
            "signal_gate_quality": {
                "report_date": "2026-09-21",
                "sent_report": {"state": "issues", "delivery_status": "confirmed",
                                "quality_issues": ["nng8:missing"],
                                "generated_at": "2026-09-21T08:16:00+08:00"},
                "current_inputs": {"state": "clear", "report_date": "2026-09-21",
                                   "checked_at": (self.NOW - timedelta(minutes=1)).isoformat(),
                                   "quality_issues": []},
            },
        }

    def render(self, snapshot=None, **options):
        script = pages.REPORTS_PAGE.split("<script>", 1)[1].split("</script>", 1)[0]
        payload = {"html": pages.REPORTS_PAGE, "script": script, "now": self.NOW.isoformat(),
                   "snapshot": snapshot, **options}
        completed = subprocess.run([self.node, "-e", NODE_RUNNER], input=json.dumps(payload),
                                   capture_output=True, text=True, timeout=5)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        return json.loads(completed.stdout)

    def before_generation_fixture(self, now):
        data = self.fixture()
        day = now.astimezone(timezone(timedelta(hours=8))).date().isoformat()
        data["exported_at"] = now.isoformat()
        data["reports"] = [report for report in data["reports"] if report["id"] == "archive"]
        quality = data["signal_gate_quality"]
        quality["report_date"] = day
        quality["sent_report"] = {"state": "not_recorded", "delivery_status": "unknown",
                                  "quality_issues": [], "generated_at": None}
        quality["current_inputs"] = {"state": "issues", "report_date": day,
                                     "checked_at": (now - timedelta(minutes=1)).isoformat(),
                                     "quality_issues": ["nng8:missing"]}
        return data

    def assert_current_issue(self, result):
        self.assertEqual(result["elements"]["current-quality"]["className"], "quality-card quality-card--error")
        self.assertEqual(result["elements"]["current-quality-state"]["text"], "当前输入仍有质量问题")

    def test_only_missing_research_waits_before_weekday_generation(self):
        for time in ("2026-09-21T07:20:00+08:00", "2026-09-21T07:59:00+08:00"):
            now = datetime.fromisoformat(time)
            with self.subTest(time=time):
                result = self.render(self.before_generation_fixture(now), now=time)
                elements = result["elements"]
                self.assertEqual(elements["current-quality-state"]["text"], "研究尚未到生成时间")
                self.assertEqual(elements["current-quality"]["className"], "quality-card quality-card--unknown")
                self.assertIn("北京时间工作日 08:00 开始生成", elements["current-quality-basis"]["text"])
                self.assertIn("不代表已生成或发送", elements["current-quality-basis"]["text"])
                self.assertIn("nng8:missing", elements["current-quality-issues"]["text"])
                self.assertEqual(elements["sent-quality-state"]["text"], "尚无今天的可核验发送记录")
                self.assertTrue(result["snapshotUnchanged"])

    def test_missing_research_is_an_issue_from_0800(self):
        for time in ("2026-09-21T08:00:00+08:00", "2026-09-21T08:15:00+08:00"):
            now = datetime.fromisoformat(time)
            with self.subTest(time=time):
                self.assert_current_issue(self.render(self.before_generation_fixture(now), now=time))

    def test_browser_timer_ends_wait_at_0800_without_new_snapshot(self):
        now = datetime.fromisoformat("2026-09-21T07:59:30+08:00")
        result = self.render(self.before_generation_fixture(now), now=now.isoformat(), advance_ms=30000)
        self.assertEqual(result["initialCurrent"]["text"], "研究尚未到生成时间")
        self.assert_current_issue(result)
        self.assertIn("nng8:missing", result["elements"]["current-quality-issues"]["text"])
        self.assertEqual(len(result["requests"]), 1)
        self.assertIn(30000, result["timers"])
        self.assertTrue(result["snapshotUnchanged"])

    def test_generation_wait_does_not_apply_on_weekends(self):
        for time in ("2026-09-26T07:20:00+08:00", "2026-09-27T07:20:00+08:00"):
            now = datetime.fromisoformat(time)
            with self.subTest(time=time):
                self.assert_current_issue(self.render(self.before_generation_fixture(now), now=time))

    def test_generation_wait_never_hides_other_or_mixed_issues(self):
        now = datetime.fromisoformat("2026-09-21T07:20:00+08:00")
        for issues in (["nng8:invalid"], ["jd:missing"], ["nng8:stale"],
                       ["nng8:missing", "nng8:invalid"], ["nng8:missing", "jd:stale"],
                       ["nng8:missing", "nng8:missing"]):
            data = self.before_generation_fixture(now)
            data["signal_gate_quality"]["current_inputs"]["quality_issues"] = issues
            with self.subTest(issues=issues):
                result = self.render(data, now=now.isoformat())
                self.assert_current_issue(result)
                for issue in issues:
                    self.assertIn(issue, result["elements"]["current-quality-issues"]["text"])

    def test_generation_wait_requires_fresh_valid_current_snapshot(self):
        now = datetime.fromisoformat("2026-09-21T07:20:00+08:00")
        cases = [({"state": "unknown"}, "当前校验状态未知"),
                 ({"state": "stale"}, "当前校验已过期"),
                 ({"state": "clear"}, "当前校验状态未知"),
                 ({"checked_at": None}, "当前校验状态未知"),
                 ({"checked_at": (now - timedelta(minutes=16)).isoformat()}, "当前校验已过期"),
                 ({"checked_at": (now + timedelta(seconds=1)).isoformat()}, "当前输入仍有质量问题"),
                 ({"checked_at": (now + timedelta(seconds=61)).isoformat()}, "当前校验状态未知"),
                 ({"checked_at": "2026-09-20T23:59:00+08:00"}, "当前校验已过期"),
                 ({"report_date": "2026-09-20"}, "当前校验已过期"),
                 ({"report_date": "2026-09-22"}, "当前校验状态未知"),
                 ({"quality_issues": "nng8:missing"}, "当前校验状态未知")]
        for change, headline in cases:
            data = self.before_generation_fixture(now)
            data["signal_gate_quality"]["current_inputs"].update(change)
            with self.subTest(change=change):
                result = self.render(data, now=now.isoformat())
                self.assertEqual(result["elements"]["current-quality-state"]["text"], headline)
                self.assert_current_not_green(result)
        for day in ("2026-09-20", "2026-09-22"):
            data = self.before_generation_fixture(now)
            data["signal_gate_quality"]["report_date"] = day
            with self.subTest(quality_day=day):
                result = self.render(data, now=now.isoformat())
                self.assertNotEqual(result["elements"]["current-quality-state"]["text"], "研究尚未到生成时间")
                self.assert_current_not_green(result)

    def test_generation_wait_does_not_hide_confirmed_or_uncertain_sent_records(self):
        now = datetime.fromisoformat("2026-09-21T07:20:00+08:00")
        for sent in (None, {},
                     {"state": "issues", "delivery_status": "confirmed", "quality_issues": ["nng8:missing"],
                      "generated_at": "2026-09-21T07:10:00+08:00"},
                     {"state": "clear", "delivery_status": "confirmed", "quality_issues": [],
                      "generated_at": "2026-09-21T07:10:00+08:00"},
                     {"state": "unverified", "delivery_status": "unknown", "quality_issues": [], "generated_at": None},
                     {"state": "not_recorded", "delivery_status": "confirmed", "quality_issues": [], "generated_at": None}):
            data = self.before_generation_fixture(now)
            data["signal_gate_quality"]["sent_report"] = sent
            with self.subTest(sent=sent):
                result = self.render(data, now=now.isoformat())
                self.assert_current_issue(result)
                if sent and sent.get("state") == "issues":
                    self.assertEqual(result["elements"]["sent-quality-state"]["text"], "已发日报有质量问题")
        data = self.before_generation_fixture(now)
        data["reports"].append(self.fixture()["reports"][0])
        self.assert_current_issue(self.render(data, now=now.isoformat()))

    def assert_current_not_green(self, result):
        self.assertNotIn("quality-card--ok", result["elements"]["current-quality"]["className"])
        self.assertNotEqual(result["elements"]["current-quality-state"]["text"], "当前校验未发现问题")

    def test_sent_issues_and_current_recovery_are_both_visible(self):
        result = self.render(self.fixture())
        elements = result["elements"]
        self.assertEqual(elements["sent-quality-state"]["text"], "已发日报有质量问题")
        self.assertIn("nnG8 研究缺失", elements["sent-quality-issues"]["text"])
        self.assertEqual(elements["current-quality-state"]["text"], "当前校验未发现问题")
        self.assertIn("不表示已补发或研究完整", elements["current-quality-basis"]["text"])
        self.assertIn("Original morning report", elements["reader"]["text"])
        self.assertIn("最新留存报告", elements["sources"]["text"])

    def test_archive_selection_does_not_change_today_cards(self):
        result = self.render(self.fixture(), select_last=True, search="?source=signal_gate")
        self.assertIn("Older archived report", result["elements"]["reader"]["text"])
        self.assertEqual(result["elements"]["quality-date"]["text"], "2026-09-21（北京时间）")
        self.assertEqual(result["elements"]["sent-quality-state"]["text"], "已发日报有质量问题")
        self.assertEqual(result["elements"]["current-quality-state"]["text"], "当前校验未发现问题")

    def test_export_time_cannot_make_old_check_fresh(self):
        data = self.fixture()
        data["signal_gate_quality"]["current_inputs"]["checked_at"] = (self.NOW - timedelta(minutes=16)).isoformat()
        result = self.render(data)
        self.assertEqual(result["elements"]["current-quality-state"]["text"], "当前校验已过期")
        self.assert_current_not_green(result)
        self.assertIn("网页导出时间不会刷新校验时间", result["elements"]["current-quality-basis"]["text"])

    def test_browser_rechecks_age_without_fetch_or_new_export(self):
        result = self.render(self.fixture(), advance_ms=15 * 60 * 1000)
        self.assertEqual(result["elements"]["current-quality-state"]["text"], "当前校验已过期")
        self.assert_current_not_green(result)
        self.assertEqual(len(result["requests"]), 1)
        self.assertIn(30000, result["timers"])

    def test_missing_fields_bad_types_and_inconsistent_clear_fail_closed(self):
        cases = []
        for missing in ("checked_at", "report_date", "quality_issues", "state"):
            data = self.fixture()
            del data["signal_gate_quality"]["current_inputs"][missing]
            cases.append(data)
        for change in ({"checked_at": None}, {"checked_at": "2026-09-21T12:00:00"},
                       {"quality_issues": "not a list"}, {"state": "clear", "quality_issues": ["nng8:missing"]},
                       {"state": "issues", "quality_issues": []}, {"state": "unknown"}):
            data = self.fixture()
            data["signal_gate_quality"]["current_inputs"].update(change)
            cases.append(data)
        for quality in (None, {}, [], {"report_date": "2026-09-21"}):
            cases.append({**self.fixture(), "signal_gate_quality": quality})
        for index, data in enumerate(cases):
            with self.subTest(case=index):
                self.assert_current_not_green(self.render(data))

    def test_current_future_and_wrong_date_are_not_green(self):
        for change in ({"checked_at": (self.NOW + timedelta(seconds=61)).isoformat()},
                       {"report_date": "2026-09-20"}, {"report_date": "2026-09-22"},
                       {"checked_at": "2026-09-20T23:59:00+08:00"}, {"state": "stale"}):
            data = self.fixture()
            data["signal_gate_quality"]["current_inputs"].update(change)
            with self.subTest(change=change):
                self.assert_current_not_green(self.render(data))

    def test_beijing_midnight_invalidates_previous_day(self):
        now = datetime(2026, 9, 21, 15, 59, tzinfo=timezone.utc)
        data = self.fixture()
        data["exported_at"] = now.isoformat()
        data["signal_gate_quality"]["current_inputs"]["checked_at"] = now.isoformat()
        result = self.render(data, now=now.isoformat(), advance_ms=2 * 60 * 1000)
        self.assertEqual(result["elements"]["quality-date"]["text"], "2026-09-22（北京时间）")
        self.assert_current_not_green(result)
        self.assertNotIn("quality-card--ok", result["elements"]["sent-quality"]["className"])

    def test_fetch_failure_clears_prior_green_card(self):
        for options in ({"fail": True}, {"fail_second": True}, {"http_status": 503},
                        {"http_status": 401}, {"content_type": "text/html"}):
            with self.subTest(options=options):
                result = self.render(self.fixture(), **options)
                self.assert_current_not_green(result)
                self.assertEqual(result["elements"]["current-quality-state"]["text"], "当前校验状态未知")
                self.assertNotIn("quality-card--ok", result["elements"]["sent-quality"]["className"])

    def test_sent_success_needs_consistent_receipt_and_time(self):
        valid = {"state": "clear", "delivery_status": "confirmed", "quality_issues": [],
                 "generated_at": "2026-09-21T08:16:00+08:00"}
        data = self.fixture()
        data["signal_gate_quality"]["sent_report"] = valid
        self.assertEqual(self.render(data)["elements"]["sent-quality-state"]["text"], "已发回执未记录质量问题")
        for change in ({"delivery_status": "sent"}, {"state": "unverified"}, {"state": "not_recorded"},
                       {"generated_at": None}, {"quality_issues": ["nng8:missing"]}):
            data["signal_gate_quality"]["sent_report"] = {**valid, **change}
            with self.subTest(change=change):
                result = self.render(data)
                self.assertNotIn("quality-card--ok", result["elements"]["sent-quality"]["className"])

    def test_values_are_text_only_and_renderer_has_no_write_path(self):
        data = self.fixture()
        markup = '<img src=x onerror="evil()">'
        data["signal_gate_quality"]["sent_report"]["quality_issues"] = [markup]
        result = self.render(data)
        self.assertIn(markup, result["elements"]["sent-quality-issues"]["text"])
        self.assertNotIn("img", result["tags"])
        script = pages.REPORTS_PAGE.split("<script>", 1)[1].split("</script>", 1)[0]
        for forbidden in ("innerHTML", "outerHTML", "insertAdjacentHTML", "eval(", "document.write", "method:'POST'", "Authorization"):
            self.assertNotIn(forbidden, script)
        self.assertEqual(re.findall(r"fetch\('([^']+)'", script), ["./data.json"])
        self.assertEqual(result["requests"], [{"url": "./data.json", "credentials": "omit", "cache": "no-store"}])
        self.assertIn(".quality-grid{grid-template-columns:1fr", pages.REPORTS_PAGE)


if __name__ == "__main__":
    unittest.main()
