"""실제 PostgreSQL의 임시 스키마에서 순위 API 계약과 기록 보존을 확인합니다.

고정 엔진은 API 전달/오류 검사 전용입니다. 실제 어휘 순위의 수학적 경계와
모델 품질은 WordRankIndex 단위 검사와 실제 모델 스모크 검사에서 따로 확인합니다.
"""
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
import json
import unicodedata
from unittest.mock import Mock

import numpy as np
import pytest
from fastapi.testclient import TestClient

from test_rules import runtime, begin, submit, scalar
from app import db, main
from app.similarity import ModelUnavailableError, VectorUnavailableError
from app.words import is_allowed_word


REFERENCE = {"vocabulary_size": 49485, "top1": 95.678901, "top10": 64.234567, "top1000": -1.234567}
RANKS = {"사과": 0, "연필": 1, "산책": 10, "바다": 1000, "학교": 1000}
SCORES = {"사과": 100.0, "연필": REFERENCE["top1"], "산책": REFERENCE["top10"],
          "바다": REFERENCE["top1000"], "학교": REFERENCE["top1000"], "모니터": -2.5}


@pytest.fixture
def rank_runtime(runtime, monkeypatch):
    client, clock, engine = runtime
    monkeypatch.setattr(engine, "rankings", lambda answer: {"ranks": dict(RANKS), "reference": dict(REFERENCE)})
    monkeypatch.setattr(engine, "score", lambda word, answer: SCORES[word])
    return client, clock, engine


def records():
    with db.connect() as conn:
        return {table: conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                for table in ("users", "puzzles", "games", "guesses")}


def assert_reference(state):
    assert state["similarity_reference"] == {"ready": True, "error": None, **REFERENCE}


def assert_unavailable(state):
    reference = state["similarity_reference"]
    assert state["model"]["ready"] is False
    assert reference["ready"] is False
    assert isinstance(reference["error"], str) and reference["error"]
    for key in ("vocabulary_size", "top1", "top10", "top1000"):
        assert reference[key] is None
    if state["game"]:
        assert all(item["similarity_rank"] is None for item in state["game"]["guesses"])
    for rows in state["ranking"].values():
        assert all(item["best_similarity_rank"] is None for item in rows)


def test_anonymous_first_state_has_reference_without_creating_user_or_game(rank_runtime):
    client, _, _ = rank_runtime
    response = client.get("/api/state")
    assert response.status_code == 200
    state = response.json()
    assert_reference(state)
    assert state["user"] is None and state["game"] is None
    assert state["ranking"] == {"completed": [], "playing": []}
    assert scalar("SELECT count(*) FROM puzzles") == 1
    for table in ("users", "games", "guesses"):
        assert scalar(f"SELECT count(*) FROM {table}") == 0
    original = records()
    assert_reference(client.get("/api/state").json())
    assert records() == original
    # 전체 순위의 단어나 정답을 공개 응답으로 보내지 않습니다.
    assert "사과" not in response.text
    assert "연필" not in response.text
    assert "ranks" not in state
    assert "answer" not in state and state["yesterday_answer"] is None


def test_simultaneous_anonymous_reads_create_one_puzzle_and_no_games(rank_runtime):
    client, _, _ = rank_runtime
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: client.get("/api/state"), range(4)))
    assert all(response.status_code == 200 for response in responses)
    for response in responses:
        assert_reference(response.json())
    assert scalar("SELECT count(*) FROM puzzles") == 1
    assert scalar("SELECT count(*) FROM games") == 0
    assert scalar("SELECT count(*) FROM users") == 0


def test_ranks_include_boundaries_ties_outside_answer_duplicate_and_reconnect(rank_runtime, monkeypatch):
    client, clock, engine = rank_runtime
    day, started = begin(client, "순위확인")
    assert started["ranking"]["playing"][0]["best_similarity_rank"] is None
    for attempt, (word, rank, best) in enumerate((
        ("모니터", None, None), ("바다", 1000, 1000), ("학교", 1000, 1000),
        ("산책", 10, 10), ("연필", 1, 1),
    ), start=1):
        response = submit(client, day, word)
        assert response.status_code == 200
        state = response.json()
        assert_reference(state)
        assert state["game"]["attempts"] == attempt
        assert state["game"]["guesses"][0]["similarity_rank"] == rank
        assert state["game"]["guesses"][0]["similarity"] == SCORES[word]
        assert state["ranking"]["playing"][0]["best_similarity_rank"] == best
    previous_ranking = state["ranking"]
    score = Mock(side_effect=AssertionError("중복 입력은 점수를 재계산하지 않습니다."))
    original_score = engine.score
    monkeypatch.setattr(engine, "score", score)
    duplicate = submit(client, day, "바다").json()
    assert duplicate["duplicate"] is True
    assert duplicate["game"]["attempts"] == 5
    assert duplicate["game"]["guesses"][0]["word"] == "바다"
    assert duplicate["game"]["guesses"][0]["similarity_rank"] == 1000
    assert duplicate["ranking"] == previous_ranking
    score.assert_not_called()
    monkeypatch.setattr(engine, "score", original_score)
    with TestClient(main.app, cookies=dict(client.cookies)) as reconnect:
        restored = reconnect.get("/api/state").json()
        assert restored["game"] == duplicate["game"]
        assert restored["ranking"] == duplicate["ranking"]
        assert_reference(restored)
    clock["now"] += timedelta(seconds=25)
    finished = submit(client, day, "사과").json()
    assert finished["game"]["status"] == "completed"
    assert finished["game"]["guesses"][0]["similarity_rank"] == 0
    assert finished["ranking"]["completed"][0]["best_similarity_rank"] == 0
    assert finished["game"]["elapsed_ms"] == 25000
    assert scalar("SELECT count(*) FROM guesses") == 6
    with db.connect() as conn:
        row = conn.execute("SELECT * FROM guesses ORDER BY id LIMIT 1").fetchone()
        assert "similarity_rank" not in row  # 순위는 저장된 모델/사전으로 재조회합니다.
    with TestClient(main.app) as visitor:
        public = visitor.get("/api/state").json()
        assert public["game"] is None
        assert public["ranking"]["completed"][0]["best_similarity_rank"] == 0
        for private_word in SCORES:
            assert private_word not in json.dumps(public, ensure_ascii=False)


def test_unready_engine_never_creates_puzzle_or_returns_example_reference(rank_runtime, monkeypatch):
    client, _, engine = rank_runtime
    engine.ready = False
    engine.error = "TEST ONLY: dictionary fingerprint mismatch"
    rankings = Mock(side_effect=AssertionError("준비되지 않은 자료를 조회하면 안 됩니다."))
    monkeypatch.setattr(engine, "rankings", rankings)
    state = client.get("/api/state").json()
    assert_unavailable(state)
    assert scalar("SELECT count(*) FROM puzzles") == 0
    response = client.post("/api/users", json={"nickname": "자료대기"})
    assert response.status_code == 200
    day = response.json()["puzzle_date"]
    assert client.post("/api/start", json={"puzzle_date": day}).status_code == 503
    assert scalar("SELECT count(*) FROM games") == 0
    assert scalar("SELECT count(*) FROM guesses") == 0
    rankings.assert_not_called()


def test_index_failure_keeps_records_and_blocks_new_guess_then_recovers(rank_runtime, monkeypatch):
    client, _, engine = rank_runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    before = records()
    original_rankings = engine.rankings
    score = Mock(side_effect=AssertionError("순위가 없으면 새 점수를 계산하면 안 됩니다."))
    monkeypatch.setattr(engine, "score", score)
    monkeypatch.setattr(engine, "rankings", Mock(side_effect=ModelUnavailableError("사과: 비공개 오류 예시")))
    response = client.get("/api/state")
    assert response.status_code == 200
    assert_unavailable(response.json())
    assert "비공개 오류 예시" not in response.text
    rejected = submit(client, day, "연필")
    assert rejected.status_code == 503
    assert rejected.json()["detail"]["code"] == "model_unavailable"
    assert records() == before
    score.assert_not_called()
    monkeypatch.setattr(engine, "rankings", original_rankings)
    recovered = client.get("/api/state").json()
    assert_reference(recovered)
    assert recovered["game"]["guesses"][0]["similarity_rank"] == 10
    assert records() == before


def test_index_failure_blocks_first_start_without_creating_game(rank_runtime, monkeypatch):
    client, _, engine = rank_runtime
    state = client.post("/api/users", json={"nickname": "시작대기"}).json()
    monkeypatch.setattr(engine, "rankings", Mock(side_effect=ModelUnavailableError("TEST ONLY")))
    response = client.post("/api/start", json={"puzzle_date": state["puzzle_date"]})
    assert response.status_code == 503
    assert scalar("SELECT count(*) FROM games") == 0
    assert scalar("SELECT count(*) FROM guesses") == 0


def test_changed_puzzle_fingerprint_hides_current_index_and_preserves_guesses(rank_runtime, monkeypatch):
    client, _, engine = rank_runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    before = records()
    engine.fingerprint = "TEST ONLY: different model"
    rankings = Mock(side_effect=AssertionError("다른 지문의 순위를 사용하면 안 됩니다."))
    monkeypatch.setattr(engine, "rankings", rankings)
    state = client.get("/api/state").json()
    assert_unavailable(state)
    assert state["game"]["guesses"][0]["similarity"] == SCORES["산책"]
    assert submit(client, day, "연필").status_code == 503
    assert records() == before
    rankings.assert_not_called()


def test_score_update_notice_survives_rank_lookup(rank_runtime):
    client, clock, _ = rank_runtime
    day, _ = begin(client)
    with db.connect() as conn:
        conn.execute("UPDATE puzzles SET scores_updated_at = %s WHERE puzzle_date = %s", (clock["now"], day))
    before = records()
    state = client.get("/api/state").json()
    assert_reference(state)
    assert datetime.fromisoformat(state["model"]["scores_updated_at"]) == clock["now"]
    assert records() == before


def test_midnight_during_first_rank_lookup_returns_new_day_without_starting_game(rank_runtime, monkeypatch):
    client, clock, engine = rank_runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    original = engine.rankings
    calls = []

    def crossing(answer):
        calls.append(True)
        if len(calls) == 1:
            clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        return original(answer)

    monkeypatch.setattr(engine, "rankings", crossing)
    response = client.get("/api/state", params={"puzzle_date": day})
    assert response.status_code == 200
    state = response.json()
    assert state["puzzle_date"] == "2026-09-20"
    assert state["date_changed"] is True
    assert state["game"] is None
    assert_reference(state)
    assert scalar("SELECT count(*) FROM puzzles") == 2
    assert scalar("SELECT count(*) FROM games") == 1
    assert scalar("SELECT status FROM games") == "incomplete"
    assert scalar("SELECT count(*) FROM guesses") == 1

@pytest.mark.parametrize("fail", [False, True], ids=["ready", "failed"])
def test_midnight_during_guess_rank_lookup_rejects_without_attempt_or_score(rank_runtime, monkeypatch, fail):
    client, clock, engine = rank_runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    original = engine.rankings
    score = Mock(side_effect=AssertionError("자정이 지나면 추론하지 않습니다."))

    def crossing(answer):
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        if fail:
            raise ModelUnavailableError("TEST ONLY")
        return original(answer)

    monkeypatch.setattr(engine, "rankings", crossing)
    monkeypatch.setattr(engine, "score", score)
    response = submit(client, day, "연필")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    assert scalar("SELECT attempts FROM games") == 1
    assert scalar("SELECT status FROM games") == "incomplete"
    assert scalar("SELECT count(*) FROM guesses") == 1
    score.assert_not_called()


def test_reference_exposes_only_numbers_even_if_internal_index_has_extra_data(rank_runtime, monkeypatch):
    client, _, engine = rank_runtime
    monkeypatch.setattr(engine, "rankings", lambda answer: {
        "ranks": dict(RANKS), "reference": {**REFERENCE, "answer": answer, "words": list(RANKS)},
    })
    response = client.get("/api/state")
    assert response.status_code == 200
    assert_reference(response.json())
    assert "사과" not in response.text
    assert "연필" not in response.text


@pytest.fixture
def oov_runtime(runtime, monkeypatch):
    """API 계약 전용 모형입니다. 운영 엔진은 실제 fastText .bin을 읽습니다."""
    client, clock, engine = runtime
    # 정답을 뺀 비교 사전 1,001개: 20점 동점 990개와 1,000위 경계를 포함합니다.
    sorted_scores = np.array([-5.0, -2.5, -1.25, -1.25] + [20.0] * 990
                             + [40.0, 50.0, 60.0, 70.0, 80.0, 90.0, 95.0], dtype=np.float64)
    scores = {"사과": 100.0, "산책": 20.0, "초록구름산책냥": 80.0,
              "새로만든한국어조합말": 70.0}
    monkeypatch.setattr(engine, "supports_oov", True, raising=False)
    monkeypatch.setattr(engine, "rankings", lambda answer: {
        "ranks": {answer: 0, "산책": 8}, "sorted_scores": sorted_scores,
        "reference": {"vocabulary_size": 1002, "top1": 95.0, "top10": 20.0, "top1000": -2.5},
    })
    monkeypatch.setattr(engine, "score", Mock(side_effect=lambda word, answer: scores[word]))
    return client, clock, engine


def test_oov_success_duplicate_reconnect_and_public_best_rank(oov_runtime, monkeypatch):
    client, clock, engine = oov_runtime
    oov_word = "초록구름산책냥"
    lower_oov_word = "새로만든한국어조합말"
    assert not is_allowed_word(oov_word) and not is_allowed_word(lower_oov_word)
    day, started = begin(client, "미등록입력검증")
    clock["now"] += timedelta(seconds=30)
    for attempt, (word, expected_rank, best_score, best_rank) in enumerate((
        ("산책", 8, 20.0, 8), (oov_word, 3, 80.0, 3), (lower_oov_word, 4, 80.0, 3),
    ), start=1):
        response = submit(client, day, word)
        assert response.status_code == 200
        state = response.json()
        assert state["duplicate"] is False
        assert state["game"]["status"] == "playing"
        assert state["game"]["attempts"] == attempt
        assert state["game"]["guesses"][0]["similarity_rank"] == expected_rank
        own = state["ranking"]["playing"][0]
        assert own["best_similarity"] == best_score
        assert own["best_similarity_rank"] == best_rank
    assert engine.score.call_count == 3
    score = Mock(side_effect=AssertionError("저장한 미등록 단어를 다시 추론하면 안 됩니다."))
    monkeypatch.setattr(engine, "score", score)
    response = submit(client, day, " " + unicodedata.normalize("NFD", oov_word) + " ")
    assert response.status_code == 200
    duplicate = response.json()
    assert duplicate["duplicate"] is True
    assert duplicate["game"]["attempts"] == 3
    assert duplicate["game"]["started_at"] == started["game"]["started_at"]
    assert duplicate["game"]["elapsed_ms"] == 30000
    assert duplicate["game"]["guesses"][0] == {
        "word": oov_word, "similarity": 80.0, "attempt": 2,
        "is_correct": False, "similarity_rank": 3,
    }
    assert duplicate["ranking"] == state["ranking"]
    assert scalar("SELECT count(*) FROM guesses") == 3
    with TestClient(main.app, cookies=dict(client.cookies)) as reconnect:
        restored = reconnect.get("/api/state").json()
        assert restored["game"] == duplicate["game"]
        assert restored["ranking"] == duplicate["ranking"]
    with TestClient(main.app) as visitor:
        response = visitor.get("/api/state")
        public = response.json()
        assert public["user"] is None and public["game"] is None
        assert public["ranking"]["playing"][0]["best_similarity"] == 80.0
        assert public["ranking"]["playing"][0]["best_similarity_rank"] == 3
        assert public["ranking"]["playing"][0]["is_me"] is False
        assert "best_word" not in response.text
        assert all(word not in response.text for word in (oov_word, lower_oov_word, "산책", "사과"))
    score.assert_not_called()


@pytest.mark.parametrize("score, expected_rank", [
    (95.0, 1), (20.0, 8), (-1.25, 998), (-2.5, 1000),
    (float(np.nextafter(-2.5, -np.inf)), None),
], ids=["top-tie", "many-ties", "near-boundary-tie", "rank-1000", "strictly-outside"])
def test_oov_score_rank_uses_same_strict_comparison_for_guess_and_ranking(
        oov_runtime, monkeypatch, score, expected_rank):
    client, _, engine = oov_runtime
    word = "초록구름산책냥"
    assert not is_allowed_word(word)
    monkeypatch.setattr(engine, "score", Mock(return_value=score))
    day, _ = begin(client)
    response = submit(client, day, word)
    assert response.status_code == 200
    state = response.json()
    guess = state["game"]["guesses"][0]
    assert state["game"]["status"] == "playing"
    assert state["game"]["attempts"] == 1
    assert guess["similarity"] == score and guess["similarity_rank"] == expected_rank
    own = state["ranking"]["playing"][0]
    assert own["best_similarity"] == score and own["best_similarity_rank"] == expected_rank


@pytest.mark.parametrize("word, code", [
    ("ㄱㄴ", "unrecognized_word"), ("가 나", "unrecognized_word"),
    ("hello", "unrecognized_word"), ("가1", "unrecognized_word"),
    (" \t ", "invalid_word"), ("가\n나", "invalid_word"),
], ids=["jamo", "inner-space", "latin", "digit", "blank", "control"])
def test_oov_invalid_format_does_not_call_engine_or_change_records(oov_runtime, monkeypatch, word, code):
    client, _, engine = oov_runtime
    day, _ = begin(client)
    before = records()
    score = Mock(side_effect=AssertionError("형식 오류는 추론하지 않습니다."))
    rankings = Mock(side_effect=AssertionError("형식 오류는 순위도 조회하지 않습니다."))
    monkeypatch.setattr(engine, "score", score)
    monkeypatch.setattr(engine, "rankings", rankings)
    response = submit(client, day, word)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == code
    assert records() == before
    assert scalar("SELECT attempts FROM games") == 0
    score.assert_not_called()
    rankings.assert_not_called()


def test_oov_vector_unavailable_returns_input_error_without_counting(oov_runtime, monkeypatch):
    client, _, engine = oov_runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    before = records()
    score = Mock(side_effect=VectorUnavailableError("TEST ONLY: native vector is zero"))
    monkeypatch.setattr(engine, "score", score)
    response = submit(client, day, "쀍")
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unrecognized_word"
    assert "TEST ONLY" not in response.text
    score.assert_called_once_with("쀍", "사과")
    assert records() == before
    state = client.get("/api/state").json()
    assert state["model"]["ready"] is True
    assert state["game"]["attempts"] == 1
    assert [guess["word"] for guess in state["game"]["guesses"]] == ["산책"]


def test_oov_zero_vector_crossing_midnight_prioritizes_date_change(oov_runtime, monkeypatch):
    client, clock, engine = oov_runtime
    clock["now"] = datetime(2026, 9, 19, 14, 59, 59, tzinfo=UTC)
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200

    def fail_after_midnight(word, answer):
        clock["now"] = datetime(2026, 9, 19, 15, 0, 0, tzinfo=UTC)
        raise VectorUnavailableError("TEST ONLY: zero vector after midnight")

    score = Mock(side_effect=fail_after_midnight)
    monkeypatch.setattr(engine, "score", score)
    response = submit(client, day, "쀍")
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "date_changed"
    score.assert_called_once_with("쀍", "사과")
    assert scalar("SELECT count(*) FROM guesses") == 1
    assert scalar("SELECT attempts FROM games") == 1
    assert scalar("SELECT status FROM games") == "incomplete"
    assert scalar("SELECT closed_at FROM games") == clock["now"]


def test_completed_best_score_tie_prefers_exact_answer_over_earlier_wrong_word(rank_runtime, monkeypatch):
    client, clock, engine = rank_runtime
    monkeypatch.setattr(engine, "score", lambda word, answer: {"모니터": 100.0, "사과": 100.0}[word])
    day, _ = begin(client)
    clock["now"] += timedelta(seconds=1)
    wrong = submit(client, day, "모니터")
    assert wrong.status_code == 200
    assert wrong.json()["game"]["status"] == "playing"
    assert wrong.json()["game"]["guesses"][0]["is_correct"] is False
    clock["now"] += timedelta(seconds=1)
    response = submit(client, day, "사과")
    assert response.status_code == 200
    state = response.json()
    assert state["game"]["status"] == "completed"
    assert state["game"]["attempts"] == 2
    assert state["game"]["guesses"][0]["is_correct"] is True
    assert state["game"]["guesses"][0]["similarity_rank"] == 0
    assert state["ranking"]["completed"][0]["best_similarity"] == 100.0
    assert state["ranking"]["completed"][0]["best_similarity_rank"] == 0
