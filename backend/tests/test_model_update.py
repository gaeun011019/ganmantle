"""오늘 점수 전환의 원자성·기록 보존을 임시 PostgreSQL 스키마에서 확인합니다.

운영 모델 품질 검사가 아닌 규칙 검사입니다. 실제 사용자 DB는 조회하지 않으며,
TEST_DATABASE_URL이 없으면 기존 runtime fixture가 검사를 건너뜁니다.
"""

import copy
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from statistics import mean
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from psycopg.errors import CheckViolation

from test_rules import runtime, begin, submit, RuleTestEngine
from app import db, main

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from recalculate_scores import ScoreUpdateError, recalculate_scores


GLOBAL_ROOM = "00000000-0000-0000-0000-000000000001"
TABLES = (
    "users",
    "puzzles",
    "games",
    "guesses",
    "chat_rooms",
    "chat_members",
    "chat_invitations",
    "chat_messages",
    "schema_migrations",
)


class UpdateTestEngine(RuleTestEngine):
    """전환 전후 점수가 확실히 다른 테스트 전용 엔진입니다."""

    ready = True
    name = "TEST ONLY: score update fixture"
    error = None
    fingerprint = "test-rules-v2"
    scores = {"산책": -12.25, "바다": 72.125, "연필": 4.5, "사과": 100.0}

    def __init__(self):
        self.calls = []
        self.after_score = None

    def score(self, word, answer):
        self.calls.append((word, answer))
        result = self.scores[word]
        if self.after_score:
            self.after_score()
        return result


def stored_records():
    # 테이블명은 위의 고정 목록만 사용하고, 복합 키 테이블도 안정적으로 정렬합니다.
    with db.connect() as conn:
        return {
            table: conn.execute(f"SELECT * FROM {table} ORDER BY 1, 2").fetchall()
            for table in TABLES
        }


def preserved_fields(records, day):
    """오늘 점수·모델 지문·전환 시각만 비교에서 빼고 나머지 전부를 비교합니다."""
    result = copy.deepcopy(records)
    game_ids = {row["id"] for row in result["games"] if row["puzzle_date"] == day}
    for row in result["guesses"]:
        if row["game_id"] in game_ids:
            row.pop("similarity")
    for row in result["puzzles"]:
        if row["puzzle_date"] == day:
            row.pop("model_fingerprint")
            row.pop("scores_updated_at")
    return result


def today_guesses(records, day):
    game_ids = {row["id"] for row in records["games"] if row["puzzle_date"] == day}
    return [row for row in records["guesses"] if row["game_id"] in game_ids]


def ranking_without_scores(ranking):
    return {
        status: [
            {key: value for key, value in row.items() if key != "best_similarity"} for row in rows
        ]
        for status, rows in ranking.items()
    }


def update(engine, old_fingerprint, *, apply=True, target_date=None, now=None):
    with db.connect() as conn:
        return recalculate_scores(
            conn,
            engine,
            from_fingerprint=old_fingerprint,
            target_date=target_date,
            apply=apply,
            now=now,
        )


def assert_report_hides_private_data(report, records, cookie):
    encoded = json.dumps(report, ensure_ascii=False)
    private_values = {cookie}
    for table, field in (
        ("users", "nickname"),
        ("users", "session_hash"),
        ("puzzles", "answer"),
        ("guesses", "word"),
        ("chat_messages", "body"),
    ):
        private_values.update(row[field] for row in records[table])
    assert all(value not in encoded for value in private_values)


def assert_summary(summary, scores):
    assert summary["count"] == len(scores)
    if scores:
        assert summary["min"] == pytest.approx(min(scores))
        assert summary["max"] == pytest.approx(max(scores))
        assert summary["mean"] == pytest.approx(mean(scores))
    else:
        assert summary["min"] is None
        assert summary["max"] is None
        assert summary["mean"] is None


@pytest.fixture
def mixed_games(runtime):
    client, clock, old_engine = runtime
    current_time = clock["now"]
    clock["now"] = current_time - timedelta(days=1)
    yesterday, _ = begin(client, "전환진행사용자")
    # 과거에만 있는 단어는 새 엔진의 점수 사전에 없으므로 잘못 재계산하면 실패합니다.
    assert submit(client, yesterday, "여행").status_code == 200
    clock["now"] += timedelta(seconds=3)
    assert submit(client, yesterday, "사과").status_code == 200
    clock["now"] = current_time
    day_text, _ = begin(client, "전환진행사용자")
    day = date.fromisoformat(day_text)
    with (
        TestClient(main.app) as first,
        TestClient(main.app) as second,
        TestClient(main.app) as empty,
    ):
        _, first_state = begin(first, "전환완료먼저")
        _, second_state = begin(second, "전환완료나중")
        begin(empty, "전환무입력")
        assert submit(client, day_text, "산책").status_code == 200
        assert submit(client, day_text, "바다").status_code == 200
        assert submit(client, day_text, "산책").json()["duplicate"] is True
        clock["now"] += timedelta(seconds=12, microseconds=321)
        assert submit(first, day_text, "사과").status_code == 200
        assert submit(second, day_text, "연필").status_code == 200
        clock["now"] += timedelta(seconds=18)
        assert submit(second, day_text, "사과").status_code == 200

        room_response = client.post(
            "/api/chat/rooms",
            json={
                "name": "점수와 무관한 대화",
                "invitee_ids": [first_state["user"]["id"], second_state["user"]["id"]],
            },
        )
        assert room_response.status_code == 200, room_response.text
        room_id = room_response.json()["room"]["id"]
        assert (
            first.post(f"/api/chat/invitations/{room_id}", json={"accept": True}).status_code == 200
        )
        for room in (GLOBAL_ROOM, room_id):
            sent = client.post(
                f"/api/chat/rooms/{room}/messages",
                json={
                    "body": "점수 재계산 중에도 보존할 테스트 대화",
                    "client_id": str(uuid4()),
                },
            )
            assert sent.status_code == 200, sent.text
        yield client, clock, old_engine, day, first, second, empty


def test_apply_recalculates_all_today_scores_and_preserves_every_other_record(mixed_games):
    client, clock, old_engine, day, first, second, empty = mixed_games
    before_state = client.get("/api/state").json()
    before = stored_records()
    assert before_state["model"]["scores_updated_at"] is None
    new_engine = UpdateTestEngine()
    result = update(new_engine, old_engine.fingerprint)
    after = stored_records()

    assert result["status"] == "applied"
    assert_report_hides_private_data(result, before, client.cookies["ganmantle_session"])
    assert result["puzzle_date"] == day.isoformat()
    assert result["from_fingerprint"] == old_engine.fingerprint
    assert result["to_fingerprint"] == new_engine.fingerprint
    assert result["games_count"] == 4
    assert result["guesses_count"] == result["updated_count"] == 5
    assert datetime.fromisoformat(result["scores_updated_at"]) == clock["now"]
    assert preserved_fields(after, day) == preserved_fields(before, day)
    assert_summary(result["old_scores"], [row["similarity"] for row in today_guesses(before, day)])
    assert_summary(result["new_scores"], [row["similarity"] for row in today_guesses(after, day)])
    assert set(new_engine.calls) == {(word, "사과") for word in new_engine.scores}
    for row in today_guesses(after, day):
        assert row["similarity"] == new_engine.scores[row["word"]]
    puzzle = next(row for row in after["puzzles"] if row["puzzle_date"] == day)
    assert puzzle["model_fingerprint"] == new_engine.fingerprint
    assert puzzle["scores_updated_at"] == clock["now"]

    main.app.state.engine = new_engine
    state = client.get("/api/state").json()
    assert state["model"]["ready"] is True
    assert datetime.fromisoformat(state["model"]["scores_updated_at"]) == clock["now"]
    assert ranking_without_scores(state["ranking"]) == ranking_without_scores(
        before_state["ranking"]
    )
    assert state["game"]["started_at"] == before_state["game"]["started_at"]
    assert state["game"]["elapsed_ms"] == before_state["game"]["elapsed_ms"]
    assert state["game"]["attempts"] == before_state["game"]["attempts"]
    assert [row["word"] for row in state["game"]["guesses"]] == ["산책", "바다"]
    best = {
        row["nickname"]: row["best_similarity"]
        for rows in state["ranking"].values()
        for row in rows
    }
    assert best == {
        "전환진행사용자": 72.125,
        "전환완료먼저": 100.0,
        "전환완료나중": 100.0,
        "전환무입력": None,
    }
    assert first.get("/api/state").json()["game"]["status"] == "completed"
    assert second.get("/api/state").json()["game"]["status"] == "completed"
    assert empty.get("/api/state").json()["game"]["attempts"] == 0


def test_duplicate_returns_recalculated_score_and_old_engine_stays_blocked(runtime):
    client, clock, old_engine = runtime
    day, started = begin(client)
    assert submit(client, day, "산책").status_code == 200
    clock["now"] += timedelta(seconds=15)
    new_engine = UpdateTestEngine()
    update(new_engine, old_engine.fingerprint)
    assert client.get("/api/state").json()["model"]["ready"] is False
    rejected = submit(client, day, "바다")
    assert rejected.status_code == 503
    assert rejected.json()["detail"]["code"] == "model_unavailable"
    duplicate = submit(client, day, "산책").json()
    assert duplicate["duplicate"] is True
    assert duplicate["game"]["guesses"][0]["similarity"] == -12.25
    assert duplicate["game"]["attempts"] == 1
    assert duplicate["game"]["started_at"] == started["game"]["started_at"]
    assert duplicate["game"]["elapsed_ms"] == 15000

    main.app.state.engine = new_engine
    new_guess = submit(client, day, "바다")
    assert new_guess.status_code == 200
    assert new_guess.json()["game"]["guesses"][0]["similarity"] == 72.125
    assert new_guess.json()["game"]["attempts"] == 2
    solved = submit(client, day, "사과").json()
    assert solved["game"]["status"] == "completed"
    assert solved["game"]["elapsed_ms"] == 15000


def test_dry_run_reports_new_scores_but_changes_nothing(mixed_games):
    client, _, old_engine, day, *_ = mixed_games
    before = stored_records()
    result = update(UpdateTestEngine(), old_engine.fingerprint, apply=False)
    assert result["status"] == "dry_run"
    assert_report_hides_private_data(result, before, client.cookies["ganmantle_session"])
    assert result["games_count"] == 4
    assert result["guesses_count"] == 5
    assert result["updated_count"] == 0
    assert result["scores_updated_at"] is None
    assert_summary(result["old_scores"], [row["similarity"] for row in today_guesses(before, day)])
    assert_summary(
        result["new_scores"],
        [UpdateTestEngine.scores[row["word"]] for row in today_guesses(before, day)],
    )
    assert stored_records() == before


def test_repeating_applied_update_is_noop_even_with_original_from_fingerprint(runtime):
    client, clock, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    new_engine = UpdateTestEngine()
    first = update(new_engine, old_engine.fingerprint)
    before = stored_records()
    new_engine.calls.clear()
    clock["now"] += timedelta(minutes=1)
    repeated = update(new_engine, old_engine.fingerprint)
    assert repeated["status"] == "already_current"
    assert repeated["updated_count"] == 0
    assert repeated["scores_updated_at"] == first["scores_updated_at"]
    assert new_engine.calls == []
    assert stored_records() == before


def test_already_current_without_previous_conversion_does_not_stamp_or_infer(runtime):
    client, _, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    new_engine = UpdateTestEngine()
    new_engine.fingerprint = old_engine.fingerprint
    before = stored_records()
    result = update(new_engine, "older-model-already-replaced")
    assert result["status"] == "already_current"
    assert result["updated_count"] == 0
    assert result["scores_updated_at"] is None
    assert new_engine.calls == []
    assert stored_records() == before


def test_inference_failure_rolls_back_scores_fingerprint_and_notice(runtime, monkeypatch):
    client, _, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    assert submit(client, day, "바다").status_code == 200
    before = stored_records()
    engine = UpdateTestEngine()
    calls = []

    def fail_second(word, answer):
        calls.append(word)
        if len(calls) == 2:
            raise RuntimeError("TEST ONLY: second inference failed")
        return -80.5

    monkeypatch.setattr(engine, "score", fail_second)
    with db.connect() as conn:
        # 예외를 연결 context 안에서 잡아도 함수 자체가 부분 갱신을 남기면 안 됩니다.
        with pytest.raises(ScoreUpdateError) as raised:
            recalculate_scores(conn, engine, from_fingerprint=old_engine.fingerprint, apply=True)
        assert raised.value.code == "score_failed"
    assert len(calls) == 2
    assert stored_records() == before


def test_unexpected_old_fingerprint_refuses_without_inference(runtime):
    client, _, _ = runtime
    begin(client)
    before = stored_records()
    engine = UpdateTestEngine()
    with pytest.raises(ScoreUpdateError) as raised:
        update(engine, "unrelated-model")
    assert raised.value.code == "fingerprint_mismatch"
    assert engine.calls == []
    assert stored_records() == before


@pytest.mark.parametrize("offset", [-1, 1], ids=["past", "future"])
def test_only_current_korean_date_can_be_selected(runtime, offset):
    client, _, old_engine = runtime
    day, _ = begin(client)
    before = stored_records()
    engine = UpdateTestEngine()
    with pytest.raises(ScoreUpdateError) as raised:
        update(
            engine,
            old_engine.fingerprint,
            target_date=date.fromisoformat(day) + timedelta(days=offset),
        )
    assert raised.value.code == "wrong_date"
    assert engine.calls == []
    assert stored_records() == before


def test_missing_puzzle_is_not_created_as_a_side_effect(runtime):
    _, _, old_engine = runtime
    before = stored_records()
    engine = UpdateTestEngine()
    with pytest.raises(ScoreUpdateError) as raised:
        update(engine, old_engine.fingerprint)
    assert raised.value.code == "puzzle_missing"
    assert engine.calls == []
    assert stored_records() == before


def test_midnight_during_inference_cancels_every_change(runtime):
    client, clock, old_engine = runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 58, tzinfo=UTC)
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    assert submit(client, day, "바다").status_code == 200
    before = stored_records()
    engine = UpdateTestEngine()
    engine.after_score = lambda: clock.update(now=datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC))
    with db.connect() as conn:
        with pytest.raises(ScoreUpdateError) as raised:
            recalculate_scores(
                conn,
                engine,
                from_fingerprint=old_engine.fingerprint,
                apply=True,
                now=lambda: clock["now"],
            )
        assert raised.value.code == "date_changed"
    assert engine.calls
    # state API는 자정 만료 정리를 하므로 DB를 직접 비교해 전환 도구만 평가합니다.
    assert stored_records() == before


def test_unavailable_model_cannot_change_records(runtime):
    client, _, old_engine = runtime
    begin(client)
    before = stored_records()
    engine = UpdateTestEngine()
    engine.ready = False
    engine.error = "TEST ONLY: model unavailable"
    with pytest.raises(ScoreUpdateError) as raised:
        update(engine, old_engine.fingerprint)
    assert raised.value.code == "model_unavailable"
    assert engine.calls == []
    assert stored_records() == before


@pytest.mark.parametrize(
    "invalid",
    [float("nan"), float("inf"), -float("inf"), -100.01, 100.01],
    ids=["nan", "positive-infinity", "negative-infinity", "below-range", "above-range"],
)
def test_nonfinite_or_out_of_range_scores_cancel_update(runtime, monkeypatch, invalid):
    client, _, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    before = stored_records()
    engine = UpdateTestEngine()
    monkeypatch.setattr(engine, "score", lambda word, answer: invalid)
    with pytest.raises(ScoreUpdateError) as raised:
        update(engine, old_engine.fingerprint)
    assert raised.value.code == "invalid_score"
    assert stored_records() == before


@pytest.mark.parametrize("score", [-100.0, 0.0, 100.0])
def test_valid_score_boundaries_do_not_change_exact_word_judgment(runtime, monkeypatch, score):
    client, _, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    engine = UpdateTestEngine()
    monkeypatch.setattr(engine, "score", lambda word, answer: score)
    update(engine, old_engine.fingerprint)
    main.app.state.engine = engine
    state = client.get("/api/state").json()
    assert state["game"]["guesses"][0]["similarity"] == score
    assert state["game"]["guesses"][0]["is_correct"] is False
    assert state["game"]["status"] == "playing"


@pytest.mark.parametrize("field", ["from", "to"])
def test_empty_fingerprint_is_rejected(runtime, field):
    client, _, old_engine = runtime
    begin(client)
    before = stored_records()
    engine = UpdateTestEngine()
    old_fingerprint = old_engine.fingerprint
    if field == "from":
        old_fingerprint = ""
    else:
        engine.fingerprint = ""
    with pytest.raises(ScoreUpdateError) as raised:
        update(engine, old_fingerprint)
    assert raised.value.code == "invalid_fingerprint"
    assert engine.calls == []
    assert stored_records() == before


def test_zero_guess_update_changes_only_model_metadata(runtime):
    client, clock, old_engine = runtime
    day_text, _ = begin(client)
    day = date.fromisoformat(day_text)
    before = stored_records()
    engine = UpdateTestEngine()
    result = update(engine, old_engine.fingerprint, target_date=day)
    after = stored_records()
    assert result["status"] == "applied"
    assert result["games_count"] == 1
    assert result["guesses_count"] == result["updated_count"] == 0
    assert datetime.fromisoformat(result["scores_updated_at"]) == clock["now"]
    assert_summary(result["old_scores"], [])
    assert_summary(result["new_scores"], [])
    assert engine.calls == []
    assert preserved_fields(after, day) == preserved_fields(before, day)


def test_database_lock_conflict_stops_without_waiting_or_inference(runtime):
    client, _, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    before = stored_records()
    engine = UpdateTestEngine()
    # 임시 스키마의 테이블만 잠급니다. NOWAIT가 없어도 2초 제한으로 검사 무한 대기를 막습니다.
    with db.connect() as busy, db.connect() as attempt:
        busy.execute("LOCK TABLE guesses IN ACCESS EXCLUSIVE MODE")
        attempt.execute("SET LOCAL statement_timeout = '2s'")
        with pytest.raises(ScoreUpdateError) as raised:
            recalculate_scores(attempt, engine, from_fingerprint=old_engine.fingerprint, apply=True)
        assert raised.value.code == "database_busy"
        assert attempt.execute("SELECT 1 AS usable").fetchone()["usable"] == 1
    assert engine.calls == []
    assert stored_records() == before


def test_later_database_write_failure_rolls_back_first_score_even_when_caught(runtime):
    client, _, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    assert submit(client, day, "바다").status_code == 200
    # 두 번째 새 점수만 거부합니다. 기존 점수와 첫 번째 UPDATE는 이 제약을 통과합니다.
    with db.connect() as conn:
        conn.execute(
            "ALTER TABLE guesses ADD CONSTRAINT test_recalc_second_write_failure "
            "CHECK (similarity <> 72.125)"
        )
    before = stored_records()
    with db.connect() as conn:
        with pytest.raises(CheckViolation):
            recalculate_scores(
                conn, UpdateTestEngine(), from_fingerprint=old_engine.fingerprint, apply=True
            )
        # 전환 함수가 자체 트랜잭션을 복구하여 같은 연결도 바로 다시 쓸 수 있어야 합니다.
        rows = conn.execute("SELECT similarity FROM guesses ORDER BY id").fetchall()
        assert [row["similarity"] for row in rows] == [23.4567, 23.4567]
    assert stored_records() == before


@pytest.mark.parametrize("field", ["ready", "fingerprint"])
def test_model_change_during_inference_cancels_update(runtime, field):
    client, _, old_engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    before = stored_records()
    engine = UpdateTestEngine()
    engine.after_score = lambda: setattr(
        engine, field, False if field == "ready" else "unexpected-version"
    )
    with pytest.raises(ScoreUpdateError) as raised:
        update(engine, old_engine.fingerprint)
    assert raised.value.code == "model_unavailable"
    assert stored_records() == before
