# Cloudflare HTTPS deployment

Production hostname: `https://arena.jiejiezi.ccwu.cc`

## Data path

```text
Browser
  -> Cloudflare edge TLS
  -> remote-managed Tunnel: dedirock-arena
  -> http://127.0.0.1:18765 (nginx public read-only policy and request controls)
  -> http://127.0.0.1:18766 (Arena application)
```

The Tunnel must terminate at nginx on port `18765`, not at the Python backend on `18766`. This preserves the 4 KiB request limit, rate and connection limits, proxy timeouts, and security headers.

## Secret boundaries

- `/etc/cloudflared/tunnel-token`: `root:cloudflared`, mode `0640`.
- Existing password files remain machine-local; public portal access does not use them.
- No Tunnel token, plaintext password, account `cert.pem`, credential JSON, `.env`, backup, or generated artifact belongs in Git.
- The checked-in systemd unit uses `--token-file`; it contains no token.

## Acceptance checks

```bash
systemctl is-active cloudflared nginx investment-debate-arena
curl -fsS http://127.0.0.1:18766/readyz
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18765/
sudo ufw status
```

The nginx homepage check should return `200` without credentials. The HTTPS hostname must also return `200` anonymously with valid TLS; external plain HTTP must redirect to HTTPS. UFW must not list a public allow rule for `18765/tcp`, and nginx must listen only on loopback. Do not reopen the origin to test public access.

The exact `/reports/data.json` and `/ops/data.json` paths serve only their prepared snapshots, reject writes, and disable caching. Sensitive files, private sampler state, arbitrary files, Netdata configuration/control/unknown API paths, MCP/SSE and WebSocket upgrades must remain inaccessible. Run the repository unit tests and `scripts/check_netdata_policy.py`; the latter checks actual nginx rules against a harmless temporary upstream and never calls live management APIs.

## Access mode

Since the owner's 2026-09-21 decision, the portal, reports and Netdata monitoring are public without login; Arena's existing demo endpoints remain public and rate limited. This supersedes the earlier Basic Auth deployment. Keep the public read-only policy and sensitive/management deny rules together. Do not restore login as part of a source synchronization or infer permission to expand data exposure.

Cloudflare Tunnel terminates at nginx and does not grant the application permission to read private exports, source databases, credentials, logs or arbitrary paths. Private subscription locations stay in the separate root-only nginx include and must not be copied into this repository or linked from the portal.

## Rollback

1. Restore only the exact files and service state recorded for the failed change. Keep the nginx origin on loopback and preserve the private/control deny rules.
2. Use the existing administrative SSH path for diagnosis. Any different access or firewall policy requires a separate owner decision; never reopen `18765/tcp` to everyone.
3. Change a published Tunnel route only as part of an explicitly scoped rollback. Do not delete unrelated DNS records, nginx listeners or service state.
4. Historical archives may contain an obsolete authentication or listener policy. Review the exact diff before using one; do not reset the whole repository or replace current public read-only boundaries with an earlier deployment.
