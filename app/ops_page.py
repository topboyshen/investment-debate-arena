"""Public, read-only operations UI. The server never loads operations data.

The snapshot endpoint is served separately by nginx. All snapshot values are
rendered as text, and missing, stale or malformed observations stay explicit.
"""

OPS_PAGE = r'''<!doctype html>
<html lang="zh-CN"><head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><meta name="referrer" content="no-referrer">
<title>运维与网络服务 · 项目工作台</title>
<link rel="icon" type="image/svg+xml" sizes="any" href="/favicon.svg?v=1">
<style>
:root{--paper:#f5f4ef;--card:#fffefa;--ink:#19312f;--muted:#68736b;--line:#dcdfd5;--green:#304f43;--orange:#c1694c;--soft:#e8ecdf;--warn:#8b5a2a;--bad:#963c32}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}a{color:inherit;text-decoration:none}button{font:inherit;cursor:pointer}a:focus-visible,button:focus-visible,summary:focus-visible,.table-wrap:focus-visible{outline:3px solid var(--orange);outline-offset:4px}.wrap{max-width:1240px;margin:auto;padding:0 38px}.skip{position:absolute;top:-80px;left:20px;background:white;padding:12px;z-index:5}.skip:focus{top:12px}.top{height:88px;display:flex;align-items:center;justify-content:space-between;gap:16px;border-bottom:1px solid var(--line)}.brand{display:flex;align-items:center;gap:11px;font-size:15px;font-weight:650}.mark{background:var(--green);color:var(--paper);border-radius:9px;width:33px;height:33px;display:grid;place-items:center;font-family:Georgia,serif;font-size:25px;font-weight:400}.back{font-size:12px;color:var(--muted)}.hero{padding:42px 0 26px;display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.eyebrow{font-size:10px;color:var(--orange);letter-spacing:.18em;font-weight:650}h1{font-size:36px;font-weight:550;line-height:1.3;letter-spacing:-.035em;margin:13px 0 12px}.hero p{font-size:13px;color:var(--muted);line-height:1.9;margin:0}.refresh{border:1px solid var(--line);border-radius:7px;padding:11px 15px;font-size:12px;background:var(--card);color:var(--green);white-space:nowrap}.refresh:hover{background:var(--soft)}.refresh:disabled{opacity:.6;cursor:wait}.sync{font-size:11px;color:var(--muted);line-height:1.8;margin:0 0 16px}.banner{padding:14px 17px;background:#fff2df;border:1px solid #e4cfb2;border-radius:8px;color:var(--warn);font-size:12px;line-height:1.8;margin-bottom:16px}.banner.error{color:var(--bad);background:#fff0e9;border-color:#e5c5b8}.summary{background:var(--soft);border:1px solid #d3dccb;border-radius:10px;padding:22px 25px;margin-bottom:18px;display:flex;align-items:center;justify-content:space-between;gap:20px}.summary-title{font-size:19px;font-weight:550;line-height:1.5;margin:0 0 7px}.summary-copy{font-size:12px;color:var(--muted);line-height:1.8;margin:0}.summary .badge{flex-shrink:0}.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:13px;margin-bottom:32px}.metric{border:1px solid var(--line);border-radius:9px;background:var(--card);padding:19px 20px}.metric-label{font-size:12px;color:var(--muted)}.metric-value{font-size:29px;letter-spacing:-.025em;font-weight:550;margin:11px 0 10px;font-variant-numeric:tabular-nums}.metric-detail{font-size:11px;color:var(--muted);line-height:1.8;min-height:40px}.meter{height:4px;background:#e7e9df;border-radius:4px;margin:15px 0 0;overflow:hidden}.meter-fill{height:100%;background:#668164}.section{margin-bottom:30px}.section-heading{display:flex;align-items:baseline;justify-content:space-between;gap:18px;margin-bottom:14px}.section-heading h2{font-size:18px;font-weight:600;margin:0;letter-spacing:-.01em}.section-heading p{font-size:11px;line-height:1.7;color:var(--muted);margin:0}.panel{border:1px solid var(--line);border-radius:10px;background:var(--card);overflow:hidden}.table-wrap{overflow-x:auto}table{border-collapse:collapse;width:100%;text-align:left;font-size:12px}th{font-size:10px;color:var(--muted);font-weight:550;white-space:nowrap;background:#fafbf5}th,td{padding:15px 18px;border-bottom:1px solid #e6e8df;vertical-align:top}tbody tr:last-child td{border-bottom:0}td{font-variant-numeric:tabular-nums;line-height:1.7}.services-table{min-width:1010px}.cell-title{font-size:12px;font-weight:550;white-space:nowrap}.cell-note{color:var(--muted);font-size:10px;line-height:1.8;overflow-wrap:anywhere;max-width:235px}.badge{display:inline-flex;align-items:center;gap:6px;padding:5px 9px;border-radius:30px;border:1px solid #d9dfd4;color:#637164;font-size:10px;white-space:nowrap;background:#f0f2ea}.badge:before{content:"";height:5px;width:5px;border-radius:50%;background:currentColor}.badge.ok{background:#e8efdf;color:#44663b;border-color:#d7e0ca}.badge.warning,.badge.stale{background:#fbefdf;color:var(--warn);border-color:#e7d8bd}.badge.error{background:#fbebe4;color:var(--bad);border-color:#eccdc2}.panel-note{font-size:11px;line-height:1.85;color:var(--muted);padding:15px 18px;border-top:1px solid var(--line);background:#fafbf5}.network-top{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:14px;margin-bottom:14px}.traffic{padding:21px 24px}.traffic-label{font-size:12px;color:var(--muted);display:flex;justify-content:space-between;gap:10px}.traffic-value{font-size:31px;font-weight:550;letter-spacing:-.025em;margin:12px 0;font-variant-numeric:tabular-nums}.traffic-total{font-size:11px;color:var(--muted);line-height:1.8}.split{display:grid;grid-template-columns:1fr 1fr;gap:14px}.subheading{font-size:13px;font-weight:550;padding:18px 19px;margin:0;border-bottom:1px solid var(--line)}.rows{padding:0 19px}.detail-row{padding:15px 0;border-bottom:1px solid #e6e8df;display:flex;justify-content:space-between;gap:15px;align-items:flex-start}.detail-row:last-child{border:0}.detail-title{font-size:12px;font-weight:550;line-height:1.7;margin:0 0 5px}.detail-text{font-size:11px;line-height:1.85;color:var(--muted);margin:0;overflow-wrap:anywhere}.checks{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:13px}.check{padding:19px 20px}.check-head{display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:12px}.check-head h3{font-size:13px;font-weight:550;margin:0}.check-time{font-size:10px;color:var(--muted);line-height:1.8}.check ul{font-size:11px;line-height:1.85;padding-left:18px;color:var(--warn);margin:11px 0 0}.empty{padding:23px 20px;color:var(--muted);font-size:12px;line-height:1.9}.source{padding:19px 22px;background:#eeefe6;border:1px solid var(--line);border-radius:9px;margin:34px 0}.source summary{font-size:12px;font-weight:550;cursor:pointer}.source p{font-size:11px;color:var(--muted);line-height:1.95;margin:13px 0 0}.source a{text-decoration:underline;text-underline-offset:3px}.footer{display:flex;justify-content:space-between;gap:20px;font-size:10px;color:var(--muted);padding:0 0 29px;line-height:1.8}[hidden]{display:none!important}@media(max-width:940px){.wrap{padding:0 25px}.metrics{grid-template-columns:repeat(2,minmax(0,1fr))}.checks{grid-template-columns:repeat(2,minmax(0,1fr))}.split{grid-template-columns:1fr}.section-heading{align-items:flex-start}.section-heading p{max-width:55%;text-align:right}}@media(max-width:580px){.wrap{padding:0 20px}.top{height:74px}.brand{font-size:14px}.back{font-size:10px}.hero{padding:31px 0 21px;align-items:flex-start;gap:10px}h1{font-size:28px;margin:12px 0}.hero p{font-size:12px}.refresh{padding:9px 10px;font-size:11px;margin-top:29px}.summary{padding:18px;align-items:flex-start;gap:12px}.summary-title{font-size:17px}.summary-copy{font-size:11px}.summary .badge{font-size:9px}.metrics{gap:10px;margin-bottom:27px}.metric{padding:16px}.metric-value{font-size:25px}.metric-detail{font-size:10px}.section-heading{display:block}.section-heading h2{font-size:17px}.section-heading p{max-width:none;text-align:left;margin-top:7px}.checks{grid-template-columns:1fr}.network-top{gap:10px}.traffic{padding:17px 16px}.traffic-value{font-size:25px}.traffic-label{font-size:11px}.traffic-total{font-size:10px}.source{padding:18px}.footer{font-size:9px}.footer span{max-width:52%}.footer span:last-child{text-align:right}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style></head>
<body><a class="skip" href="#main">跳到运行状态</a><div class="wrap">
<header class="top"><a class="brand" href="/"><span class="mark" aria-hidden="true">J</span>项目工作台</a><a class="back" href="/">← 返回全部项目</a></header>
<main id="main"><section class="hero"><div><div class="eyebrow">OPERATIONS · 公开只读</div><h1>运维与网络服务</h1><p>查看服务是否在运行、资源用了多少，以及最近的巡检结果。<br>不提供订阅、原始日志或管理操作。</p></div><button class="refresh" id="refresh" type="button">刷新状态 ↻</button></section>
<div class="sync" id="sync" role="status" aria-live="polite">正在读取服务器快照…</div><div class="banner" id="banner" role="status" hidden></div>
<section class="summary" aria-label="运行概览"><div><h2 class="summary-title" id="summary-title">等待真实数据</h2><p class="summary-copy" id="summary-copy">尚未读到服务器快照；不将未知状态当作正常。</p></div><span class="badge" id="summary-badge">未采集</span></section>
<section class="metrics" id="metrics" aria-label="主机资源"><div class="empty">资源数据尚未采集。</div></section>
<section class="section" aria-labelledby="services-title"><div class="section-heading"><h2 id="services-title">服务明细</h2><p>运行状态来自系统；不等于用户侧连通或业务成功。</p></div><div class="panel"><div class="table-wrap" tabindex="0" role="region" aria-label="服务明细，可横向滚动"><table class="services-table"><thead><tr><th scope="col">服务</th><th scope="col">状态</th><th scope="col">当前内存 / 峰值</th><th scope="col">内存上限</th><th scope="col">已运行</th><th scope="col">累计 CPU 时间</th><th scope="col">任务数</th><th scope="col">自动重启</th></tr></thead><tbody id="services"><tr><td colspan="8">服务数据尚未采集。</td></tr></tbody></table></div><div class="panel-note">内存上限不是实际占用；峰值依赖当前 cgroup 的统计窗口。已运行从当前启动时间计算；自动重启为 systemd 的自动恢复计数，不包含所有手动重启，也不是历史总数。累计 CPU 时间是系统当前记账窗口的用时，不是实时 CPU 使用率。</div></div></section>
<section class="section" aria-labelledby="network-title"><div class="section-heading"><h2 id="network-title">网络与订阅检查</h2><p>主机流量与节点套餐计费流量不是同一口径。</p></div><div class="network-top" id="traffic"><div class="panel empty">网络流量尚未采集。</div></div><div class="split"><div class="panel"><h3 class="subheading">服务监听</h3><div class="rows" id="listeners"><div class="empty">监听数据尚未采集。</div></div><div class="panel-note">仅显示服务端口与监听范围，不展示地址。正在监听不代表家庭网络可直连。</div></div><div class="panel"><h3 class="subheading">订阅可用性</h3><div class="rows" id="subscriptions"><div class="empty">订阅检查尚未采集。</div></div><div class="panel-note">下载、格式与 TCP 入口检查分别显示。TCP 可达不等于代理认证成功，也不证明家庭线路可用；这里不提供订阅链接。</div></div></div></section>
<section class="section" aria-labelledby="mtg-title"><div class="section-heading"><h2 id="mtg-title">MTG 连接与流量</h2><p>当前连接来自 MTG；计数是本次进程累计，不是今日或套餐用量。</p></div><div class="panel"><div class="rows" id="mtg"><div class="empty">MTG 运行指标尚未采集。</div></div></div></section>
<section class="section" aria-labelledby="checks-title"><div class="section-heading"><h2 id="checks-title">运维巡检</h2><p>每项显示自己的检查时间；页面刷新不会重新执行巡检。</p></div><div class="checks" id="checks"><div class="panel empty">巡检结果尚未采集。</div></div></section>
<details class="source"><summary>这些数据代表什么？</summary><p>主机资源与服务状态由服务器定时导出，页面每 60 秒读取一次只读快照。CPU 与网络速率来自相邻两次采样，首次采样可能暂缺；时间统一显示为北京时间。超过 3 分钟的快照会明确标为过期。</p><p>内存已用 = 总量 − 可用量；磁盘统计服务器根文件系统；主机网络累计值来自采样网络接口，通常随接口重建或主机重启重置，不可用于推算订阅流量余额。巡检有独立周期，即使快照新鲜，巡检本身也可能过期。</p><p>这里只展示经筛选的运行指标；不会公开凭据、订阅地址、客户端 IP、原始日志或配置文件，也不能重启服务、修改设置或发出告警。更细的时序图可前往 <a href="/netdata/">Netdata 监控 ↗</a>。</p></details>
</main><footer class="footer"><span>JIE / OPERATIONS</span><span>真实快照 · 公开只读 · 未知不等于正常</span></footer></div>
<script>
'use strict';
(() => {
 const el = id => document.getElementById(id);
 const num = value => typeof value === 'number' && Number.isFinite(value) && value >= 0;
 const obj = value => value !== null && typeof value === 'object' && !Array.isArray(value);
 const text = (value, limit = 120) => typeof value === 'string' ? value.slice(0, limit) : '';
 const known = (mapping, value, fallback = '未采集') => Object.hasOwn(mapping, value) ? mapping[value] : fallback;
 const node = (tag, className, value) => {const n = document.createElement(tag); if (className) n.className = className; if (value !== undefined) n.textContent = value; return n;};
 const missing = '未采集';
 const formatNumber = value => num(value) ? value.toLocaleString('zh-CN', {maximumFractionDigits:1}) : missing;
 const bytes = value => {if (!num(value)) return missing; const units = ['B','KiB','MiB','GiB','TiB']; let i = 0; while (value >= 1024 && i < units.length - 1) {value /= 1024; i++;} return formatNumber(value) + ' ' + units[i];};
 const rate = value => num(value) ? bytes(value) + '/s' : missing;
 const duration = value => {if (!num(value)) return missing; const days = Math.floor(value / 86400), hours = Math.floor(value % 86400 / 3600), minutes = Math.floor(value % 3600 / 60); if (days) return days + ' 天 ' + hours + ' 小时'; if (hours) return hours + ' 小时 ' + minutes + ' 分'; return minutes + ' 分';};
 const stamp = value => {const date = Date.parse(value); return typeof value === 'string' && Number.isFinite(date) ? new Date(date).toLocaleString('zh-CN', {timeZone:'Asia/Shanghai',hour12:false}) : missing;};
 const percent = (part, total) => num(part) && num(total) && total > 0 && part <= total ? part / total * 100 : null;
 const pct = value => num(value) && value <= 100 ? value.toFixed(1) + '%' : missing;
 const statusNames = {ok:'正常',warning:'需关注',error:'异常',unknown:'未采集',stale:'数据过期'};
 const badge = (label, state = 'unknown') => node('span', 'badge ' + (Object.hasOwn(statusNames, state) ? state : 'unknown'), label);
 const statuses = {active:'运行中',inactive:'未运行',failed:'运行失败',activating:'启动中',deactivating:'停止中',reloading:'重载中'};
 const serviceLevel = s => s.active_state === 'active' ? 'ok' : s.active_state === 'failed' ? 'error' : Object.hasOwn(statuses, s.active_state) ? 'warning' : 'unknown';
 let snapshot = null, loading = false, fetchError = false;
 function validSnapshot(data) {
  if (!obj(data) || data.schema_version !== 1 || typeof data.exported_at !== 'string' || !Number.isFinite(Date.parse(data.exported_at)) || Date.parse(data.exported_at) > Date.now() + 60000) return false;
  if (!obj(data.host) || !Array.isArray(data.services) || data.services.length > 50 || !data.services.every(obj) || !Array.isArray(data.checks) || data.checks.length > 30 || !data.checks.every(obj)) return false;
  if (data.network !== undefined && !obj(data.network)) return false;
  if (data.network && data.network.mtg !== undefined && data.network.mtg !== null && !obj(data.network.mtg)) return false;
  if (data.checks.some(c => c.issues !== undefined && (!Array.isArray(c.issues) || c.issues.length > 50 || !c.issues.every(x => typeof x === 'string')))) return false;
  for (const key of ['listening_services','subscriptions']) {const list = data.network && data.network[key]; if (list !== undefined && (!Array.isArray(list) || list.length > 50 || !list.every(obj))) return false;}
  return true;
 }
 function freshness() {
  if (!snapshot) return;
  const age = (Date.now() - Date.parse(snapshot.exported_at)) / 1000;
  const stale = age > 180;
  el('sync').textContent = '快照时间 ' + stamp(snapshot.exported_at) + '（北京时间） · 每 60 秒自动刷新 · ' + (stale ? '已过期' : '距现在 ' + Math.max(0, Math.floor(age)) + ' 秒');
  const banner = el('banner');
  banner.hidden = !stale && !fetchError;
  banner.className = 'banner' + (fetchError ? ' error' : '');
  if (fetchError) banner.textContent = '本次读取失败或数据格式无效。以下保留上次快照，不代表当前状态；请稍后刷新。';
  else if (stale) banner.textContent = '快照已超过 3 分钟未更新。以下是历史状态，不能据此确认服务当前正常。';
  renderSummary(snapshot, stale || fetchError);
 }
 function renderSummary(data, uncertain) {
  const services = data.services, checks = data.checks;
  const active = services.filter(s => s.active_state === 'active').length;
  const inactive = services.filter(s => serviceLevel(s) === 'error' || serviceLevel(s) === 'warning').length;
  const attention = checks.filter(c => ['warning','error','stale'].includes(c.status)).length;
  const unknown = services.filter(s => serviceLevel(s) === 'unknown').length + checks.filter(c => !Object.hasOwn(statusNames,c.status) || c.status === 'unknown').length;
  const incomplete = !services.length || !checks.length || unknown > 0;
  let label = uncertain ? '历史快照' : inactive || attention ? '需要关注' : incomplete ? '状态未完整采集' : '服务与巡检未见异常';
  el('summary-title').textContent = label;
  el('summary-copy').textContent = (services.length ? active + ' / ' + services.length + ' 个已监测服务运行中' : '服务状态未采集') + ' · ' + (checks.length ? attention + ' 项巡检需关注' : '巡检结果未采集') + (unknown ? ' · ' + unknown + ' 项状态未知' : '') + '。分母仅为本页已监测服务，并非整机全部服务；详细指标可能缺测，不代表业务端到端验收。';
  el('summary-badge').textContent = uncertain ? '待刷新' : inactive || attention ? '需关注' : incomplete ? '待采集' : '服务 / 巡检正常';
  el('summary-badge').className = 'badge ' + (uncertain || inactive || attention ? 'warning' : incomplete ? 'unknown' : 'ok');
 }
 function metric(label, value, detail, fill) {const card=node('article','metric'); card.append(node('div','metric-label',label),node('div','metric-value',value),node('div','metric-detail',detail)); if (num(fill) && fill <= 100) {const meter=node('div','meter'), bar=node('div','meter-fill'); bar.style.width=fill.toFixed(2)+'%'; meter.append(bar); card.append(meter);} return card;}
 function renderHost(h) {
  const used = num(h.memory_total_bytes) && num(h.memory_available_bytes) && h.memory_available_bytes <= h.memory_total_bytes ? h.memory_total_bytes - h.memory_available_bytes : null;
  const swapUsed = num(h.swap_total_bytes) && num(h.swap_free_bytes) && h.swap_free_bytes <= h.swap_total_bytes ? h.swap_total_bytes - h.swap_free_bytes : null;
  const memoryPct=percent(used,h.memory_total_bytes), diskPct=percent(h.disk_used_bytes,h.disk_total_bytes);
  const load=Array.isArray(h.load) && h.load.length === 3 ? h.load.map(formatNumber).join(' / ') : missing;
  el('metrics').replaceChildren(
   metric('CPU 使用率',pct(h.cpu_percent),formatNumber(h.cpu_count)+' 核 · 负载 1 / 5 / 15 分钟：'+load,h.cpu_percent),
   metric('内存使用率',pct(memoryPct),'已用 '+bytes(used)+' / 总计 '+bytes(h.memory_total_bytes)+'；可用 '+bytes(h.memory_available_bytes),memoryPct),
   metric('磁盘使用率',pct(diskPct),'已用 '+bytes(h.disk_used_bytes)+' / 总计 '+bytes(h.disk_total_bytes)+'（根文件系统）',diskPct),
   metric('主机已运行',duration(h.uptime_seconds),'Swap 已用 '+bytes(swapUsed)+' / 总计 '+bytes(h.swap_total_bytes),null));
  const makeTraffic=(label,speed,total)=>{const card=node('article','panel traffic');card.append(node('div','traffic-label',label),node('div','traffic-value',rate(speed)),node('div','traffic-total','接口累计 '+bytes(total)+' · 非套餐用量'));return card;};
  el('traffic').replaceChildren(makeTraffic('↓ 主机接收',h.network_rx_bytes_per_second,h.network_rx_bytes),makeTraffic('↑ 主机发送',h.network_tx_bytes_per_second,h.network_tx_bytes));
 }
 function renderServices(list) {
  const parent=el('services');parent.replaceChildren();
  if (!list.length) {const row=node('tr'),cell=node('td','','服务状态未采集，不能据此判断服务正常。');cell.colSpan=8;row.append(cell);parent.append(row);return;}
  for (const service of list) {
   const row=node('tr'),name=node('td');name.append(node('div','cell-title',text(service.label)||text(service.id)||'未命名服务'),node('div','cell-note',text(service.id)));
   const status=node('td');status.append(badge(known(statuses,service.active_state),serviceLevel(service)),node('div','cell-note',text(service.sub_state)||missing));
   const memory=node('td');memory.append(node('div','',bytes(service.memory_bytes)),node('div','cell-note','峰值 '+bytes(service.memory_peak_bytes)));
   const limit=node('td','',service.memory_limit_unlimited === true ? '无上限' : bytes(service.memory_limit_bytes));
   if (typeof service.version==='string') name.append(node('div','cell-note','版本 '+text(service.version,60)));
   const up=node('td');up.append(node('div','',duration(service.uptime_seconds)),node('div','cell-note','启动 '+stamp(service.started_at)));
   row.append(name,status,memory,limit,up,node('td','',num(service.cpu_seconds)?formatNumber(service.cpu_seconds)+' 秒':missing),node('td','',formatNumber(service.tasks)),node('td','',formatNumber(service.restarts)));parent.append(row);
  }
 }
 function detailRow(label, description, status, level) {const row=node('div','detail-row'),copy=node('div');copy.append(node('div','detail-title',label),node('p','detail-text',description));row.append(copy,badge(status,level));return row;}
 function renderNetwork(network) {
  const listeners=el('listeners'),subscriptions=el('subscriptions');listeners.replaceChildren();subscriptions.replaceChildren();
  const ports=network.listening_services||[],subs=network.subscriptions||[];
  if (!ports.length) listeners.append(node('div','empty','监听数据未采集。'));
  for (const item of ports) {const scope=known({public:'全部 / 公网地址监听',loopback:'仅本机',private:'内网监听',unknown:'范围未采集'},item.scope);const port=Number.isInteger(item.port)&&item.port>0&&item.port<=65535?String(item.port):missing;listeners.append(detailRow(text(item.label)||text(item.id)||'服务',text(item.transport,8).toUpperCase()+' '+port+' · '+scope,known({listening:'正在监听',not_listening:'未监听',unknown:'未采集'},item.state),known({listening:'ok',not_listening:'warning'},item.state,'unknown')));}
  if (ports.length) listeners.append(node('p','detail-text','监听范围不等于防火墙已放行；公网路由和客户端线路未在此验证。'));
  if (!subs.length) subscriptions.append(node('div','empty','订阅检查未采集；没有记录不代表订阅可用。'));
  for (const item of subs) {
   const part={ok:'通过',error:'失败',unknown:'未采集'},nodes={reachable:'TCP 可达',unreachable:'TCP 不通',unverified:'未验证',unknown:'未采集'};
   const bad=item.overall==='error'||item.download==='error'||item.format==='error'||item.nodes==='unreachable';
   const good=item.download==='ok'&&item.format==='ok'&&item.nodes==='reachable';
   const row=detailRow(text(item.label)||text(item.id)||'订阅','下载 '+known(part,item.download)+' · 格式 '+known(part,item.format)+' · 节点 '+known(nodes,item.nodes),bad?'检查异常':good?'TCP 检查通过':'验证未完整',bad?'error':good?'ok':'unknown');
   const format=known({'sing-box-json':'sing-box JSON','base64-proxy-uri':'Base64 代理列表','clash-yaml':'Clash / mihomo YAML'},item.format_name);
   row.firstChild.append(node('p','detail-text','内容 '+format+' · 证书剩余 '+(num(item.certificate_days)?formatNumber(item.certificate_days)+' 天':missing)));
   row.firstChild.append(node('p','detail-text','可达 '+formatNumber(item.reachable)+' / 入口 '+formatNumber(item.endpoints)+' · '+(item.check==='tcp_only'?'仅 TCP 检查':'验证级别未采集')),node('p','detail-text','检查 '+stamp(item.checked_at)));subscriptions.append(row);
  }
  const mtg=el('mtg'),m=obj(network.mtg)?network.mtg:{};mtg.replaceChildren();
  for (const [label,value,detail] of [
   ['当前连接', '客户端 '+formatNumber(m.client_connections)+' · Telegram '+formatNumber(m.telegram_connections),'瞬时连接数，不等于独立用户数'],
   ['代理累计流量','发往客户端 '+bytes(m.traffic_to_client_bytes)+' · 来自客户端 '+bytes(m.traffic_from_client_bytes),'自本次 MTG 进程启动累计，不是计费数据'],
   ['保护机制计数','并发限制 '+formatNumber(m.concurrency_limited)+' · 重放拦截 '+formatNumber(m.replay_attacks)+' · 前置转发 '+formatNumber(m.domain_fronting),'累计触发计数，不推断来源或攻击者'],
   ['采集时间',stamp(m.collected_at),'北京时间 · 未采集不会显示为零']
  ]) {const row=node('div','detail-row'),labelNode=node('div','detail-title',label),copy=node('div');copy.append(node('p','detail-text',value),node('p','cell-note',detail));row.append(labelNode,copy);mtg.append(row);}
 }
 function renderChecks(list) {
  const parent=el('checks');parent.replaceChildren();
  if (!list.length) {parent.append(node('div','panel empty','运维巡检未采集，不能据此判断没有异常。'));return;}
  for (const check of list) {const card=node('article','panel check'),head=node('div','check-head');head.append(node('h3','',text(check.label)||text(check.id)||'巡检'),badge(known(statusNames,check.status),check.status));card.append(head,node('div','check-time','检查 '+stamp(check.checked_at)));if (num(check.source_interval_seconds)) card.append(node('div','check-time','计划每 '+duration(check.source_interval_seconds)+' 检查一次')); if ((check.issues||[]).length) {const ul=node('ul');for (const issue of check.issues) ul.append(node('li','',text(issue,240)));card.append(ul);}else card.append(node('p','detail-text',check.status==='ok'?'本次已采集范围内无问题。':'暂无可用的异常详情。'));parent.append(card);}
 }
 async function load() {
  if (loading) return;loading=true;el('refresh').disabled=true;
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
  try {const response=await fetch('/ops/data.json',{cache:'no-store',credentials:'omit',signal:controller.signal});if (!response.ok) throw new Error('snapshot unavailable');const data=await response.json();if (!validSnapshot(data)) throw new Error('invalid snapshot');snapshot=data;fetchError=false;renderHost(data.host);renderServices(data.services);renderNetwork(data.network||{});renderChecks(data.checks);freshness();}
  catch (_) {fetchError=true;if (snapshot) freshness();else {el('sync').textContent='尚无可用快照 · 每 60 秒重试';el('banner').hidden=false;el('banner').className='banner error';el('banner').textContent='暂时无法读取有效的服务器状态。没有用示例数据代替，请稍后刷新。';el('summary-title').textContent='状态暂时未知';el('summary-copy').textContent='读取失败或快照格式无效，不代表服务故障，也不能据此确认正常。';}}
  finally {clearTimeout(timeout);loading=false;el('refresh').disabled=false;}
 }
 el('refresh').addEventListener('click',load);
 setInterval(load,60000);setInterval(freshness,10000);load();
})();
</script></body></html>'''
