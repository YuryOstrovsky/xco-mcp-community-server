# Security Policy

## Supported versions

This project follows a rolling release on the `main` branch. Security fixes are
applied to `main`; there is no separate long-term-support branch.

| Version | Supported |
|---------|-----------|
| `main` (latest) | ✅ |
| older tags | ⚠️ best effort |

## Reporting a vulnerability

**Please do not open a public issue for security vulnerabilities.**

Report privately using **GitHub's "Report a vulnerability"** button under the
repository's **Security** tab (Private Vulnerability Reporting), or email the
maintainers at **yostrovs@extremenetworks.com**.

Please include:

- A description of the vulnerability and its impact.
- Steps to reproduce (a minimal proof-of-concept if possible).
- Affected version / commit.
- Any suggested remediation.

We aim to acknowledge reports within **5 business days** and to provide a
remediation timeline after triage. Please give us a reasonable window to fix the
issue before any public disclosure.

## Scope & hardening notes

This is a **read-only** MCP server for ExtremeCloud Orchestrator (XCO) and SLX
RESTCONF. Security-relevant properties of this edition:

- **No mutating operations** — every catalogued tool is `SAFE_READ`; the server
  does not expose config-change or destructive RESTCONF/SLX operations.
- **Credentials** are supplied via environment (`.env`, never committed) and are
  redacted from logs; do not commit real credentials.
- **Network exposure** — the server talks to your XCO controller and switches.
  Run it on a trusted management network; put authentication/TLS termination in
  front of it (e.g. a reverse proxy) if exposing it beyond localhost.
- **Rate limiting** — a per-IP limiter is enabled by default
  (`MCP_RATE_LIMIT_RPM`).
- Dependencies are pinned in `requirements.txt`; we bump security-relevant
  packages (starlette, fastapi, cryptography, urllib3, requests, idna) as
  advisories land.
