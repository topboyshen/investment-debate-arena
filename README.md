# DediRock 项目工作台与投研辩论场

## 概览

首页是中文项目入口，日报中心只读展示已经存在的报告；各项目、进程和安全边界不合并。辩论场位于 `/arena/`，将证券代码与研究观点转成五个角色的结构化论证，并由主审给出共识、分歧、关键证据、待验证问题与逻辑失效条件。已覆盖发行人的内容按 **FACT / INFERENCE / SCENARIO** 分层；未覆盖代码使用 **COVERAGE_NOTICE / INFERENCE / SCENARIO**，不会把内部覆盖状态伪装成外部事实。演示事实保留来源 URL、发布日期与证据快照日期。

系统仅用于研究流程组织，**不构成个性化财务建议，不提供确定性交易指令**。

## 隔离部署
**依赖**：纯 Python 标准库实现，无新增外部依赖。

| 项目 | 配置 |
|---|---|
| 项目目录 | `/opt/investment-debate-arena` |
| 专用账户 | `debatearena` |
| 专用环境 | `/opt/investment-debate-arena/.venv` |
| 后端监听 | `127.0.0.1:18766` |
| 公网入口 | Cloudflare HTTPS → nginx `127.0.0.1:18765`（限流、并发和超时保护） |
| systemd 单元 | `investment-debate-arena.service` |
| 健康检查 | `GET /healthz` |
| 就绪检查 | `GET /readyz` |

该原型不读取、不修改 Mini Hermes 的代码、配置、端口或 systemd 单元。

### 访问方式

按所有者要求，2026-09-21 上线第一期：

| 路径 | 用途 | 访问 |
|---|---|---|
| `/` | 项目工作台，常用入口与既有公开快照的日期/状态摘要；不展示正文或管理操作 | 公开只读 |
| `/arena/` | 投研辩论场原型 | 公开、限流 |
| `/arena/api/demo`、`/arena/api/debate` | 原有静态演示接口 | 公开、限流 |
| `/api/demo`、`/api/debate` | 兼容原有客户端与检查 | 公开、限流 |
| `/reports/` | 日报中心 | 按所有者要求公开阅读、无需登录 |
| `/reports/data.json` | 唯一报告数据入口 | 公开只读、禁止缓存 |
| `/netdata/` | Netdata 监控 | 按所有者要求公开只读；控制与配置接口不开放 |
| `/ops/`、`/ops/data.json` | 运维与网络服务明细、白名单指标快照 | 公开只读、禁止缓存 |

任何知道网址的人均可读取当前与历史留存日报；`noindex` 仅建议搜索引擎不收录，不是访问控制。

私有订阅入口不变，不在工作台展示。网页没有 pi 执行、聊天、审批、重发日报、管理服务或读取任意文件的权限。
nginx 与应用仍仅监听回环地址，公网访问经 Cloudflare Tunnel，未新增防火墙放行。

Netdata 公网监控会公开主机资源、运行指标及仪表盘提供的相关信息。仅在此域名的 `/netdata/` 移除登录要求，保留限流和禁止缓存；配置下载、管理与函数执行入口不开放。原有回环 `19998` SSH 隧道入口与凭据文件不变。

Netdata 自带的云账号登录是可选项。首次看到欢迎页时，选择 `Skip and use the dashboard anonymously` 即可查看图表，不必注册或输入口令。启动所需 registry 查询仅允许原始参数恰为 `action=hello`，不开放登记或修改行为。

2026-09-21 已升级至 Netdata 2.11.1，软件源从停更的 PackageCloud 迁至官方 stable 源。公开代理额外拦截 MCP/SSE 及 WebSocket Upgrade，避免新版本增加远程工具执行入口；新增 OTEL 采集器在 infra 的 Netdata 配置中显式停用。

### 首页常用入口与状态摘要（2026-09-22）

首页按「日报中心 → mini-hermes + pi → 系统与网络状态 → 投研辩论场」排列四个入口，缩短首屏介绍。Signal Gate 归入日报来源，Netdata 归入系统深度监控；仍保留各自现有 URL。Telegram 链接仅打开公开机器人主页，不发送消息、不更改机器人权限。nnG8 的研究项目与完整研究附件不在本机门户范围内。

`app/home_page.py` 只通过同源 GET 读取原有 `/reports/data.json` 与 `/ops/data.json`，不携带认证凭据、不存浏览器缓存，不增加后端权限或采集任务。日报只展示来源的最新留存日期，不能当作已发送确认；来源部分可用、缺失、快照超过 30 分钟分别提示。运维只统计固定 12 项已监测服务与 4 类巡检，含独立的 Signal Gate 收件核心与人审进程，不能称为整机全服务覆盖。巡检按自身实际时间与原有过期阈值复核；运维快照超过 3 分钟、时间缺失/超前、网络失败或结构不完整均不能显示正常。

页面每 60 秒重读快照、每 15 秒重新判断时效。两个来源读取彼此独立，单侧失败不会隐藏另一侧的有效信息；关闭 JavaScript 时保留普通入口并明确摘要不可用。所有动态展示均使用纯文本，公开访问标签与健康状态分开；进程 active 不是 Telegram、模型或代理端到端成功证明。

### 日报快照边界

`project-portal-export.timer` 每约 5 分钟运行无网络的只读导出器。它不生成研究、不发送 Telegram、不修改业务数据。最多取每类最近 30 份已留存报告：

- mini-hermes：仅查询 SQLite `market_reports` 的日期、正文及保存/更新时间，`mode=ro`，支持在线 WAL。该表没有发送回执，因此不能声称已送达。
- Signal Gate：只读取 `out/daily-YYYY-MM-DD.md` 与对应投递回执；日期、正文哈希、分片和确认时间匹配才展示已确认发送。质量问题独立展示，发送成功不等于内容完整。

导出路径固定为 `/var/lib/project-portal/reports.json`（目录 `root:www-data 0750`、文件 `0640`），nginx 仅通过限流的精确只读路径公开该文件；不开放目录浏览。应用进程不读取源数据库、秘密配置、聊天、raw inbox、日志或导出文件；直接请求后端 `/reports/data.json` 返回 404。

页面区分报告日期、保存/生成时间、网页同步时间和投递状态。海外晨报按既有周二至周六计划展示，不将周一的周六最新报告自动判过期；来源日期与问题以原报告/回执为准。快照超过 30 分钟显示同步延迟，不冒充实时状态。正文始终按纯文本显示，不执行 HTML。

### Signal Gate 今日双状态（2026-09-21）

日报中心顶部两个状态固定对应北京时间今天，不跟随归档选择切换：

- **当日已发日报**：只用当天正文和哈希匹配的真实投递回执。已确认发送和回执记录的质量问题分别展示；缺回执、正文不匹配、当日无报告均不能显示正常。今天的输入恢复不会清除早晨回执的问题。
- **当前输入校验**：原有五分钟导出启动前，先运行独立的 `project-portal-inputs.service`。该服务以 `signal-gate` 身份执行固定 `digest.py --dry-run --json`，只在内存中校验/预览，不保存报告、不发送消息或执行审批。网络被隔离、密钥与 out 路径不可见，业务文件系统只读，仅独立状态目录可写。

校验器由 Signal Gate 仓库维护：`app/input_status.py`、`systemd/project-portal-inputs.service`。状态文件 `/var/lib/project-portal-inputs/status.json` 为 `signal-gate:signal-gate 0600`，目录0700；门户导出器保留既有 `CAP_DAC_READ_SEARCH`，只读取此白名单快照，不新增 raw inbox 读取权限。公开数据仅增加日期、独立校验时间、状态、固定问题代码，不输出源正文、哈希、消息ID、路径或凭据。

超过15分钟、日期错位、时间超前、格式/属主/权限错误、命令失败均降级为过期或未知；导出器和页面分别验证，网页挂着不刷新也会重新判断时效。`clear` 仅代表现有校验未发现问题，**不代表研究内容完备、准时交付或已补发**。原有日报异常监控保留，不能因当前输入恢复而修改历史告警。

部署需安装上述 Signal Gate 单元及本仓库的 `project-portal-export.service`（Wants/After 依赖），沿用现有 timer，不新增定时器或告警。校验失败不阻断旧报告阅读。回退只需撤回本次确切代码/单元依赖，保留原始业务数据和回执。

## 本地验证

### 运维与网络服务快照（2026-09-21）

主页的运维卡片链接到 `/ops/`。独立 `project-portal-ops.timer` 每约 60 秒采集；页面每 60 秒读取，超过 3 分钟标为历史状态。采集器不重跑业务巡检、不发送消息、不读取秘密配置；仅自身快照可写。MTG 现有 loopback 指标端点可读，其他网络访问被 systemd 的 localhost 白名单限制；未开放新端口。

| 指标 | 权威来源与口径 |
|---|---|
| 主机资源 | `/proc` 与根目录文件系统；内存已用=总量−可用，CPU 使用率为相邻采样均值 |
| 服务状态 | 固定 12 个 systemd unit 的白名单属性（含 Signal Gate 收件与人审两个独立服务）；内存峰值来自对应 cgroup。仅已监测范围，运行中≠业务端到端通过 |
| 主机网络 | 有设备关联的网卡累计计数；速率为相邻采样差，重启/计数回退/间隔异常不计算。非套餐计费数据 |
| 监听 | 内核 TCP/TCP6 的固定 8443、9443、18765、19999 端口；不导出任何地址，不证明公网/家庭可达 |
| MTG | 只读本机 `19091/metrics`；仅连接数、方向聚合字节数和保护机制计数，丢弃所有地址/DC标签。计数从当前进程启动累计 |
| 运维检查 | 已有 business-health、subscription-health、config-drift 状态；分别保留各自检查时间。业务25分钟、订阅/漂移45分钟、晨报27小时过期 |
| 订阅分层 | 最新检查日志中固定字段：下载、格式、证书剩余天数、mihomo TCP 检测；按日志时间选最新，不导出原始日志或URL |

缺失/失效/过期不显示绿色。订阅 TCP 通过不代表 REALITY 认证或家庭线路成功。只暴露 `/var/lib/project-portal/ops.json` 的精确文件；采样内部状态 `ops-private.json` 为0600且无网页路由。服务进程无读取任意日志、配置或业务库的新权限。

新增 exporter 与页面分别有源数据白名单、计数重置、时间、新旧记录、缺失状态、文本注入、路由与只读边界回归。部署仅重启工作台进程、reload nginx并启用该采集器，其他业务不重启。

```bash
cd /opt/investment-debate-arena
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app .venv/bin/python -m unittest discover -s tests -v
# 本地假后端验证 Netdata 公网只读规则，不请求真实管理接口（需 nginx）
.venv/bin/python -B scripts/check_netdata_policy.py
curl -fsS http://127.0.0.1:18766/readyz
curl -fsS http://127.0.0.1:18765/healthz
```

`POST /api/debate` 仅接受 `application/json`，正文必须恰好包含字符串字段 `ticker` 与 `thesis`。代码格式限 `A-Z`、数字、点、脱字符和连字符，长度 1–16；观点长度为 1–600。

## 发布与回滚

发布先运行完整测试、导出器假数据测试、nginx/systemd 配置校验。保持 Git 中的 nginx/unit 模板与安装文件一致，只重启本服务，不重启 mini-hermes、Signal Gate 或其他业务。

日报页面与数据入口必须通过不携带凭据可读、目录穿越不能扩大读取范围、后端直接读取 404 的检查。公网首页与 Arena 保持可用，Netdata 图表免登录可读、配置和控制接口不可用，订阅配置字节不变。部署失败时恢复本次变更前的确切文件/服务状态，禁止重置整个仓库。

若之后撤回门户，先停用 `project-portal-export.timer`，再按已记录的前版本恢复本项目和 nginx 配置；认证边界不扩大。无需回滚业务数据库，也无需重发任何消息。

## 演示资料来源

1. [Apple 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm)
2. [Apple FY2026 Q1 results](https://www.apple.com/newsroom/2026/01/apple-reports-first-quarter-results/)
