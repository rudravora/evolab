"""M0: health, error shape, security headers, owner sign-in, agent registry routes."""

from conftest import OWNER_PASSWORD

API = "/api/v1"


def assert_error(r, status, code):
    assert r.status_code == status, r.text
    body = r.json()
    assert set(body) == {"error"}
    assert body["error"]["code"] == code
    assert "Traceback" not in r.text


def test_health_needs_no_auth(client):
    r = client.get(f"{API}/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok" and body["version"] and body["time"].endswith("Z")


def test_security_headers(client):
    h = client.get(f"{API}/health").headers
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in h["content-security-policy"]
    assert "strict-transport-security" not in h  # only behind https


def test_cors_allows_only_configured_origin(client):
    ok = client.options(f"{API}/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    bad = client.options(f"{API}/health", headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in bad.headers


def test_unknown_route_uses_error_shape(client):
    assert_error(client.get(f"{API}/nope"), 404, "not_found")


def test_dashboard_routes_need_auth(client):
    assert_error(client.get(f"{API}/agents"), 401, "unauthorized")
    assert_error(client.get(f"{API}/auth/me"), 401, "unauthorized")


def test_login_wrong_password(client):
    assert_error(client.post(f"{API}/auth/login", json={"password": "nope"}), 401, "unauthorized")


def test_login_validation_error_shape(client):
    r = client.post(f"{API}/auth/login", json={})
    assert_error(r, 422, "validation_error")
    assert r.json()["error"]["details"]["fields"]


def test_login_sets_httponly_cookie_and_bearer_works(client):
    r = client.post(f"{API}/auth/login", json={"password": OWNER_PASSWORD})
    assert r.status_code == 200
    assert "httponly" in r.headers["set-cookie"].lower()
    assert client.get(f"{API}/auth/me").json() == {"id": "usr_owner"}  # via cookie
    token = r.json()["token"]
    client.cookies.clear()
    assert client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}"}).status_code == 200
    assert_error(client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {token}x"}), 401, "unauthorized")


def test_logout_clears_cookie(authed):
    assert authed.post(f"{API}/auth/logout").status_code == 204
    authed.cookies.clear()
    assert_error(authed.get(f"{API}/auth/me"), 401, "unauthorized")


def test_login_is_rate_limited(client):
    for _ in range(5):
        client.post(f"{API}/auth/login", json={"password": "nope"})
    assert_error(client.post(f"{API}/auth/login", json={"password": OWNER_PASSWORD}), 429, "rate_limited")


def test_expired_token_rejected(settings):
    from app.security import issue_token, read_token

    settings.session_ttl_s = -1
    token, _ = issue_token(settings)
    assert read_token(token, settings) is None


def test_list_agents(authed):
    agents = authed.get(f"{API}/agents").json()
    assert len(agents) == 12
    judges = [a for a in agents if a["role"] == "council_judge"]
    assert len(judges) == 3 and all(a["kind"] == "core" and not a["evolvable"] for a in judges)
    assert {a["current_version"]["model"] for a in judges} == {"strong", "code", "fast"}


def test_list_agents_filter_by_kind(authed):
    core = authed.get(f"{API}/agents", params={"kind": "core"}).json()
    assert {a["role"] for a in core} == {"meta_controller", "evaluator", "council_judge"}
    assert_error(authed.get(f"{API}/agents", params={"kind": "bogus"}), 422, "validation_error")


def test_agent_detail_and_versions(authed):
    a = authed.get(f"{API}/agents/agt_debugger").json()
    assert a["current_version"]["capability_tags"] == ["debug:python", "debug:deps"]
    versions = authed.get(f"{API}/agents/agt_debugger/versions").json()
    assert [v["version"] for v in versions] == [1]
    detail = authed.get(f"{API}/agents/agt_debugger/versions/1").json()
    assert "Debugger" in detail["system_prompt"] and detail["output_schema"] == "debugger.json"
    assert_error(authed.get(f"{API}/agents/agt_nope"), 404, "not_found")
    assert_error(authed.get(f"{API}/agents/agt_debugger/versions/9"), 404, "not_found")


def test_seeding_is_idempotent(app):
    from app.seed import seed_agents

    with app.state.db.sessionmaker() as s:
        assert seed_agents(s) == 0
