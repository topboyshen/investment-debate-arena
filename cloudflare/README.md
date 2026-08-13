# Cloudflare HTTPS deployment

Production hostname: `https://arena.jiejiezi.ccwu.cc`

## Data path

```text
Browser
  -> Cloudflare edge TLS
  -> remote-managed Tunnel: dedirock-arena
  -> http://127.0.0.1:18765 (nginx Basic Auth and request controls)
  -> http://127.0.0.1:18766 (Arena application)
```

The Tunnel must terminate at nginx on port `18765`, not at the Python backend on `18766`. This preserves the 4 KiB request limit, rate and connection limits, proxy timeouts, and security headers.

## Secret boundaries

- `/etc/cloudflared/tunnel-token`: `root:cloudflared`, mode `0640`.
- `/etc/nginx/arena.htpasswd`: `root:www-data`, mode `0640`.
- No Tunnel token, plaintext password, account `cert.pem`, credential JSON, `.env`, backup, or generated artifact belongs in Git.
- The checked-in systemd unit uses `--token-file`; it contains no token.

## Acceptance checks

```bash
systemctl is-active cloudflared nginx investment-debate-arena
curl -fsS http://127.0.0.1:18766/readyz
curl -sS -o /dev/null -w '%{http_code}\n' http://127.0.0.1:18765/
ufw status
```

The nginx check should return `401`, and UFW must not list an allow rule for `18765/tcp`. From an external machine, plain HTTP must redirect to HTTPS before presenting an authentication challenge; the HTTPS hostname should return `401` without credentials and `200` with credentials, and TLS verification must succeed. Direct access to `23.95.122.93:18765` should time out.

## Access mode

The live no-cost gate is nginx Basic Auth. Cloudflare Zero Trust email OTP was intentionally not activated because the account checkout required a payment method and authorization for overage charges. If the account owner later activates Zero Trust, create a self-hosted Access application for this exact hostname, allow only the exact owner email, and require One-time PIN. Verify the Access redirect and authenticated application before removing Basic Auth.

## Rollback

1. If emergency IP access is required, keep Basic Auth enabled and allow only a known administrator address: `ufw allow from <ADMIN_IP> to any port 18765 proto tcp`. Never reopen `18765/tcp` to everyone.
2. Confirm the restricted IP fallback works with authentication before stopping `cloudflared.service`.
3. Disable the published Tunnel route in Cloudflare. Do not delete unrelated DNS records, nginx listeners, or Mini Hermes services.
4. The `cloudflare-arena-https-redirect-*` archive can reverse only the redirect/real-IP change. Do not restore the pre-auth `cloudflare-arena-auth-*` nginx file while any public firewall rule exists.
