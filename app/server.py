from __future__ import annotations

import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

from debate import build_debate, normalize_input
from portal_pages import HOME_PAGE, REPORTS_PAGE
from ops_page import OPS_PAGE
from branding import FAVICON_SVG

MAX_BODY_BYTES = 4096
SECURITY_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; "
        "connect-src 'self'; img-src 'self'; base-uri 'none'; form-action 'self'; "
        "frame-ancestors 'none'"
    ),
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
}

PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>多角色投研辩论场 · Prototype</title>
  <link rel="icon" type="image/svg+xml" sizes="any" href="/favicon.svg?v=1" />
  <style>
    :root{--ink:#12233f;--muted:#61708a;--paper:#f6f4ee;--line:#d8dce4;--white:#fffdfa;--navy:#13294b;--gold:#d79e37;--coral:#db6d59;--teal:#2d827b;--violet:#7160b4;--shadow:0 18px 48px rgba(26,49,86,.10)}
    *{box-sizing:border-box} body{margin:0;background:var(--paper);color:var(--ink);font-family:Inter,"PingFang SC","Microsoft YaHei",Arial,sans-serif;line-height:1.55}
    .top{background:var(--navy);color:white;padding:30px max(24px,calc((100vw - 1160px)/2));display:flex;justify-content:space-between;gap:20px;align-items:flex-end}.eyebrow{font-size:12px;letter-spacing:.17em;text-transform:uppercase;color:#bcd2ee;font-weight:700}.top h1{font-size:clamp(30px,4vw,49px);line-height:1.05;margin:7px 0 0;letter-spacing:-.04em}.top p{margin:12px 0 0;color:#d7e4f3;max-width:660px}.mode{border:1px solid rgba(255,255,255,.34);color:#e5f0fc;border-radius:99px;padding:7px 12px;font-size:12px;white-space:nowrap}
    main{max-width:1160px;margin:0 auto;padding:30px 24px 76px}.notice{padding:14px 16px;border-left:4px solid var(--gold);background:#fff8e8;color:#604719;margin-bottom:22px;border-radius:4px}.grid{display:grid;grid-template-columns:340px 1fr;gap:22px;align-items:start}.panel{background:var(--white);border:1px solid var(--line);border-radius:14px;box-shadow:var(--shadow)}.controls{padding:21px;position:sticky;top:20px}.controls h2,.section-title{margin:0;color:var(--navy);letter-spacing:-.02em}.controls h2{font-size:21px}.controls p{color:var(--muted);font-size:14px;margin:8px 0 18px}label{font-size:12px;text-transform:uppercase;letter-spacing:.1em;font-weight:800;color:#53617a;display:block;margin:15px 0 7px}input,textarea{width:100%;border:1px solid #c6ced9;background:#fff;padding:11px 12px;border-radius:8px;font:inherit;color:var(--ink)}textarea{min-height:148px;resize:vertical}button{width:100%;background:var(--coral);color:white;border:0;border-radius:8px;padding:12px;font:inherit;font-weight:800;margin-top:16px;cursor:pointer;transition:.15s}button:hover{transform:translateY(-1px);background:#c55745}button:disabled{opacity:.6;cursor:wait}.micro{font-size:12px;color:var(--muted);margin-top:12px}.content{min-width:0}.hero-card{padding:22px 24px;margin-bottom:22px;background:linear-gradient(135deg,#fffdfa,#eef4f7);border-left:5px solid var(--teal)}.ticker{font-size:12px;letter-spacing:.15em;font-weight:800;color:var(--teal)}.thesis{font-size:20px;line-height:1.4;font-weight:650;margin:8px 0}.meta{font-size:12px;color:var(--muted)}.role-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.role{padding:18px}.role:last-child{grid-column:1/-1}.role-head{display:flex;justify-content:space-between;gap:12px;align-items:start;border-bottom:1px solid var(--line);padding-bottom:12px;margin-bottom:12px}.role h3{margin:0;font-size:18px;color:var(--navy)}.role .focus{margin:4px 0 0;color:var(--muted);font-size:13px}.count{font-size:11px;padding:4px 7px;background:#edf2f7;border-radius:99px;color:#526077;white-space:nowrap}.claim{padding:12px;margin-top:10px;border:1px solid var(--line);border-radius:9px;background:#fff}.badge{font-size:10px;letter-spacing:.09em;font-weight:900;padding:4px 6px;border-radius:4px;display:inline-block}.FACT{background:#e4f4f1;color:#146159}.INFERENCE{background:#eeeafb;color:#50408d}.SCENARIO{background:#fff1df;color:#a05b14}.claim p{margin:8px 0;color:#273956;font-size:14px}.cite{font-size:11px;color:var(--muted);margin-top:7px}.cite a{color:#286a91;text-decoration:none}.cite a:hover{text-decoration:underline}.chief{padding:23px;margin-top:22px;border-top:5px solid var(--gold)}.chief h2{margin:0 0 14px;font-size:23px;color:var(--navy)}.review-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.review{padding:14px;border-radius:9px;background:#f2f4f7}.review.wide{grid-column:1/-1}.review h4{font-size:12px;letter-spacing:.12em;text-transform:uppercase;margin:0 0 8px;color:#53617a}.review ul{margin:0;padding-left:19px;font-size:14px;color:#2b3d59}.sources{padding:21px;margin-top:22px}.sources h2{font-size:20px}.source{border-top:1px solid var(--line);padding:12px 0;font-size:14px}.source:first-of-type{border-top:0}.source a{color:#286a91;text-decoration:none;font-weight:700}.stamp{font-size:12px;color:var(--muted);margin-top:3px}.empty{padding:34px;text-align:center;color:var(--muted)}.footer{margin-top:28px;font-size:12px;color:#65728b;text-align:center}@media(max-width:860px){.top{display:block}.mode{display:inline-block;margin-top:18px}.grid{grid-template-columns:1fr}.controls{position:static}.role-grid{grid-template-columns:1fr}.role:last-child{grid-column:auto}.review-grid{grid-template-columns:1fr}.review.wide{grid-column:auto}}
  </style>
</head>
<body>
  <header class="top"><div><a href="/" style="color:#d7e4f3;text-decoration:none;font-size:14px">← 返回项目工作台</a><div class="eyebrow" style="margin-top:14px">Investment Research Debate Arena</div><h1>多角色投研辩论场</h1><p>把研究观点拆分为可审计的事实、推断与情景，再由多角色反证与主审归纳。</p></div><div class="mode">原型 · 演示资料库</div></header>
  <main>
    <div class="notice"><strong>研究边界：</strong> 本工具用于研究过程结构化。它不生成确定性交易指令；请自行核验来源、时点、口径与适用性。</div>
    <div class="grid">
      <aside class="panel controls"><h2>建立一场辩论</h2><p>输入代码和初始观点。AAPL 已加载演示资料；其他代码将保留结构并提示证据缺口。</p><label for="ticker">证券代码</label><input id="ticker" value="AAPL" maxlength="16" /><label for="thesis">初始投资观点</label><textarea id="thesis">近期收入、服务业务与现金流表现支持经营韧性，但需要检验竞争与产品周期风险。</textarea><button id="run">生成研究辩论</button><div class="micro">所有论点都标注为 FACT、INFERENCE 或 SCENARIO，并保留来源链接和时间戳。</div></aside>
      <section class="content" id="content"><div class="panel empty">正在加载演示研究材料…</div></section>
    </div>
    <div class="footer">研究与分析工具原型，不构成个性化财务建议。</div>
  </main>
<script>
const content=document.getElementById('content'), run=document.getElementById('run');
const esc=s=>String(s).replace(/[&<>'"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
const cite=c=>`<div class="cite">来源：<a href="${esc(c.source_url)}" target="_blank" rel="noopener noreferrer">${esc(c.source_name)}</a> · 发布 ${esc(c.published_at)} · 证据快照 ${esc(c.evidence_snapshot_date)}</div>`;
const claims=items=>items.map(i=>`<article class="claim"><span class="badge ${esc(i.classification)}">${esc(i.classification)}</span><p>${esc(i.claim)}</p>${i.citations.map(cite).join('')}</article>`).join('');
const list=(title,items,wide='')=>`<section class="review ${wide}"><h4>${title}</h4><ul>${items.map(x=>`<li>${esc(x)}</li>`).join('')}</ul></section>`;
function render(data){
 const roles=data.roles.map(r=>`<article class="panel role"><div class="role-head"><div><h3>${esc(r.role)}</h3><p class="focus">${esc(r.focus)}</p><p class="focus"><strong>本轮问题：</strong>${esc(r.research_question)}</p></div><span class="count">3 层论证</span></div>${claims(r.claims)}</article>`).join('');
 const review=data.chief_review;
 const sources=data.sources.map(s=>`<div class="source"><a href="${esc(s.source_url)}" target="_blank" rel="noopener noreferrer">${esc(s.source_name)}</a><div class="stamp">发布：${esc(s.published_at)} · 证据快照：${esc(s.evidence_snapshot_date)}</div></div>`).join('');
  const coverage=data.coverage_notice?`<div class="notice"><strong>覆盖说明：</strong>${esc(data.coverage_notice)}</div>`:'';
  content.innerHTML=`<section class="panel hero-card"><div class="ticker">${esc(data.ticker)} · ${esc(data.coverage_status)}</div><div class="thesis">“${esc(data.user_thesis)}”</div><div class="meta">生成时间：${esc(data.generated_at)} · ${esc(data.research_notice)}</div></section>${coverage}<h2 class="section-title">角色论证</h2><div class="role-grid" style="margin-top:14px">${roles}</div><section class="panel chief"><h2>主审结论</h2><div class="review-grid">${list('共识',review.consensus)}${list('分歧',review.disagreements)}${list('关键证据',review.key_evidence)}${list('待验证问题',review.questions)}${list('逻辑失效条件',review.failure_conditions,'wide')}</div></section><section class="panel sources"><h2>来源与时间戳</h2>${sources||'<div class="source">尚无可核验的发行人资料。</div>'}</section>`;
}
async function load(){run.disabled=true;run.textContent='构建论证中…';try{const res=await fetch('/arena/api/debate',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({ticker:document.getElementById('ticker').value,thesis:document.getElementById('thesis').value})});const data=await res.json();if(!res.ok)throw new Error(data.error||'请求失败');render(data)}catch(e){content.innerHTML=`<div class="panel empty">无法生成辩论：${esc(e.message)}</div>`}finally{run.disabled=false;run.textContent='生成研究辩论'}}
run.addEventListener('click',load);load();
</script>
</body></html>'''


class Handler(BaseHTTPRequestHandler):
    server_version = "InvestmentDebateArena"
    sys_version = ""

    def version_string(self) -> str:
        return self.server_version

    def setup(self) -> None:
        super().setup()
        self.connection.settimeout(10)

    def _security_headers(self) -> None:
        for name, value in SECURITY_HEADERS.items():
            self.send_header(name, value)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/favicon.svg":
            self._favicon()
            return
        if path == "/healthz":
            self._json(HTTPStatus.OK, {"status": "ok", "service": "investment-debate-arena"})
            return
        if path == "/readyz":
            demo = build_debate("AAPL", "检查演示证据包和输出结构是否可用。")
            ready = len(demo["sources"]) == 2 and len(demo["roles"]) == 5
            self._json(
                HTTPStatus.OK if ready else HTTPStatus.SERVICE_UNAVAILABLE,
                {"status": "ready" if ready else "not_ready", "service": "investment-debate-arena"},
            )
            return
        if path in {"/api/demo", "/arena/api/demo"}:
            self._json(HTTPStatus.OK, build_debate("AAPL", "近期收入、服务业务与现金流表现支持经营韧性，但需要检验竞争与产品周期风险。"))
            return
        if path in {"/arena", "/reports", "/ops"}:
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", path + "/")
            self.send_header("Content-Length", "0")
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            return
        if path in {"/", "/arena/", "/reports/", "/ops/"}:
            # The report page is a data-free shell. Only nginx can serve the
            # read-only snapshot; this process never opens source reports/DBs.
            body = {"/": HOME_PAGE, "/arena/": PAGE, "/reports/": REPORTS_PAGE, "/ops/": OPS_PAGE}[path].encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self._security_headers()
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if urlparse(self.path).path not in {"/api/debate", "/arena/api/debate"}:
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            content_type = self.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
            if content_type != "application/json":
                self._json(HTTPStatus.UNSUPPORTED_MEDIA_TYPE, {"error": "content type must be application/json"})
                return
            raw_size = self.headers.get("Content-Length")
            if raw_size is None:
                self._json(HTTPStatus.LENGTH_REQUIRED, {"error": "content length is required"})
                return
            size = int(raw_size)
            if size < 0:
                raise ValueError("content length must not be negative")
            if size > MAX_BODY_BYTES:
                self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"error": "request too large"})
                return
            data = json.loads(self.rfile.read(size).decode("utf-8"))
            if type(data) is not dict:
                raise ValueError("JSON body must be an object")
            if set(data) != {"ticker", "thesis"}:
                raise ValueError("JSON body must contain exactly ticker and thesis")
            ticker, thesis = normalize_input(data["ticker"], data["thesis"])
            self._json(HTTPStatus.OK, build_debate(ticker, thesis))
        except (UnicodeDecodeError, json.JSONDecodeError):
            self._json(HTTPStatus.BAD_REQUEST, {"error": "malformed JSON body"})
        except TimeoutError:
            self._json(HTTPStatus.REQUEST_TIMEOUT, {"error": "request timed out"})
        except (TypeError, ValueError) as exc:
            self._json(HTTPStatus.UNPROCESSABLE_ENTITY, {"error": str(exc)})

    def _favicon(self, *, head_only: bool = False) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "image/svg+xml")
        self.send_header("Content-Length", str(len(FAVICON_SVG)))
        self.send_header("Cache-Control", "public, max-age=3600")
        self._security_headers()
        self.end_headers()
        if not head_only:
            self.wfile.write(FAVICON_SVG)

    def do_HEAD(self) -> None:
        path = urlparse(self.path).path
        if path == "/favicon.svg":
            self._favicon(head_only=True)
            return
        if path == "/ops":
            self.send_response(HTTPStatus.PERMANENT_REDIRECT)
            self.send_header("Location", "/ops/")
        elif path not in {"/", "/arena/", "/reports/", "/ops/", "/healthz", "/readyz"}:
            self.send_response(HTTPStatus.NOT_FOUND)
        else:
            self.send_response(HTTPStatus.OK)
        page = {"/": HOME_PAGE, "/arena/": PAGE, "/reports/": REPORTS_PAGE, "/ops/": OPS_PAGE}.get(path)
        if page is not None:
            self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(page.encode("utf-8"))) if page is not None else "0")
        self.send_header("Cache-Control", "no-store")
        self._security_headers()
        self.end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Allow", "GET, HEAD, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self._security_headers()
        self.end_headers()

    def log_message(self, fmt: str, *args: object) -> None:
        print("%s - %s" % (self.address_string(), fmt % args), flush=True)


if __name__ == "__main__":
    server = ThreadingHTTPServer(("127.0.0.1", 18766), Handler)
    server.daemon_threads = True
    server.timeout = 10
    print("investment-debate-arena listening on 127.0.0.1:18766", flush=True)
    server.serve_forever()
