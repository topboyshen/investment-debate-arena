# 多角色投研辩论场原型

## 概览

该服务将用户输入的证券代码与研究观点转成五个角色的结构化论证，并由主审给出共识、分歧、关键证据、待验证问题与逻辑失效条件。已覆盖发行人的内容按 **FACT / INFERENCE / SCENARIO** 分层；未覆盖代码使用 **COVERAGE_NOTICE / INFERENCE / SCENARIO**，不会把内部覆盖状态伪装成外部事实。演示事实保留来源 URL、发布日期与证据快照日期。

系统仅用于研究流程组织，**不构成个性化财务建议，不提供确定性交易指令**。

## 当前边界

- 当前版本是确定性演示原型，不会自动抓取实时行情或生成个性化交易建议。
- 公网部署必须由反向代理限制请求大小、并发和超时；若入口没有可信 HTTPS 与访问控制，请勿提交敏感或专有研究观点。
- 服务不需要任何 API Key、Telegram Token 或 Mini Hermes 配置；这些内容不得加入仓库。

## 隔离部署

| 项目 | 配置 |
|---|---|
| 项目目录 | `/opt/investment-debate-arena` |
| 专用账户 | `debatearena` |
| 专用环境 | `/opt/investment-debate-arena/.venv` |
| 后端监听 | `127.0.0.1:18766` |
| 可信入口 | `https://arena.jiejiezi.ccwu.cc`（Cloudflare Tunnel → nginx 密码门） |
| systemd 单元 | `investment-debate-arena.service` |
| 健康检查 | `GET /healthz` |
| 就绪检查 | `GET /readyz` |

该原型不读取、不修改 Mini Hermes 的代码、配置、端口或 systemd 单元。

## 本地验证

```bash
cd /opt/investment-debate-arena
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=app .venv/bin/python -m unittest discover -s tests -v
curl -fsS http://127.0.0.1:18766/readyz
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18765/  # 期望 401
```

## 可信 HTTPS 与访问控制

- `cloudflared` 仅建立出站 Tunnel，路由到 `http://127.0.0.1:18765`；不会绕过 nginx 的请求体、限流、并发和超时保护。
- nginx 对页面和 API 启用 Basic Auth，密码文件为服务器上的 `/etc/nginx/arena.htpasswd`，不进入 Git。
- UFW 不再放行公网 `18765/tcp`；旧的 `http://23.95.122.93:18765/` 入口不可达。
- Cloudflare Zero Trust 邮箱验证码未启用：当前免费版激活页面要求绑定支付方式并授权超额计费。若以后由账户所有者完成激活，可在不改应用的情况下用 Access 替换 Basic Auth。
- Tunnel 的 token、账户证书、密码文件和任何凭据 JSON 都不得提交。具体部署与回滚见 `cloudflare/README.md`。

`POST /api/debate` 仅接受 `application/json`，正文必须恰好包含字符串字段 `ticker` 与 `thesis`。代码格式限 `A-Z`、数字、点、脱字符和连字符，长度 1–16；观点长度为 1–600。

## 回滚

服务和文件均独立。升级前归档保存在 `/root/backups/`。如需回滚版本，应先停止 Arena、恢复归档中的应用和 unit、移除对应 nginx Arena 配置，再验证配置后启动；不要直接删除项目目录。Mini Hermes 不在回滚范围内。

```bash
sudo systemctl stop investment-debate-arena.service
sudo nginx -t
# 从 /root/backups/investment-debate-arena-<UTC>.tar.gz 恢复后：
sudo systemctl daemon-reload
sudo systemctl start investment-debate-arena.service
sudo nginx -t && sudo systemctl reload nginx
```

## 演示资料来源

1. [Apple 2025 Form 10-K](https://www.sec.gov/Archives/edgar/data/320193/000032019325000079/aapl-20250927.htm)
2. [Apple FY2026 Q1 results](https://www.apple.com/newsroom/2026/01/apple-reports-first-quarter-results/)
