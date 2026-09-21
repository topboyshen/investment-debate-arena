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
| `/` | 项目工作台，只列功能与入口，不公开真实报告或运行细节 | 公开 |
| `/arena/` | 投研辩论场原型 | 公开、限流 |
| `/arena/api/demo`、`/arena/api/debate` | 原有静态演示接口 | 公开、限流 |
| `/api/demo`、`/api/debate` | 兼容原有客户端与检查 | 公开、限流 |
| `/reports/` | 日报中心 | 按所有者要求公开阅读、无需登录 |
| `/reports/data.json` | 唯一报告数据入口 | 公开只读、禁止缓存 |
| `/netdata/` | Netdata 监控 | 按所有者要求公开只读；控制与配置接口不开放 |

任何知道网址的人均可读取当前与历史留存日报；`noindex` 仅建议搜索引擎不收录，不是访问控制。

私有订阅入口不变，不在工作台展示。网页没有 pi 执行、聊天、审批、重发日报、管理服务或读取任意文件的权限。
nginx 与应用仍仅监听回环地址，公网访问经 Cloudflare Tunnel，未新增防火墙放行。

Netdata 公网监控会公开主机资源、运行指标及仪表盘提供的相关信息。仅在此域名的 `/netdata/` 移除登录要求，保留限流和禁止缓存；配置下载、管理与函数执行入口不开放。原有回环 `19998` SSH 隧道入口与凭据文件不变。

Netdata 自带的云账号登录是可选项。首次看到欢迎页时，选择 `Skip and use the dashboard anonymously` 即可查看图表，不必注册或输入口令。启动所需 registry 查询仅允许原始参数恰为 `action=hello`，不开放登记或修改行为。

### 日报快照边界

`project-portal-export.timer` 每约 5 分钟运行无网络的只读导出器。它不生成研究、不发送 Telegram、不修改业务数据。最多取每类最近 30 份已留存报告：

- mini-hermes：仅查询 SQLite `market_reports` 的日期、正文及保存/更新时间，`mode=ro`，支持在线 WAL。该表没有发送回执，因此不能声称已送达。
- Signal Gate：只读取 `out/daily-YYYY-MM-DD.md` 与对应投递回执；日期、正文哈希、分片和确认时间匹配才展示已确认发送。质量问题独立展示，发送成功不等于内容完整。

导出路径固定为 `/var/lib/project-portal/reports.json`（目录 `root:www-data 0750`、文件 `0640`），nginx 仅通过限流的精确只读路径公开该文件；不开放目录浏览。应用进程不读取源数据库、秘密配置、聊天、raw inbox、日志或导出文件；直接请求后端 `/reports/data.json` 返回 404。

页面区分报告日期、保存/生成时间、网页同步时间和投递状态。海外晨报按既有周二至周六计划展示，不将周一的周六最新报告自动判过期；来源日期与问题以原报告/回执为准。快照超过 30 分钟显示同步延迟，不冒充实时状态。正文始终按纯文本显示，不执行 HTML。

## 本地验证

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
