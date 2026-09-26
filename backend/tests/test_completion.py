"""정답 후 개인 통계와 상위 단어의 접근 권한을 실제 PostgreSQL에서 검사합니다.

점수는 규칙용 모형/합성 벡터입니다. 운영 모델 품질 검사와 구분합니다.
runtime이 만든 임시 스키마만 사용하며 기존 게임 기록은 수정하지 않습니다.
"""
from datetime import UTC, date, datetime
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from test_rules import begin, runtime, scalar, submit
from test_word_ranks import index_for_rules
from app import game, main
from app.similarity import ModelUnavailableError


def related(client, day):
    return client.get("/api/related-words", params={"puzzle_date": day})


def on_day(clock, day):
    clock["now"] = datetime.combine(date.fromisoformat(day), datetime.min.time(), UTC)


def test_unregistered_and_unfinished_players_cannot_query_related_words(runtime, monkeypatch):
    client, _, engine = runtime
    day = client.get("/api/state").json()["puzzle_date"]
    assert client.get("/api/state").json()["player_stats"] is None
    assert related(client, day).status_code == 401

    registered = client.post("/api/users", json={"nickname": "미시작검사"}).json()
    assert registered["player_stats"] is None
    assert related(client, day).status_code == 403
    client.post("/api/start", json={"puzzle_date": day})
    with TestClient(main.app) as completed:
        begin(completed, "다른완료사용자")
        submit(completed, day, "사과")
        assert client.get("/api/state").json()["player_stats"] is None
        rankings = Mock(side_effect=AssertionError("권한 확인 전에 단어를 조회하면 안 됩니다."))
        monkeypatch.setattr(engine, "rankings", rankings)
        response = related(client, day)
        assert response.status_code == 403
        assert response.json()["detail"]["code"] == "game_not_completed"
        assert "사과" not in response.text
        rankings.assert_not_called()


def test_related_words_use_same_scores_ranks_and_references_and_do_not_expose_answer(runtime, monkeypatch):
    client, _, engine = runtime
    day, _ = begin(client)
    submit(client, day, "사과")
    index = index_for_rules()
    index.words[0] = "사과"
    index.positions = {word: position for position, word in enumerate(index.words)}
    index.vectors[2] = index.vectors[1]
    index.vectors[1001] = index.vectors[1000]
    monkeypatch.setattr(engine, "rankings", index.rankings)

    response = related(client, day)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert set(response.json()) == {"puzzle_date", "words"}
    assert response.json()["puzzle_date"] == day
    words = response.json()["words"]
    assert len(words) == 1000
    assert len({row["word"] for row in words}) == 1000
    assert "사과" not in response.text
    assert [row["rank"] for row in words[:3]] == [1, 1, 3]
    assert [row["word"] for row in words[:3]] == ["검사1", "검사2", "검사3"]
    assert words[-1]["rank"] == 1000
    assert words[-1]["word"] == "검사1000"
    assert all(a["similarity"] >= b["similarity"] for a, b in zip(words, words[1:]))
    reference = client.get("/api/state").json()["similarity_reference"]
    for place in (1, 10, 1000):
        assert words[place - 1]["similarity"] == reference[f"top{place}"]
    # 단어 목록은 별도 완료 API에만 들어가고 일반 상태 응답에는 포함되지 않습니다.
    assert "검사1" not in client.get("/api/state").text
    with TestClient(main.app, cookies=dict(client.cookies)) as reconnect:
        assert related(reconnect, day).json() == response.json()
    assert scalar("SELECT count(*) FROM guesses") == 1


@pytest.mark.parametrize("requested_day", ["2026-09-18", "2026-09-20"])
def test_related_words_reject_other_dates_before_model_lookup(runtime, monkeypatch, requested_day):
    client, _, engine = runtime
    day, _ = begin(client)
    submit(client, day, "사과")
    rankings = Mock(side_effect=AssertionError("다른 날짜의 모델을 조회하면 안 됩니다."))
    monkeypatch.setattr(engine, "rankings", rankings)
    response = related(client, requested_day)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    rankings.assert_not_called()


def test_related_words_validate_date_and_session(runtime):
    client, _, _ = runtime
    day, started = begin(client)
    submit(client, day, "사과")
    assert related(client, "invalid-date").status_code == 422
    assert client.get("/api/related-words").status_code == 422
    with TestClient(main.app) as visitor:
        visitor.cookies.set("ganmantle_session", started["user"]["id"])
        assert related(visitor, day).status_code == 401


@pytest.mark.parametrize("fault", ["unready", "fingerprint", "rankings"])
def test_related_words_model_failures_never_return_partial_words(runtime, monkeypatch, fault):
    client, _, engine = runtime
    day, _ = begin(client)
    submit(client, day, "사과")
    if fault == "unready":
        engine.ready = False
    elif fault == "fingerprint":
        engine.fingerprint = "TEST ONLY: changed fingerprint"
    else:
        monkeypatch.setattr(engine, "rankings", Mock(side_effect=ModelUnavailableError("사과 비공개 오류")))
    response = related(client, day)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_unavailable"
    assert "words" not in response.json()
    assert "사과" not in response.text


@pytest.mark.parametrize("fails", [False, True])
def test_related_words_crossing_midnight_are_not_returned(runtime, monkeypatch, fails):
    client, clock, engine = runtime
    day, _ = begin(client)
    submit(client, day, "사과")
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)

    def cross_midnight(answer):
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        if fails:
            raise ModelUnavailableError("TEST ONLY: midnight failure")
        return {"words": [{"word": "비공개검사", "similarity": 50, "rank": 1}]}

    monkeypatch.setattr(engine, "rankings", cross_midnight)
    response = related(client, day)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    assert "비공개검사" not in response.text


def test_player_stats_use_own_saved_history_and_duplicates_do_not_count(runtime):
    client, clock, _ = runtime
    on_day(clock, "2026-09-16")
    day, _ = begin(client)
    submit(client, day, "산책")
    submit(client, day, "사과")
    on_day(clock, "2026-09-17")
    day, _ = begin(client)
    submit(client, day, "바다")  # 자정 이후 미완료로 마감됩니다.
    on_day(clock, "2026-09-18")
    day, _ = begin(client)
    submit(client, day, "사과")
    on_day(clock, "2026-09-19")
    day, started = begin(client)
    assert started["player_stats"] is None
    submit(client, day, "산책")
    submit(client, day, "산책")
    completed = submit(client, day, "사과").json()
    expected = {
        "first_played_date": "2026-09-16", "games_played": 4,
        "games_completed": 3, "current_streak": 2,
        "games_incomplete": 1, "total_guesses": 6,
    }
    assert completed["player_stats"] == expected
    duplicate = submit(client, day, "산책").json()
    assert duplicate["duplicate"] is True
    assert duplicate["player_stats"] == expected
    assert duplicate["game"]["attempts"] == 2
    with TestClient(main.app) as other:
        begin(other, "통계분리검사")
        assert other.get("/api/state").json()["player_stats"] is None
        submit(other, day, "사과")
        assert other.get("/api/state").json()["player_stats"]["games_played"] == 1
        assert client.get("/api/state").json()["player_stats"] == expected
    with TestClient(main.app, cookies=dict(client.cookies)) as reconnect:
        assert reconnect.get("/api/state").json()["player_stats"] == expected
        renamed = reconnect.post("/api/users", json={"nickname": "기록유지검사"}).json()
        assert renamed["player_stats"] == expected
    with TestClient(main.app) as visitor:
        assert visitor.get("/api/state").json()["player_stats"] is None


@pytest.mark.parametrize("days,streak", [
    (["2025-12-31", "2026-01-01"], 2),
    (["2024-02-28", "2024-02-29", "2024-03-01"], 3),
    (["2026-09-16", "2026-09-18", "2026-09-19"], 2),
])
def test_streak_uses_consecutive_korean_calendar_dates(runtime, days, streak):
    client, clock, _ = runtime
    for day in days:
        on_day(clock, day)
        begin(client)
        state = submit(client, day, "사과").json()
    assert state["player_stats"]["current_streak"] == streak
    assert state["player_stats"]["first_played_date"] == days[0]
    assert state["player_stats"]["games_played"] == len(days)
    assert state["player_stats"]["games_incomplete"] == 0


def test_first_game_completion_stats_and_next_day_are_not_carried_over(runtime):
    client, clock, _ = runtime
    day, _ = begin(client)
    completed = submit(client, day, "사과").json()
    assert completed["player_stats"] == {
        "first_played_date": day, "games_played": 1, "games_completed": 1,
        "current_streak": 1, "games_incomplete": 0, "total_guesses": 1,
    }
    clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
    state = client.get("/api/state").json()
    assert state["game"] is None
    assert state["player_stats"] is None
    assert related(client, day).status_code == 409
    assert related(client, "2026-09-20").status_code == 403


def test_state_refreshes_if_statistics_lookup_crosses_midnight(runtime, monkeypatch):
    client, clock, _ = runtime
    day, _ = begin(client)
    submit(client, day, "사과")
    original = game.player_stats

    def cross_midnight(conn, user_id, expected):
        result = original(conn, user_id, expected)
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        return result

    monkeypatch.setattr(game, "player_stats", cross_midnight)
    response = client.get("/api/state", params={"puzzle_date": day}).json()
    assert response["puzzle_date"] == "2026-09-20"
    assert response["date_changed"] is True
    assert response["game"] is None
    assert response["player_stats"] is None
