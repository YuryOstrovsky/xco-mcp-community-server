# Release Checklist

Run and record every step below **before tagging a release** and announcing the
repo as community-ready. Paste the captured versions and the smoke-test summary
into the release notes / GitHub Release for that tag.

> This edition is **read-only**. The smoke tests are the live release gate; the
> offline unit tests (`pytest`) run in CI on every push.

## 1. Offline unit tests (no XCO needed)

```bash
pytest -q
```
Expected: all tests pass (e.g. `27 passed`).

## 2. Build the image

```bash
docker build -t xco-mcp-community:1.0.0 .
```
Expected: build completes; image tagged `xco-mcp-community:1.0.0`.

## 3. Start the server

```bash
# Create .env first (copy .env.example and fill in real XCO/RESTCONF creds)
docker compose up -d
```

## 4. Health / discovery / readiness

```bash
curl http://localhost:8000/health
curl http://localhost:8000/tools
curl http://localhost:8000/ready
```
Expected: `/health` ok; `/tools` returns the catalog; `/ready` reports
`{"status":"ready", ... "xco":true}` against a reachable XCO.

## 5. Live smoke tests (release gate)

Require a running server + reachable XCO and SLX switches.

```bash
python smoke-test/smoke_tier2_a.py --url http://localhost:8000
python smoke-test/smoke_tier2_b.py --url http://localhost:8000
python smoke-test/smoke_tier2_c.py --url http://localhost:8000
python smoke-test/smoke_tier2_d.py --url http://localhost:8000
python smoke-test/smoke_tier2_e.py --url http://localhost:8000
```

---

## Tested versions (fill in at release time)

| Item | Version |
|---|---|
| XCO version | `<fill in>` |
| SLX-OS version | `<fill in — e.g. SLX9150 / 20.8.x>` |
| Python version | `<fill in — CI matrix: 3.10, 3.11>` |
| Docker version | `<fill in>` |
| Image tag | `xco-mcp-community:1.0.0` |
| Test date | `<YYYY-MM-DD>` |

## Smoke-test summary (fill in at release time)

| Batch | Result | Notes |
|---|---|---|
| `smoke_tier2_a` | PASS / FAIL | |
| `smoke_tier2_b` | PASS / FAIL | |
| `smoke_tier2_c` | PASS / FAIL | |
| `smoke_tier2_d` | PASS / FAIL | |
| `smoke_tier2_e` | PASS / FAIL | |

## Sign-off

- [ ] Unit tests pass (`pytest -q`)
- [ ] Image builds and starts; `/health`, `/tools`, `/ready` all OK
- [ ] All five smoke batches PASS against live XCO + switches
- [ ] Versions table and smoke summary captured in the GitHub Release notes
- [ ] `CHANGELOG.md` updated for the tag
- [ ] Git tag created and pushed
