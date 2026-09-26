"""운영 준비: 상태 검사와 HTTPS 설정을 PostgreSQL의 임시 스키마에서 검증합니다."""
from contextlib import contextmanager

import psycopg
import pytest
from fastapi.testclient import TestClient

from test_rules import runtime, scalar
from app import db, main


def test_health_is_read_only_and_never_caches_readiness(runtime):
    client, _, _ = runtime
    for _ in range(2):
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert response.json()["database"] is True
        assert response.json()["model"]["ready"] is True
        assert response.headers["Cache-Control"] == "no-store"
    assert scalar("SELECT count(*) FROM puzzles") == 0
    assert scalar("SELECT count(*) FROM users") == 0
    assert scalar("SELECT count(*) FROM games") == 0


def test_unprepared_model_returns_503_without_internal_error(runtime):
    client, _, engine = runtime
    engine.ready = False
    engine.error = "TEST ONLY: private model file /internal/path/model.bin"
    response = client.get("/api/health")
    assert response.status_code == 503
    data = response.json()
    assert data["status"] == "model_unavailable"
    assert data["database"] is True and data["model"]["ready"] is False
    assert "private model file" not in response.text
    assert "/internal/path" not in response.text
    assert response.headers["Cache-Control"] == "no-store"
    assert scalar("SELECT count(*) FROM puzzles") == 0


@pytest.mark.parametrize("failure_point", ["connect", "query"])
def test_database_failure_returns_503_without_internal_error(runtime, monkeypatch, caplog, failure_point):
    client, _, _ = runtime
    internal_message = "TEST ONLY: private database connection detail"

    @contextmanager
    def failed_connection():
        if failure_point == "connect":
            raise psycopg.OperationalError(internal_message)

        class FailedQuery:
            def execute(self, *args, **kwargs):
                raise psycopg.OperationalError(internal_message)

        yield FailedQuery()

    # 앱 기동 후에만 실패를 모사해 실제 DB를 중단하지 않습니다.
    with monkeypatch.context() as patch:
        patch.setattr(db, "connect", failed_connection)
        response = client.get("/api/health")
    assert response.status_code == 503
    assert response.json()["status"] == "database_unavailable"
    assert response.json()["database"] is False
    assert response.headers["Cache-Control"] == "no-store"
    assert internal_message not in response.text
    assert internal_message not in caplog.text
    assert "OperationalError" in caplog.text
    assert client.get("/api/health").status_code == 200


def test_https_origin_and_secure_cookie_preserve_game_session(runtime, monkeypatch):
    origin = "https://ganmantle.example"
    monkeypatch.setenv("APP_ORIGIN", origin)
    monkeypatch.setenv("COOKIE_SECURE", "true")
    with TestClient(main.app, base_url=origin) as client:
        registered = client.post("/api/users", json={"nickname": "HTTPS검증"}, headers={"Origin": origin})
        assert registered.status_code == 200
        cookie = registered.headers["set-cookie"]
        assert "Secure" in cookie and "HttpOnly" in cookie and "SameSite=lax" in cookie
        state = registered.json()
        assert client.get("/api/state").json()["user"] == state["user"]
        started = client.post("/api/start", json={"puzzle_date": state["puzzle_date"]}, headers={"Origin": origin})
        assert started.status_code == 200
        assert started.json()["game"]["attempts"] == 0
        for blocked_origin in ("http://ganmantle.example", "https://another.example"):
            rejected = client.post("/api/users", json={"nickname": "변경거부"}, headers={"Origin": blocked_origin})
            assert rejected.status_code == 403
            assert rejected.json()["detail"]["code"] == "invalid_origin"
        assert client.get("/api/state").json()["user"] == state["user"]
