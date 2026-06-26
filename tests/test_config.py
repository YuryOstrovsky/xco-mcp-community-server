"""Config / env-var handling — guard against the `--env-file` whitespace footgun."""

from mcp_runtime.auth import AuthManager


def test_auth_strips_whitespace_from_env(monkeypatch):
    # Docker --env-file passes values literally (incl. trailing spaces); the
    # server must strip them so a stray space in XCO_HOST doesn't URL-encode to
    # %20 and break DNS resolution.
    monkeypatch.setenv("XCO_HOST", "  10.0.0.1  ")
    monkeypatch.setenv("XCO_USERNAME", " admin ")
    monkeypatch.setenv("XCO_PASSWORD", " secret ")

    a = AuthManager()

    assert a.host == "10.0.0.1"
    assert a.username == "admin"
    assert a.password == "secret"
