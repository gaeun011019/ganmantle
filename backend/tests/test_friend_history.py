"""완료한 사람의 친구 기록 조회 권한과 최초 시도 순서를 검사합니다.

실제 PostgreSQL의 임시 스키마와 규칙용 모델/합성 벡터를 사용합니다.
운영 DB나 실제 모델 품질 검사를 대신하지 않습니다.
"""
from datetime import UTC, datetime
from unittest.mock import Mock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from test_rules import begin, runtime, scalar, submit
from test_word_ranks import index_for_rules
from app import game, main
from app.similarity import ModelUnavailableError
from app.word_ranks import cosine_scores, rank_for_score


def history(client, user_id, day):
    return client.get(f"/api/ranking/{user_id}/guesses", params={"puzzle_date": day})


def complete(client, nickname="완료조회자"):
    day, initial = begin(client, nickname)
    assert submit(client, day, "사과").status_code == 200
    return day, initial["user"]["id"]


@pytest.mark.parametrize("stage", ["anonymous", "registered", "playing"])
def test_history_requires_the_viewers_own_completed_game(runtime, monkeypatch, stage):
    client, _, engine = runtime
    with TestClient(main.app) as target:
        day, target_id = complete(target, "기록소유자")
        if stage != "anonymous":
            client.post("/api/users", json={"nickname": "미완료조회자"})
        if stage == "playing":
            client.post("/api/start", json={"puzzle_date": day})
        rankings = Mock(side_effect=AssertionError("완료 권한 확인 전 모델 조회 금지"))
        monkeypatch.setattr(engine, "rankings", rankings)
        # 존재하는 친구와 없는 친구 모두 같은 권한 오류를 반환합니다.
        for target_user_id in (target_id, uuid4()):
            response = history(client, target_user_id, day)
            assert response.status_code == (401 if stage == "anonymous" else 403)
            assert response.json()["detail"]["code"] == (
                "nickname_required" if stage == "anonymous" else "game_not_completed"
            )
            assert "사과" not in response.text
            assert "기록소유자" not in response.text
        rankings.assert_not_called()


@pytest.mark.parametrize("saved", [None, {"status": "playing", "answer": "비공개"}])
def test_unfinished_viewer_is_checked_before_target_query(runtime, saved):
    _, clock, engine = runtime
    conn = Mock()
    conn.execute.return_value.fetchone.return_value = saved
    with pytest.raises(game.GameError) as caught:
        game.friend_history(conn, {"id": uuid4()}, uuid4(), game.puzzle_date(clock["now"]), engine)
    assert caught.value.status == 403
    assert conn.execute.call_count == 1
    assert "g.user_id" in conn.execute.call_args.args[0]


def test_history_preserves_first_attempt_order_without_duplicates_and_reconnects(runtime):
    client, _, _ = runtime
    day, viewer_id = complete(client)
    with TestClient(main.app) as friend, TestClient(main.app) as another:
        _, first = begin(friend, "친구기록")
        _, unrelated = begin(another, "다른친구")
        submit(another, day, "키보드")
        target_id = first["user"]["id"]
        empty = history(client, target_id, day).json()
        assert empty["status"] == "playing" and empty["attempts"] == 0
        assert empty["guesses"] == []
        for word in ("산책", "연필", "바다", "산책"):
            assert submit(friend, day, word).status_code == 200

        playing = history(client, target_id, day)
        assert playing.status_code == 200
        assert playing.headers["cache-control"] == "no-store"
        assert playing.json()["status"] == "playing"
        assert playing.json()["attempts"] == 3
        assert [row["word"] for row in playing.json()["guesses"]] == ["산책", "연필", "바다"]
        assert [row["attempt"] for row in playing.json()["guesses"]] == [1, 2, 3]
        # 현재 화면의 최근 입력/유사도 정렬과 달리 처음 제출했던 순서입니다.
        own_order = friend.get("/api/state").json()["game"]["guesses"]
        assert [row["word"] for row in own_order] == ["산책", "바다", "연필"]

        solved = submit(friend, day, "사과").json()
        assert submit(friend, day, "산책").json()["duplicate"] is True
        response = history(client, target_id, day)
        payload = response.json()
        assert set(payload) == {"puzzle_date", "user", "status", "attempts", "guesses"}
        assert payload["puzzle_date"] == day
        assert payload["user"] == first["user"]
        assert payload["status"] == "completed" and payload["attempts"] == 4
        assert [row["attempt"] for row in payload["guesses"]] == [1, 2, 3, 4]
        assert payload["guesses"] == sorted(solved["game"]["guesses"], key=lambda row: row["attempt"])
        assert [row["is_correct"] for row in payload["guesses"]] == [False, False, False, True]
        assert payload["guesses"][-1]["similarity_rank"] == 0
        assert all(set(row) == {"word", "similarity", "similarity_rank", "attempt", "is_correct"}
                   for row in payload["guesses"])
        assert "키보드" not in response.text
        assert scalar("SELECT count(*) FROM guesses") == 6
        with TestClient(main.app, cookies=dict(client.cookies)) as reconnect:
            assert history(reconnect, target_id, day).json() == payload
        assert history(client, viewer_id, day).json()["attempts"] == 1
        assert history(client, unrelated["user"]["id"], day).json()["guesses"][0]["word"] == "키보드"
        renamed = friend.post("/api/users", json={"nickname": "친구새닉네임"}).json()
        assert history(client, target_id, day).json()["user"] == renamed["user"]
        # 일반 상태의 랭킹은 완료 여부와 무관하게 추측 단어를 포함하지 않습니다.
        rankings = client.get("/api/state").json()["ranking"]
        assert all("word" not in key and "guesses" not in key
                   for group in rankings.values() for row in group for key in row)


@pytest.mark.parametrize("target_kind", ["absent", "not_started", "yesterday_only"])
def test_target_must_have_a_game_on_the_requested_current_day(runtime, target_kind):
    client, clock, _ = runtime
    with TestClient(main.app) as friend:
        target_id = str(uuid4())
        if target_kind == "not_started":
            target_id = friend.post("/api/users", json={"nickname": "미시작친구"}).json()["user"]["id"]
        elif target_kind == "yesterday_only":
            clock["now"] = datetime(2026, 9, 18, 2, 0, tzinfo=UTC)
            _, target_id = complete(friend, "전날참가친구")
            clock["now"] = datetime(2026, 9, 19, 2, 0, tzinfo=UTC)
        day, _ = complete(client)
        response = history(client, target_id, day)
        assert response.status_code == 404
        assert response.json()["detail"]["code"] == "game_not_found"
        assert "guesses" not in response.json()


@pytest.mark.parametrize("requested_day", ["2026-09-18", "2026-09-20"])
def test_history_rejects_other_dates_before_target_or_model_lookup(runtime, monkeypatch, requested_day):
    client, _, engine = runtime
    _, target_id = complete(client)
    rankings = Mock(side_effect=AssertionError("다른 날짜 모델 조회 금지"))
    monkeypatch.setattr(engine, "rankings", rankings)
    response = history(client, target_id, requested_day)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    rankings.assert_not_called()
    conn = Mock()
    with pytest.raises(game.GameError):
        game.friend_history(conn, {"id": uuid4()}, uuid4(), datetime.fromisoformat(requested_day).date(), engine)
    conn.execute.assert_not_called()


def test_history_validates_uuid_date_and_session(runtime):
    client, _, _ = runtime
    day, target_id = complete(client)
    assert history(client, "not-a-uuid", day).status_code == 422
    assert history(client, target_id, "invalid-date").status_code == 422
    assert client.get(f"/api/ranking/{target_id}/guesses").status_code == 422
    with TestClient(main.app) as visitor:
        visitor.cookies.set("ganmantle_session", target_id)
        assert history(visitor, target_id, day).status_code == 401


@pytest.mark.parametrize("fault", ["unready", "fingerprint", "rankings"])
def test_history_never_mixes_existing_scores_with_an_unavailable_or_changed_model(runtime, monkeypatch, fault):
    client, _, engine = runtime
    day, target_id = complete(client)
    if fault == "unready":
        engine.ready = False
    elif fault == "fingerprint":
        engine.fingerprint = "TEST ONLY: changed fingerprint"
    else:
        monkeypatch.setattr(engine, "rankings", Mock(side_effect=ModelUnavailableError("비공개 사과")))
    response = history(client, target_id, day)
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "model_unavailable"
    assert "guesses" not in response.json() and "사과" not in response.text


def test_history_matches_current_index_scores_and_oov_tie_ranks(runtime, monkeypatch):
    client, _, engine = runtime
    index = index_for_rules()
    index.words[:4] = ["사과", "산책", "바다", "연필"]
    index.positions = {word: position for position, word in enumerate(index.words)}
    index.vectors[2] = index.vectors[1]
    monkeypatch.setattr(engine, "rankings", index.rankings)
    monkeypatch.setattr(engine, "supports_oov", True, raising=False)

    def score(word, answer):
        if word == answer:
            return 100.0
        vector = index.vector("산책" if word == "미등록검사용말" else word)
        return float(cosine_scores(vector[None, :], index.vector(answer))[0])

    monkeypatch.setattr(engine, "score", score)
    day, _ = complete(client)
    with TestClient(main.app) as friend:
        _, initial = begin(friend, "모델일관성친구")
        for word in ("바다", "산책", "미등록검사용말", "연필", "사과"):
            saved = submit(friend, day, word)
            assert saved.status_code == 200
        response = history(client, initial["user"]["id"], day)
        assert response.status_code == 200
        rows = response.json()["guesses"]
        indexed = index.rankings("사과")
        for row in rows:
            assert row["similarity"] == score(row["word"], "사과")
            assert row["similarity_rank"] == rank_for_score(indexed, row["word"], row["similarity"])
        assert [row["similarity_rank"] for row in rows[:3]] == [1, 1, 1]
        assert rows[0]["similarity"] == client.get("/api/state").json()["similarity_reference"]["top1"]
        assert rows == sorted(saved.json()["game"]["guesses"], key=lambda row: row["attempt"])


@pytest.mark.parametrize("fails", [False, True])
def test_history_calculation_crossing_midnight_never_returns_old_words(runtime, monkeypatch, fails):
    client, clock, engine = runtime
    day, target_id = complete(client)
    original = engine.rankings

    def cross_midnight(answer):
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        if fails:
            raise ModelUnavailableError("TEST ONLY: midnight failure")
        return original(answer)

    monkeypatch.setattr(engine, "rankings", cross_midnight)
    response = history(client, target_id, day)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    assert "사과" not in response.text


def test_history_checks_date_after_mapping_guess_ranks(runtime, monkeypatch):
    client, clock, _ = runtime
    day, target_id = complete(client)
    original = game.rank_for_score

    def cross_midnight(*args):
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        return original(*args)

    monkeypatch.setattr(game, "rank_for_score", cross_midnight)
    response = history(client, target_id, day)
    assert response.status_code == 409
    assert "사과" not in response.text


def test_yesterdays_completion_cannot_unlock_todays_friends(runtime):
    client, clock, _ = runtime
    day, target_id = complete(client)
    clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
    with TestClient(main.app) as friend:
        today, friend_id = complete(friend, "새날친구")
        assert history(client, target_id, day).status_code == 409
        assert history(client, friend_id, today).status_code == 403
        begin(client)
        assert history(client, friend_id, today).status_code == 403
        submit(client, today, "사과")
        assert history(client, friend_id, today).status_code == 200
