"""2단계 전체 랭킹: 실제 PostgreSQL과 익명 세션으로 명세 3.5절을 검증합니다.

점수는 기존 규칙 테스트의 모형을 사용합니다. 실제 모델 품질 검사는 별도입니다.
각 검사는 runtime이 만든 임시 스키마만 사용하고 종료 후 제거합니다.
"""

from datetime import UTC, datetime, timedelta

from fastapi.testclient import TestClient

from test_rules import runtime, begin, submit, scalar
from app import db, main


def ranking(client):
    response = client.get("/api/state")
    assert response.status_code == 200
    return response.json()["ranking"]


def stored_records():
    """조회가 게임 원본이나 추측 기록을 변경하지 않았는지 비교합니다."""
    with db.connect() as conn:
        return {
            "users": conn.execute("SELECT * FROM users ORDER BY id").fetchall(),
            "puzzles": conn.execute("SELECT * FROM puzzles ORDER BY puzzle_date").fetchall(),
            "games": conn.execute("SELECT * FROM games ORDER BY id").fetchall(),
            "guesses": conn.execute("SELECT * FROM guesses ORDER BY id").fetchall(),
        }


def test_attempts_then_raw_time_and_competition_ties(runtime):
    client, clock, _ = runtime
    started = clock["now"]
    day, _ = begin(client, "SlowOne")
    with TestClient(main.app) as alpha, TestClient(main.app) as beta, TestClient(main.app) as quick:
        begin(alpha, "TieAlpha")
        begin(beta, "TieBeta")
        begin(quick, "QuickTwo")
        clock["now"] = started + timedelta(milliseconds=500)
        assert submit(quick, day, "산책").status_code == 200
        clock["now"] = started + timedelta(seconds=1)
        assert submit(quick, day, "사과").status_code == 200
        clock["now"] = started + timedelta(seconds=10, microseconds=100)
        assert submit(alpha, day, "사과").status_code == 200
        assert submit(beta, day, "사과").status_code == 200
        clock["now"] = started + timedelta(seconds=10, microseconds=900)
        assert submit(client, day, "사과").status_code == 200

        result = ranking(client)
        rows = result["completed"]
        assert {row["nickname"] for row in rows[:2]} == {"TieAlpha", "TieBeta"}
        assert [row["nickname"] for row in rows[2:]] == ["SlowOne", "QuickTwo"]
        # 화면용 밀리초는 같아도 원래 800마이크로초 차이를 순위에 반영합니다.
        assert [row["elapsed_ms"] for row in rows] == [10000, 10000, 10000, 1000]
        assert [row["attempts"] for row in rows] == [1, 1, 1, 2]
        assert [row["rank"] for row in rows] == [1, 1, 3, 4]
        assert [row["nickname"] for row in rows if row["is_me"]] == ["SlowOne"]
        assert result["playing"] == []


def test_separate_playing_omit_unstarted_and_expose_only_public_fields(runtime):
    client, clock, _ = runtime
    assert ranking(client) == {"completed": [], "playing": []}
    day, _ = begin(client, "완료사용자")
    with (
        TestClient(main.app) as playing,
        TestClient(main.app) as unstarted,
        TestClient(main.app) as visitor,
    ):
        _, started = begin(playing, "진행사용자")
        assert started["ranking"]["playing"][-1]["rank"] is None
        assert all(row["best_similarity"] is None for row in started["ranking"]["playing"])
        assert unstarted.post("/api/users", json={"nickname": "시작안함"}).status_code == 200
        assert submit(playing, day, "모니터").status_code == 200
        clock["now"] += timedelta(seconds=30)
        assert submit(client, day, "사과").status_code == 200

        response = visitor.get("/api/state")
        state = response.json()
        result = state["ranking"]
        assert state["user"] is None and state["game"] is None
        assert [row["nickname"] for row in result["completed"]] == ["완료사용자"]
        assert [row["nickname"] for row in result["playing"]] == ["진행사용자"]
        assert result["playing"][0]["attempts"] == 1
        assert result["playing"][0]["elapsed_ms"] is None
        assert result["playing"][0]["rank"] is None
        assert result["playing"][0]["best_similarity"] == 23.4567
        assert result["completed"][0]["best_similarity"] == 100.0
        allowed = {
            "user_id",
            "nickname",
            "attempts",
            "elapsed_ms",
            "rank",
            "is_me",
            "best_similarity",
            "best_similarity_rank",
        }
        for row in result["completed"] + result["playing"]:
            assert set(row) == allowed
            assert row["is_me"] is False
        for private_value in (
            "모니터",
            "사과",
            client.cookies["ganmantle_session"],
            playing.cookies["ganmantle_session"],
        ):
            assert private_value not in response.text
        assert "session_hash" not in response.text
        assert "answer" not in state
        assert state["yesterday_answer"] is None


def test_reconnect_application_restart_and_nickname_change_preserve_ranking(runtime):
    client, clock, _ = runtime
    day, original = begin(client, "원래닉네임")
    with TestClient(main.app) as other:
        begin(other, "다른사용자")
        clock["now"] += timedelta(seconds=7, microseconds=321)
        assert submit(client, day, "사과").status_code == 200
        previous = ranking(client)
        cookies = dict(client.cookies)

        # 새 클라이언트가 앱 시작 절차(migrate/만료 정리)를 다시 실행합니다.
        # 실제 OS 프로세스 재시작 검사는 별도의 실행 확인에서 구분합니다.
        with TestClient(main.app, cookies=cookies) as reconnect:
            state = reconnect.get("/api/state").json()
            assert state["user"] == original["user"]
            assert state["ranking"] == previous
            assert state["game"]["elapsed_ms"] == 7000
            renamed = reconnect.post("/api/users", json={"nickname": "바뀐닉네임"})
            assert renamed.status_code == 200
            changed = renamed.json()["ranking"]["completed"][0]
            assert changed == {**previous["completed"][0], "nickname": "바뀐닉네임"}
            assert changed["user_id"] == original["user"]["id"]
            assert dict(reconnect.cookies) == cookies

        other_rows = ranking(other)
        assert other_rows["completed"][0]["is_me"] is False
        assert other_rows["playing"][0]["is_me"] is True
        assert other_rows["completed"][0]["nickname"] == "바뀐닉네임"
        assert scalar("SELECT count(*) FROM games") == 2
        assert scalar("SELECT count(*) FROM users") == 2


def test_repeated_ranking_reads_do_not_change_saved_game_records(runtime):
    client, clock, _ = runtime
    day, _ = begin(client, "조회검증")
    with TestClient(main.app) as other, TestClient(main.app) as visitor:
        begin(other, "완료검증")
        assert submit(client, day, "산책").status_code == 200
        clock["now"] += timedelta(seconds=3)
        assert submit(other, day, "사과").status_code == 200
        previous = ranking(client)
        records = stored_records()
        clock["now"] += timedelta(minutes=40)
        for _ in range(3):
            assert ranking(client) == previous
            assert ranking(visitor)["completed"][0]["elapsed_ms"] == 3000
        assert stored_records() == records
        assert client.get("/api/state").json()["game"]["elapsed_ms"] == 2403000


def test_midnight_clears_todays_ranking_and_preserves_history(runtime):
    client, clock, _ = runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    yesterday, original = begin(client, "자정진행")
    with TestClient(main.app) as solved, TestClient(main.app) as unstarted:
        begin(solved, "자정완료")
        assert unstarted.post("/api/users", json={"nickname": "자정미시작"}).status_code == 200
        clock["now"] += timedelta(microseconds=500)
        assert submit(solved, yesterday, "사과").status_code == 200
        assert len(ranking(client)["completed"]) == 1
        assert len(ranking(client)["playing"]) == 1
        with db.connect() as conn:
            completed = conn.execute("SELECT * FROM games WHERE status = 'completed'").fetchone()
            guesses = conn.execute("SELECT * FROM guesses ORDER BY id").fetchall()

        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        state = client.get("/api/state", params={"puzzle_date": yesterday}).json()
        assert state["date_changed"] is True
        assert state["puzzle_date"] == "2026-09-20"
        assert state["game"] is None
        assert state["ranking"] == {"completed": [], "playing": []}
        assert ranking(solved) == {"completed": [], "playing": []}
        assert submit(client, yesterday, "사과").status_code == 409
        assert scalar("SELECT count(*) FROM games WHERE status = 'incomplete'") == 1
        assert scalar("SELECT count(*) FROM games") == 2
        with db.connect() as conn:
            assert (
                conn.execute("SELECT * FROM games WHERE status = 'completed'").fetchone()
                == completed
            )
            assert conn.execute("SELECT * FROM guesses ORDER BY id").fetchall() == guesses

        fresh = client.post("/api/start", json={"puzzle_date": state["puzzle_date"]}).json()
        assert fresh["ranking"]["completed"] == []
        assert fresh["ranking"]["playing"] == [
            {
                "user_id": original["user"]["id"],
                "nickname": "자정진행",
                "attempts": 0,
                "elapsed_ms": None,
                "rank": None,
                "is_me": True,
                "best_similarity": None,
                "best_similarity_rank": None,
            }
        ]
        assert scalar("SELECT count(*) FROM games") == 3


def test_duplicate_after_completion_never_changes_rank_attempts_or_finish_time(runtime):
    client, clock, _ = runtime
    day, _ = begin(client, "중복검증")
    with TestClient(main.app) as other:
        begin(other, "비교사용자")
        assert submit(client, day, "산책").status_code == 200
        clock["now"] += timedelta(seconds=8)
        assert submit(other, day, "사과").status_code == 200
        clock["now"] += timedelta(seconds=2)
        finished = submit(client, day, "사과").json()
        assert finished["ranking"]["completed"][1]["rank"] == 2
        assert finished["game"]["elapsed_ms"] == 10000
        assert finished["ranking"]["completed"][1]["best_similarity"] == 100.0

        clock["now"] += timedelta(hours=1)
        duplicate = submit(client, day, "산책").json()
        assert duplicate["duplicate"] is True
        assert duplicate["ranking"] == finished["ranking"]
        assert duplicate["ranking"]["completed"][1]["best_similarity"] == 100.0
        assert duplicate["game"]["attempts"] == 2
        assert duplicate["game"]["elapsed_ms"] == 10000
        assert duplicate["game"]["completed_at"] == finished["game"]["completed_at"]
        assert duplicate["game"]["guesses"][0]["word"] == "산책"
        assert scalar("SELECT count(*) FROM guesses") == 3


def test_best_similarity_is_raw_max_for_each_game_before_and_after_completion(runtime, monkeypatch):
    client, _, engine = runtime
    day, original = begin(client, "최고점검증")
    scores = {"모니터": -12.345678, "키보드": 73.123456789, "걷다": 21.654321, "사과": 66.54321}
    # 집계 검사용 모형입니다. 완료한 게임도 점수를 100으로 바꾸지 않고 원본 MAX를 반환해야 합니다.
    monkeypatch.setattr(engine, "score", lambda word, answer: scores[word])
    with TestClient(main.app) as empty:
        _, untouched = begin(empty, "미입력검증")
        for word in ("모니터", "키보드", "걷다"):
            response = submit(client, day, word)
            assert response.status_code == 200
            result = response.json()
            rows = result["ranking"]["playing"]
            assert len(rows) == 2
            own = next(row for row in rows if row["user_id"] == original["user"]["id"])
            other = next(row for row in rows if row["user_id"] == untouched["user"]["id"])
            expected = max(item["similarity"] for item in result["game"]["guesses"])
            assert own["best_similarity"] == expected
            assert other["best_similarity"] is None
        assert own["best_similarity"] == 73.123456789
        previous_ranking = result["ranking"]
        repeated = submit(client, day, "모니터").json()
        assert repeated["duplicate"] is True
        assert repeated["game"]["guesses"][0]["similarity"] == -12.345678
        assert repeated["ranking"] == previous_ranking
        finished = submit(client, day, "사과").json()
        assert finished["game"]["status"] == "completed"
        assert finished["game"]["guesses"][0]["similarity"] == 66.54321
        assert len(finished["ranking"]["completed"]) == 1
        assert len(finished["ranking"]["playing"]) == 1
        assert finished["ranking"]["completed"][0]["best_similarity"] == 73.123456789
        assert finished["ranking"]["playing"][0]["best_similarity"] is None
