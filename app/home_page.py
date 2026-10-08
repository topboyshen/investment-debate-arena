"""Public navigation plus summaries from the existing redacted read-only feeds.

No source DB access, credential discovery or management routes are added.
"""

HOME_PAGE = r'''<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="color-scheme" content="light"><meta name="referrer" content="no-referrer">
<title>项目工作台 · Jie</title>
<link rel="icon" type="image/svg+xml" sizes="any" href="/favicon.svg?v=1">
<style>
:root{--paper:#f5f4ef;--card:#fffefa;--ink:#19312f;--muted:#657269;--line:#dce0d5;--green:#304f43;--orange:#b76043;--soft:#e9eddf}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;-webkit-font-smoothing:antialiased}a{color:inherit;text-decoration:none}button{font:inherit;cursor:pointer}a:focus-visible,button:focus-visible{outline:3px solid var(--orange);outline-offset:4px}.skip{position:absolute;left:20px;top:-80px;padding:12px;background:white;z-index:10}.skip:focus{top:12px}.wrap{max-width:1160px;margin:auto;padding:0 36px}.top{height:76px;display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid var(--line);gap:20px}.brand{display:flex;align-items:center;gap:11px;font-size:16px;font-weight:650}.mark{width:34px;height:34px;background:var(--green);color:var(--paper);display:grid;place-items:center;border-radius:9px;font-family:Georgia,serif;font-size:26px;font-weight:400}.nav{display:flex;align-items:center;gap:22px;font-size:12px;color:var(--muted)}.nav a:hover,.sub-links a:hover{text-decoration:underline;text-underline-offset:4px}.hero{display:flex;align-items:center;justify-content:space-between;gap:24px;padding:29px 0 24px}.eyebrow{font-size:10px;font-weight:600;letter-spacing:.15em;color:var(--orange)}h1{font-size:31px;line-height:1.35;font-weight:550;letter-spacing:-.025em;margin:9px 0}.intro{font-size:13px;line-height:1.8;color:var(--muted);margin:0}.refresh{padding:10px 13px;border:1px solid var(--line);border-radius:7px;background:var(--card);font-size:12px;color:var(--green);white-space:nowrap}.refresh:hover{background:var(--soft)}.refresh:disabled{opacity:.6;cursor:wait}.grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px}.card{min-width:0;border:1px solid var(--line);border-radius:11px;padding:23px 25px;background:var(--card);display:flex;flex-direction:column}.card.featured{background:#e9eddf;border-color:#d3ddc8}.card-head{display:flex;align-items:center;justify-content:space-between;gap:12px}.icon{width:33px;height:33px;display:grid;place-items:center;background:#f8f9f3;border:1px solid #d6ddcf;border-radius:9px;color:var(--green);font-size:17px}.access{font-size:10px;padding:5px 9px;border:1px solid #dce0d5;border-radius:30px;color:var(--muted);white-space:nowrap}.card h2{font-size:21px;font-weight:580;letter-spacing:-.02em;line-height:1.5;margin:13px 0 6px}.description{color:var(--muted);font-size:12px;line-height:1.85;margin:0 0 13px}.report-rows{margin:0 0 6px}.report-row{display:flex;justify-content:space-between;align-items:baseline;gap:12px;padding:7px 0;border-bottom:1px solid #d8dfcf;font-size:12px;line-height:1.7}.report-row dt{color:#54685a}.report-row dd{margin:0;text-align:right;font-variant-numeric:tabular-nums}.status{font-size:12px;line-height:1.8;margin:0 0 7px;color:#657269}.status.ok{color:#3e663e}.status.warning{color:#94602c}.status.unknown,.status.stale{color:#8a6535}.data-meta{font-size:10px;line-height:1.85;color:var(--muted);margin:0 0 8px;overflow-wrap:anywhere}.card-actions{margin-top:auto;padding-top:13px}.primary-link{min-height:44px;display:flex;justify-content:space-between;align-items:center;gap:14px;font-size:13px;font-weight:600;padding-top:12px;border-top:1px solid #dce1d5}.primary-link:hover{color:var(--orange)}.sub-links{display:flex;flex-wrap:wrap;gap:7px 18px;margin-top:10px;font-size:11px;color:var(--muted);line-height:1.8}.info-box{border:1px solid #e1e5db;border-radius:7px;padding:11px 13px;background:#f8f9f3;margin-bottom:10px}.info-box .status{font-size:14px;font-weight:550}.info-box .data-meta:last-child{margin:0}.boundary{border-top:1px solid var(--line);margin:25px 0 0;padding:18px 0;display:flex;gap:23px;align-items:baseline;font-size:11px;line-height:1.9;color:var(--muted)}.boundary strong{white-space:nowrap;font-weight:600;color:var(--ink)}.boundary p{margin:0}.footer{display:flex;justify-content:space-between;gap:20px;border-top:1px solid var(--line);padding:17px 0 24px;font-size:10px;line-height:1.8;color:var(--muted)}.scope-note{font-size:10px;line-height:1.8;color:var(--muted);margin:11px 0 0}.noscript{padding:14px;margin:0 0 16px;background:#faf0df;border:1px solid #e1cfae;border-radius:7px;font-size:12px;line-height:1.8}@media(max-width:680px){.wrap{padding:0 20px}.top{height:66px}.brand{font-size:14px;gap:8px}.nav{font-size:11px;gap:13px}.hero{padding:23px 0 20px;align-items:flex-start;gap:14px}h1{font-size:26px}.intro{font-size:12px}.refresh{font-size:11px;padding:9px 10px;margin-top:23px}.grid{grid-template-columns:1fr;gap:13px}.card{padding:20px}.card h2{font-size:20px;margin-top:12px}.boundary{display:block;margin-top:22px;padding:16px 0}.boundary p{margin-top:5px}.footer{font-size:9px;gap:15px}.footer span:last-child{text-align:right}.report-row{gap:7px}.nav a:last-child{display:none}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto!important}}
</style></head>
<body><a class="skip" href="#main">跳到主要内容</a><div class="wrap">
<header class="top"><a class="brand" href="/" aria-label="项目工作台首页"><span class="mark" aria-hidden="true">J</span>项目工作台</a><nav class="nav" aria-label="常用入口"><a href="/reports/">日报</a><a href="/ops/">系统状态</a><a href="/arena/">辩论场</a></nav></header>
<main id="main"><section class="hero"><div><div class="eyebrow">DEDIROCK · 日常工作台</div><h1>今天，从这里开始。</h1><p class="intro">读日报、找助手、看运行状态。常用项目，一处直达。</p></div><button class="refresh" id="refresh" type="button">刷新摘要 ↻</button></section>
<noscript><p class="noscript">未启用 JavaScript，动态摘要不可用。下方入口仍可打开；未读取的状态不代表正常。</p></noscript>
<section class="grid" aria-label="项目入口">
<article class="card featured" id="reports-card"><div class="card-head"><span class="icon" aria-hidden="true">▤</span><span class="access">公开阅读</span></div><h2>日报中心</h2><p class="description">先看最新留存，再按来源查阅原文与质量提示。</p>
<dl class="report-rows"><div class="report-row"><dt>海外市场晨报</dt><dd id="report-overseas">尚未读取</dd></div><div class="report-row"><dt>Signal Gate 日报</dt><dd id="report-signal_gate">尚未读取</dd></div></dl>
<p class="status" id="reports-status" role="status">正在读取留存日期…</p><p class="data-meta" id="reports-meta">报告日期 ≠ 快照时间；留存不代表已发送。</p>
<div class="card-actions"><a class="primary-link" href="/reports/">阅读最新日报 <span aria-hidden="true">↗</span></a><div class="sub-links"><a href="/reports/?source=overseas">海外晨报归档</a><a href="/reports/?source=signal_gate">Signal Gate 与今日质量</a></div></div></article>
<article class="card" id="assistant-card"><div class="card-head"><span class="icon" aria-hidden="true">✳</span><span class="access">Telegram 使用</span></div><h2>mini-hermes + pi</h2><p class="description">对话、研究与助手任务，继续在你的 Telegram 机器人中进行。</p>
<div class="info-box"><p class="status" id="assistant-status" role="status">服务状态尚未读取</p><p class="data-meta" id="assistant-meta">进程运行不等于消息收发成功。</p></div><p class="data-meta">仅跳转机器人；原有使用权限不变，网页不执行工具。</p>
<div class="card-actions"><a class="primary-link" href="https://t.me/lucyjie_clawdbot" target="_blank" rel="noopener noreferrer">在 Telegram 打开助手 <span aria-hidden="true">↗</span></a><div class="sub-links"><a href="/ops/">查看助手服务详情</a></div></div></article>
<article class="card" id="ops-card"><div class="card-head"><span class="icon" aria-hidden="true">⌘</span><span class="access">公开只读</span></div><h2>系统与网络状态</h2><p class="description">dedirock-infra 巡检、sing-box / MTG、主机资源与服务状态。</p>
<div class="info-box"><p class="status" id="ops-status" role="status">正在读取运行快照…</p><p class="data-meta" id="ops-count">仅统计已纳入监测的服务与巡检。</p><p class="data-meta" id="ops-reasons"></p><p class="data-meta" id="ops-meta">快照尚未读取；未知不等于正常。</p></div>
<div class="card-actions"><a class="primary-link" href="/ops/">查看详细数据与状态 <span aria-hidden="true">↗</span></a><div class="sub-links"><a href="/netdata/">Netdata 深度监控</a></div><p class="scope-note">Netdata 若显示欢迎页，可选择底部的匿名使用。</p></div></article>
<article class="card" id="arena-card"><div class="card-head"><span class="icon" aria-hidden="true">◈</span><span class="access">原型演示</span></div><h2>投研辩论场</h2><p class="description">围绕一个观点，查看多角色论证、反证与主审归纳。</p><div class="info-box"><p class="status">演示资料，不是实时投研结果</p><p class="data-meta">当前提供示例证据包；不读取真实持仓，不执行交易。</p></div>
<div class="card-actions"><a class="primary-link" href="/arena/">打开辩论场演示 <span aria-hidden="true">↗</span></a></div></article>
</section><p class="scope-note">数据来自现有只读快照，每分钟尝试更新。访问标签不代表健康状态；页面刷新不会触发日报、巡检或告警。</p>
<aside class="boundary"><strong>统一入口，各有边界</strong><p>当前收录 DediRock 本机项目。Netdata 监控也可免登录；订阅、审批、凭据与服务器管理不因入口合并而公开。nnG8 研究项目与完整研究附件尚未接入此站。</p></aside></main>
<footer class="footer"><span>JIE / PROJECT WORKSPACE</span><span>只读展示 · 不补发 · 不执行审批</span></footer></div>
<script>
'use strict';
const REQUIRED_SERVICES=['sing-box','mtg','cloudflared','nginx','netdata','fail2ban','ssh','mini-hermes','mini-hermes-pi','signal-gate','signal-gate-review','investment-debate-arena'];
const CHECK_AGES={runtime:1500,pi_requests:1500,subscriptions:2700,config_drift:2700,morning:97200};
const CHECK_NAMES={runtime:'业务健康',pi_requests:'pi 请求',subscriptions:'订阅健康',config_drift:'配置一致性',morning:'海外晨报'};
function record(value){return value!==null&&typeof value==='object'&&!Array.isArray(value);}
function stamp(value){if(typeof value!=='string'||value.length>64)return null;const match=/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.exec(value);if(!match||Number(match[2])>23||Number(match[3])>59||Number(match[4])>59)return null;const day=Date.parse(match[1]+'T00:00:00Z');if(!Number.isFinite(day)||new Date(day).toISOString().slice(0,10)!==match[1])return null;const n=Date.parse(value);return Number.isFinite(n)?n:null;}
function freshness(value,now,maxAge){const n=stamp(value);return n===null||n>now+60000?'unknown':now-n>maxAge*1000?'stale':'fresh';}
function validDate(value,now){if(typeof value!=='string'||!/^\d{4}-\d{2}-\d{2}$/.test(value))return false;const n=Date.parse(value+'T00:00:00Z');return Number.isFinite(n)&&new Date(n).toISOString().slice(0,10)===value&&value<=new Date(now+8*3600000).toISOString().slice(0,10);}
function indexed(rows,allowed){if(!Array.isArray(rows)||rows.length>100)return null;const values={};for(const row of rows){if(!record(row)||typeof row.id!=='string')return null;if(!allowed.includes(row.id))continue;if(Object.hasOwn(values,row.id))return null;values[row.id]=row;}return values;}
function summarizeReports(payload,now=Date.now()){
 const result={state:'unknown',updatedAt:null,items:{overseas:{date:null,state:'unknown'},signal_gate:{date:null,state:'unknown'}}};
 if(!record(payload)||payload.schema_version!==1)return result;
 const rows=indexed(payload.sources,['overseas','signal_gate']);if(!rows)return result;
 result.updatedAt=payload.exported_at;const age=freshness(payload.exported_at,now,1800);if(age==='unknown')return result;
 for(const id of ['overseas','signal_gate']){const row=rows[id];if(row&&['ok','partial','unavailable'].includes(row.state)){result.items[id]={date:validDate(row.latest_report_date,now)?row.latest_report_date:null,state:row.state};}}
 result.state=age==='stale'?'stale':Object.values(result.items).every(row=>row.date&&row.state==='ok')?'ready':Object.values(result.items).some(row=>row.state==='partial')?'partial':'unknown';return result;
}
function summarizeOps(payload,now=Date.now()){
 const result={state:'unknown',updatedAt:null,active:0,total:REQUIRED_SERVICES.length,serviceIssues:0,checkIssues:0,unknown:0,assistant:'unknown',reasons:[]};
 if(!record(payload)||payload.schema_version!==1)return result;
 const services=indexed(payload.services,REQUIRED_SERVICES),checks=indexed(payload.checks,Object.keys(CHECK_AGES));if(!services||!checks)return result;
 result.updatedAt=payload.exported_at;const age=freshness(payload.exported_at,now,180);if(age==='unknown')return result;
 for(const id of REQUIRED_SERVICES){const row=services[id];if(!row||!['active','inactive','failed','activating','deactivating','reloading'].includes(row.active_state)){result.unknown++;continue;}if(row.active_state==='active'&&row.sub_state==='running')result.active++;else if(['dead','failed','exited','start','stop','auto-restart','reload'].includes(row.sub_state))result.serviceIssues++;else result.unknown++;}
 for(const id of Object.keys(CHECK_AGES)){
  const row=checks[id],label=CHECK_NAMES[id];
  if(!row||!Array.isArray(row.issues)||row.issues.some(x=>typeof x!=='string')||!['ok','warning','error','unknown','stale'].includes(row.status)||freshness(row.checked_at,now,CHECK_AGES[id])!=='fresh'){
   result.unknown++;result.reasons.push(label+'：检查结果待核验');continue;
  }
  if(id==='pi_requests'&&row.status==='ok'&&(row.sample_status!=='recent_success'||!Number.isInteger(row.sample_window_seconds)||row.sample_window_seconds<=0||row.sample_window_seconds>7*86400||freshness(row.last_success_at,now,row.sample_window_seconds)!=='fresh')){
   result.unknown++;result.reasons.push(label+'：近期请求成功未验证');continue;
  }
  if(row.status==='unknown'||row.status==='stale')result.unknown++;
  else if(row.status!=='ok'||row.issues.length)result.checkIssues++;
  if(row.status!=='ok'||row.issues.length){
   const detail=row.issues[0];
   result.reasons.push(label+'：'+(typeof detail==='string'&&detail.length<=240&&!/[<>\u0000-\u001f]/.test(detail)?detail:'检查结果待核验，请查看详情'));
  }
 }
 result.state=age==='stale'?'stale':result.serviceIssues||result.checkIssues?'warning':result.unknown?'unknown':'ok';
 const bots=['mini-hermes','mini-hermes-pi'].map(id=>services[id]);result.assistant=age!=='fresh'?age:bots.some(row=>!row||row.active_state==='unknown'||!['active','inactive','failed','activating','deactivating','reloading'].includes(row.active_state))?'unknown':bots.every(row=>row.active_state==='active'&&row.sub_state==='running')?'ok':bots.some(row=>['inactive','failed','activating','deactivating','reloading'].includes(row.active_state))?'warning':'unknown';return result;
}
function clock(value){const n=stamp(value);return n===null?'时间未提供':new Date(n).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:false})+'（北京）';}
if(typeof document!=='undefined'){
 const el=id=>document.getElementById(id);const data={reports:null,ops:null};const failed={reports:false,ops:false};let loading=false;
 function status(id,text,tone){el(id).textContent=text;el(id).className='status '+tone;}
 function paint(){
  const reports=summarizeReports(data.reports),ops=summarizeOps(data.ops);
  for(const id of ['overseas','signal_gate']){const row=reports.items[id];el('report-'+id).textContent=row.date?'最新留存 '+row.date:'留存日期未知';}
  const reportTone=failed.reports?'unknown':reports.state;
  status('reports-status',failed.reports?'本次读取失败；不可视为最新状态':({ready:'留存日期已更新 · 不代表已发送',partial:'来源有质量提示，请查看日报详情',stale:'历史快照 · 已超过 30 分钟未更新',unknown:'来源信息不完整，不能确认最新日期'})[reports.state],reportTone);
  el('reports-meta').textContent='快照 '+clock(reports.updatedAt)+' · 日期指最新留存，不保证当日有新报告。';
  const opsTone=failed.ops?'unknown':ops.state;
  status('ops-status',failed.ops?'状态读取失败':({ok:'已监测服务与巡检未见异常',warning:'有运行或巡检事项需关注',unknown:'状态未完整确认',stale:'历史快照 · 已超过 3 分钟未更新'})[ops.state],opsTone);
  el('ops-count').textContent=ops.updatedAt?ops.active+' / '+ops.total+' 项已监测服务运行 · '+ops.serviceIssues+' 项服务异常 · '+ops.checkIssues+' 项巡检需关注'+(ops.unknown?' · '+ops.unknown+' 项状态未知':''):'没有用零异常代替缺失数据。';
  el('ops-reasons').textContent=failed.ops?'':ops.reasons.slice(0,3).join('；');
  el('ops-meta').textContent='快照 '+clock(ops.updatedAt)+' · 不等于整机全部服务或业务成功。';
  const assistant=failed.ops?'unknown':ops.assistant;
  status('assistant-status',({ok:'Bot 与 pi 进程运行中',warning:'助手服务需关注',unknown:'助手状态尚未确认',stale:'助手状态已过期'})[assistant],assistant);
  el('assistant-meta').textContent='采集 '+clock(ops.updatedAt)+' · 进程状态不证明消息收发或模型可用。';
 }
 async function fetchFeed(name,url){const controller=new AbortController(),timer=setTimeout(()=>controller.abort(),10000);try{const response=await fetch(url,{credentials:'omit',cache:'no-store',headers:{Accept:'application/json'},signal:controller.signal});if(!response.ok||!(response.headers.get('Content-Type')||'').includes('application/json'))throw new Error('invalid response');const value=await response.json();if(!record(value)||value.schema_version!==1)throw new Error('invalid snapshot');data[name]=value;failed[name]=false;}catch(_){failed[name]=true;}finally{clearTimeout(timer);paint();}}
 async function load(){if(loading)return;loading=true;el('refresh').disabled=true;await Promise.all([fetchFeed('reports','/reports/data.json'),fetchFeed('ops','/ops/data.json')]);loading=false;el('refresh').disabled=false;}
 el('refresh').addEventListener('click',load);paint();load();setInterval(load,60000);setInterval(paint,15000);
}
</script></body></html>'''
