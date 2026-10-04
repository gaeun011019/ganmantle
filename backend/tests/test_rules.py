"""실제 PostgreSQL에서 게임 규칙을 검사합니다. 운영 유사도는 이 가짜 모델을 사용하지 않습니다."""

import os
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import db, game, main


class RuleTestEngine:
    """100으로 반올림되는 오답/계산 실패를 재현하는 규칙 검사용 모형입니다."""

    ready = True
    name = "TEST ONLY: deterministic game-rule fixture"
    error = None
    fingerprint = "test-rules-v1"
    after_score = None

    def rankings(self, answer):
        # API 규칙용 고정 자료입니다. 실제 순위/경계 계산은 WordRankIndex 검사에서 따로 확인합니다.
        return {
            "ranks": {
                answer: 0,
                "연필": 1,
                "산책": 10,
                "바다": 10,
                "모니터": 10,
                "학교": 10,
                "키보드": 10,
                "걷다": 10,
                "아": 10,
                "바나나": 10,
            },
            "reference": {
                "vocabulary_size": 49485,
                "top1": 99.9999,
                "top10": 23.4567,
                "top1000": 12.5,
            },
        }

    def score(self, word, answer):
        if word == "실패":
            raise ValueError("의도한 테스트 오류")
        if self.after_score:
            self.after_score()
        if word == answer:
            return 100.0
        return 99.9999 if word == "연필" else 23.4567


@pytest.fixture
def runtime(monkeypatch, tmp_path):
    database_url = os.getenv("TEST_DATABASE_URL")
    if not database_url:
        pytest.skip(
            "TEST_DATABASE_URL을 지정하면 실제 PostgreSQL의 별도 임시 스키마에서 검사합니다."
        )
    schema = "ganmantle_test_" + uuid4().hex
    with psycopg.connect(database_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    # public를 검색하면 기존 앱 테이블로 잘못 연결될 수 있어 임시 스키마만 씁니다.
    monkeypatch.setenv(
        "DATABASE_URL", make_conninfo(database_url, options=f"-c search_path={schema}")
    )
    monkeypatch.delenv("APP_ORIGIN", raising=False)
    monkeypatch.setenv("COOKIE_SECURE", "false")
    clock = {"now": datetime(2026, 9, 19, 2, 0, tzinfo=UTC)}
    monkeypatch.setattr(game, "utcnow", lambda: clock["now"])
    answers = tmp_path / "answers.txt"
    answers.write_text("사과\n", encoding="utf-8")
    monkeypatch.setattr(game, "ANSWER_PATH", answers)
    engine = RuleTestEngine()
    monkeypatch.setattr(main, "get_engine", lambda: engine)
    try:
        with TestClient(main.app) as client:
            yield client, clock, engine
    finally:
        # 이름은 위에서 생성한 임시 스키마로 한정합니다. 기존 테이블은 건드리지 않습니다.
        with psycopg.connect(database_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def begin(client, nickname="검증사용자"):
    assert client.post("/api/users", json={"nickname": nickname}).status_code == 200
    day = client.get("/api/state").json()["puzzle_date"]
    result = client.post("/api/start", json={"puzzle_date": day})
    assert result.status_code == 200
    return day, result.json()


def submit(client, day, word):
    return client.post("/api/guesses", json={"puzzle_date": day, "word": word})


def scalar(query):
    with db.connect() as conn:
        row = conn.execute(query).fetchone()
        return next(iter(row.values()))


def test_start_time_reconnect_and_db_restart(runtime):
    client, clock, _ = runtime
    day, initial = begin(client)
    started = initial["game"]["started_at"]
    clock["now"] += timedelta(minutes=7)
    repeated = client.post("/api/start", json={"puzzle_date": day}).json()
    assert repeated["game"]["started_at"] == started
    assert repeated["game"]["elapsed_ms"] == 420000
    submit(client, day, "산책")
    with TestClient(main.app, cookies=dict(client.cookies)) as reconnect:
        restored = reconnect.get("/api/state").json()
        assert restored["user"] == initial["user"]
        assert restored["game"]["attempts"] == 1
        assert restored["game"]["elapsed_ms"] == 420000
        assert restored["game"]["started_at"] == started
    assert scalar("SELECT answer FROM puzzles") == "사과"
    assert scalar("SELECT count(*) FROM games") == 1


def test_nfc_duplicate_moves_row_and_concurrent_resubmits(runtime):
    client, _, _ = runtime
    day, _ = begin(client)
    submit(client, day, "산책")
    submit(client, day, "바다")
    duplicate = submit(client, day, " " + unicodedata.normalize("NFD", "산책") + " ").json()
    assert duplicate["duplicate"] is True
    assert duplicate["game"]["attempts"] == 2
    assert [item["word"] for item in duplicate["game"]["guesses"]] == ["산책", "바다"]
    assert duplicate["game"]["guesses"][0]["attempt"] == 1
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: submit(client, day, "바나나"), range(4)))
    assert all(response.status_code == 200 for response in responses)
    assert sum(not response.json()["duplicate"] for response in responses) == 1
    assert client.get("/api/state").json()["game"]["attempts"] == 3
    assert scalar("SELECT count(*) FROM guesses") == 3


def test_exact_answer_and_frozen_completion_time(runtime):
    client, clock, _ = runtime
    day, _ = begin(client)
    rounded = submit(client, day, "연필").json()
    assert round(rounded["game"]["guesses"][0]["similarity"], 2) == 100.0
    assert rounded["game"]["status"] == "playing"
    clock["now"] += timedelta(seconds=12, milliseconds=345)
    correct = submit(client, day, unicodedata.normalize("NFD", "사과")).json()
    assert correct["game"]["status"] == "completed"
    assert correct["game"]["elapsed_ms"] == 12345
    assert correct["game"]["attempts"] == 2
    clock["now"] += timedelta(hours=1)
    again = submit(client, day, "사과").json()
    assert again["duplicate"] is True
    assert again["game"] == correct["game"]
    assert submit(client, day, "바다").status_code == 409


def test_invalid_and_failed_input_do_not_count(runtime):
    client, _, _ = runtime
    day, _ = begin(client)
    for word in (" ", "가" * 41, "줄\n바꿈"):
        assert submit(client, day, word).status_code == 400
    assert submit(client, day, "실패").status_code == 503
    assert client.get("/api/state").json()["game"]["attempts"] == 0
    # 입력 사전에 없는 임의 조합은 모델을 계산하지 않고 거절합니다.
    assert submit(client, day, "새로만든한국어조합말").status_code == 400


def test_midnight_closes_only_started_incomplete_and_rejects_old_date(runtime):
    client, clock, _ = runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 58, tzinfo=UTC)
    yesterday, _ = begin(client)
    with TestClient(main.app) as solved, TestClient(main.app) as not_started:
        begin(solved, "완료사용자")
        submit(solved, yesterday, "사과")
        assert not_started.post("/api/users", json={"nickname": "미시작사용자"}).status_code == 200
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        stale = submit(client, yesterday, "사과")
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "date_changed"
        today = client.get("/api/state", params={"puzzle_date": yesterday}).json()
        assert today["date_changed"] is True
        assert today["puzzle_date"] == "2026-09-20"
        assert today["game"] is None
        assert not_started.get("/api/state").json()["game"] is None
        assert scalar("SELECT count(*) FROM games WHERE status = 'incomplete'") == 1
        assert scalar("SELECT count(*) FROM games WHERE status = 'completed'") == 1
        assert scalar("SELECT count(*) FROM games") == 2
        assert scalar("SELECT closed_at FROM games WHERE status = 'incomplete'") == clock["now"]
        fresh = client.post("/api/start", json={"puzzle_date": today["puzzle_date"]}).json()
        assert fresh["game"]["attempts"] == 0
        assert fresh["game"]["elapsed_ms"] == 0


def test_inference_crossing_midnight_is_not_counted(runtime):
    client, clock, engine = runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    day, _ = begin(client)
    engine.after_score = lambda: clock.update(now=datetime(2026, 9, 19, 15, 0, 1, tzinfo=UTC))
    response = submit(client, day, "사과")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    assert scalar("SELECT count(*) FROM guesses") == 0
    assert scalar("SELECT status FROM games") == "incomplete"


def test_nickname_unique_cookie_session_and_origin(runtime):
    client, _, _ = runtime
    begin(client, "Test이름")
    with TestClient(main.app) as stranger:
        response = stranger.post("/api/users", json={"nickname": " test이름 "})
        assert response.status_code == 409
        assert stranger.get("/api/state").json()["user"] is None
        day = stranger.get("/api/state").json()["puzzle_date"]
        assert stranger.post("/api/start", json={"puzzle_date": day}).status_code == 401
    forbidden = client.post(
        "/api/start", json={"puzzle_date": day}, headers={"origin": "https://another.example"}
    )
    assert forbidden.status_code == 403
    assert scalar("SELECT session_hash FROM users") != client.cookies["ganmantle_session"]


def test_model_missing_or_version_changed_never_invents_scores(runtime):
    client, _, engine = runtime
    day, _ = begin(client)
    submit(client, day, "산책")
    assert client.get("/api/health").json()["status"] == "ok"
    engine.fingerprint = "test-rules-v2"
    state = client.get("/api/state").json()
    assert state["model"]["ready"] is False
    health = client.get("/api/health").json()
    assert health["status"] == "model_unavailable"
    assert health["database"] is True and health["model"]["ready"] is False
    assert submit(client, day, "바다").status_code == 503
    assert submit(client, day, "산책").json()["duplicate"] is True
    assert client.get("/api/state").json()["game"]["attempts"] == 1
    engine.ready = False
    engine.error = "TEST ONLY: model missing"
    assert submit(client, day, "학교").status_code == 503


def test_simultaneous_starts_create_one_game_and_never_reset_time(runtime):
    client, clock, _ = runtime
    created = client.post("/api/users", json={"nickname": "동시시작검증"})
    assert created.status_code == 200
    assert "HttpOnly" in created.headers["set-cookie"]
    assert "SameSite=lax" in created.headers["set-cookie"]
    day = created.json()["puzzle_date"]
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(
            pool.map(lambda _: client.post("/api/start", json={"puzzle_date": day}), range(4))
        )
    assert all(response.status_code == 200 for response in responses)
    assert len({response.json()["game"]["started_at"] for response in responses}) == 1
    assert scalar("SELECT count(*) FROM games") == 1
    assert scalar("SELECT count(*) FROM puzzles") == 1
    clock["now"] += timedelta(minutes=2)
    repeated = client.post("/api/start", json={"puzzle_date": day}).json()
    assert repeated["game"]["elapsed_ms"] == 120000


def test_client_cannot_forge_game_fields_or_user_cookie(runtime):
    client, _, _ = runtime
    day, started = begin(client)
    forged = client.post(
        "/api/guesses",
        json={
            "puzzle_date": day,
            "word": "산책",
            "similarity": 100,
            "attempts": 0,
            "elapsed_ms": 1,
        },
    )
    assert forged.status_code == 422
    assert client.get("/api/state").json()["game"]["attempts"] == 0
    with TestClient(main.app) as stranger:
        stranger.cookies.set("ganmantle_session", started["user"]["id"])
        assert stranger.get("/api/state").json()["user"] is None
        assert stranger.post("/api/start", json={"puzzle_date": day}).status_code == 401


def test_failure_crossing_midnight_still_returns_date_changed(runtime, monkeypatch):
    client, clock, engine = runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    day, _ = begin(client)

    def failed_after_midnight(word, answer):
        clock["now"] = datetime(2026, 9, 19, 15, 0, 1, tzinfo=UTC)
        raise ValueError("TEST ONLY: inference failed after midnight")

    monkeypatch.setattr(engine, "score", failed_after_midnight)
    response = submit(client, day, "산책")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    assert scalar("SELECT count(*) FROM guesses") == 0
    assert scalar("SELECT status FROM games") == "incomplete"


def test_yesterday_answer_is_null_when_only_other_days_are_saved(runtime):
    client, _, engine = runtime
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO puzzles (puzzle_date, answer, model_fingerprint) VALUES (%s, %s, %s)",
            ("2026-09-17", "바다", engine.fingerprint),
        )
        conn.execute(
            "INSERT INTO puzzles (puzzle_date, answer, model_fingerprint) VALUES (%s, %s, %s)",
            ("2026-09-20", "여름", engine.fingerprint),
        )
    response = client.get("/api/state")
    assert response.status_code == 200
    state = response.json()
    assert state["puzzle_date"] == "2026-09-19"
    assert state["yesterday_answer"] is None
    assert state["user"] is None and state["game"] is None
    assert all(word not in response.text for word in ("바다", "사과", "여름"))
    assert scalar("SELECT count(*) FROM puzzles") == 3
    assert scalar("SELECT count(*) FROM users") == 0
    assert scalar("SELECT count(*) FROM games") == 0


def test_yesterday_answer_uses_server_date_even_for_stale_or_future_requests(runtime):
    client, _, engine = runtime
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO puzzles (puzzle_date, answer, model_fingerprint) VALUES (%s, %s, %s)",
            ("2026-09-17", "산책", engine.fingerprint),
        )
        conn.execute(
            "INSERT INTO puzzles (puzzle_date, answer, model_fingerprint) VALUES (%s, %s, %s)",
            ("2026-09-18", "바다", engine.fingerprint),
        )
    # 미래 날짜를 요청해 오늘 정답을 '어제 정답'으로 알아내는 것도 차단합니다.
    for requested_day in ("2026-09-17", "2026-09-19", "2026-09-20"):
        response = client.get("/api/state", params={"puzzle_date": requested_day})
        assert response.status_code == 200
        state = response.json()
        assert state["puzzle_date"] == "2026-09-19"
        assert state["yesterday_answer"] == "바다"
        assert state["date_changed"] is (requested_day != state["puzzle_date"])
        assert "answer" not in state
        assert "사과" not in response.text and "산책" not in response.text
    # 과거 정답 조회는 현재 모델 준비 여부와 무관합니다.
    engine.ready = False
    engine.error = "TEST ONLY: model missing"
    state = client.get("/api/state").json()
    assert state["model"]["ready"] is False
    assert state["yesterday_answer"] == "바다"
    assert scalar("SELECT count(*) FROM users") == 0
    assert scalar("SELECT count(*) FROM games") == 0


def test_yesterday_answer_changes_at_korean_midnight(runtime):
    client, clock, engine = runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    with db.connect() as conn:
        conn.execute(
            "INSERT INTO puzzles (puzzle_date, answer, model_fingerprint) VALUES (%s, %s, %s)",
            ("2026-09-18", "바다", engine.fingerprint),
        )
    before = client.get("/api/state")
    assert before.json()["puzzle_date"] == "2026-09-19"
    assert before.json()["yesterday_answer"] == "바다"
    assert "사과" not in before.text
    # 다음 날 후보를 바꿔도 어제의 저장된 정답만 공개해야 합니다.
    game.ANSWER_PATH.write_text("여름\n", encoding="utf-8")
    clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
    after = client.get("/api/state", params={"puzzle_date": "2026-09-19"})
    assert after.status_code == 200
    assert after.json()["puzzle_date"] == "2026-09-20"
    assert after.json()["yesterday_answer"] == "사과"
    assert after.json()["date_changed"] is True
    assert after.json()["next_reset_at"] == "2026-09-20T15:00:00+00:00"
    assert "여름" not in after.text and "바다" not in after.text
    assert scalar("SELECT count(*) FROM users") == 0
    assert scalar("SELECT count(*) FROM games") == 0


def test_yesterday_answer_refreshes_if_rank_preparation_crosses_midnight(runtime, monkeypatch):
    client, clock, engine = runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    original_rankings = engine.rankings

    def rankings_after_midnight(answer):
        result = original_rankings(answer)
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        game.ANSWER_PATH.write_text("여름\n", encoding="utf-8")
        return result

    monkeypatch.setattr(engine, "rankings", rankings_after_midnight)
    response = client.get("/api/state", params={"puzzle_date": "2026-09-19"})
    assert response.status_code == 200
    state = response.json()
    assert state["puzzle_date"] == "2026-09-20"
    assert state["yesterday_answer"] == "사과"
    assert state["date_changed"] is True
    assert "여름" not in response.text
    assert scalar("SELECT count(*) FROM puzzles") == 2
    assert scalar("SELECT count(*) FROM users") == 0
    assert scalar("SELECT count(*) FROM games") == 0
