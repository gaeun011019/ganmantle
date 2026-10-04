"""입력 사전과 계산 진입 조건을 검증합니다. 운영 모델 추론/품질 검사는 별도입니다."""

import hashlib
import json
import unicodedata
from pathlib import Path
from unittest.mock import Mock

import numpy as np
import pytest

from test_rules import runtime, begin, submit
from app import db, words
from app.similarity import SimilarityEngine


REJECTED_WORDS = (
    "ㅁㄴㅇㄹㅁㄴㅇㄹ",
    "우러ㅏㄴ러ㅣㅜㅎ",
    "유사도가이상한데",
    "임의한글조합",
    "새로만든한국어조합말",
    "apple",
    "12345",
    "오늘 날씨가 좋다",
    "😀",
)


@pytest.fixture(autouse=True)
def fresh_dictionary_cache():
    # 사전 경로를 바꾸는 검사가 이미 읽힌 운영 사전을 재사용하지 않게 합니다.
    words.get_words.cache_clear()
    yield
    words.get_words.cache_clear()


def saved_records():
    with db.connect() as conn:
        return {
            "games": conn.execute("SELECT * FROM games ORDER BY id").fetchall(),
            "guesses": conn.execute("SELECT * FROM guesses ORDER BY id").fetchall(),
        }


def assert_unchanged(client, previous_state, previous_records):
    current = client.get("/api/state").json()
    assert current["game"] == previous_state["game"]
    assert current["ranking"] == previous_state["ranking"]
    assert saved_records() == previous_records


@pytest.mark.parametrize("word", ("모니터", "키보드", "걷다", "아"))
def test_packaged_dictionary_accepts_known_words_and_nfd(word):
    assert words.is_allowed_word(word) is True
    assert words.is_allowed_word(" " + unicodedata.normalize("NFD", word) + " ") is True


@pytest.mark.parametrize("word", REJECTED_WORDS)
def test_packaged_dictionary_rejects_jamo_sentences_and_unknown_words(word):
    assert words.is_allowed_word(word) is False


def test_all_ninety_daily_answers_are_in_input_dictionary():
    answer_path = Path(words.__file__).with_name("answers.txt")
    answers = [
        line.strip()
        for line in answer_path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]
    assert len(answers) == 90
    rejected = [answer for answer in answers if not words.is_allowed_word(answer)]
    assert rejected == [], f"입력할 수 없는 정답 후보: {rejected}"


def test_rejected_inputs_do_not_call_model_or_change_attempts_history_ranking(runtime, monkeypatch):
    client, _, engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "모니터").status_code == 200
    previous = client.get("/api/state").json()
    records = saved_records()
    score = Mock(side_effect=AssertionError("거절할 입력은 모델을 호출하면 안 됩니다."))
    monkeypatch.setattr(engine, "score", score)
    for word in REJECTED_WORDS:
        response = submit(client, day, word)
        assert response.status_code == 400, (word, response.text)
        assert response.json()["detail"]["code"] == "unrecognized_word"
        assert_unchanged(client, previous, records)
    score.assert_not_called()


def test_known_words_reach_model_and_nfd_reuses_normalized_record(runtime, monkeypatch):
    client, _, engine = runtime
    day, _ = begin(client)
    score = Mock(wraps=engine.score)
    monkeypatch.setattr(engine, "score", score)
    for attempt, word in enumerate(("모니터", "키보드", "걷다", "아"), start=1):
        response = submit(client, day, word)
        assert response.status_code == 200
        state = response.json()
        assert state["game"]["attempts"] == attempt
        assert state["game"]["guesses"][0]["word"] == word
        score.assert_called_with(word, "사과")
    assert score.call_count == 4
    repeated = submit(client, day, " " + unicodedata.normalize("NFD", "모니터") + " ")
    assert repeated.status_code == 200
    result = repeated.json()
    assert result["duplicate"] is True
    assert result["game"]["attempts"] == 4
    assert len(result["game"]["guesses"]) == 4
    assert result["game"]["guesses"][0]["word"] == "모니터"
    assert result["game"]["guesses"][0]["attempt"] == 1
    assert score.call_count == 4


@pytest.mark.parametrize(
    "fault",
    (
        "missing_words",
        "missing_manifest",
        "checksum",
        "invalid_json",
        "count",
        "format",
    ),
)
def test_missing_or_corrupt_dictionary_stops_before_model_without_record_changes(
    runtime, monkeypatch, tmp_path, fault
):
    client, _, engine = runtime
    day, _ = begin(client)
    assert submit(client, day, "산책").status_code == 200
    previous = client.get("/api/state").json()
    records = saved_records()
    words_path = tmp_path / "input_words.txt"
    manifest_path = tmp_path / "input_manifest.json"
    content = ("모니터\nabc\n" if fault == "format" else "모니터\n").encode("utf-8")
    manifest = {
        "output": {
            "sha256": hashlib.sha256(content).hexdigest(),
            "count": len(content.decode("utf-8").splitlines()),
        }
    }
    if fault == "checksum":
        manifest["output"]["sha256"] = "0" * 64
    elif fault == "count":
        manifest["output"]["count"] += 1
    if fault != "missing_words":
        words_path.write_bytes(content)
    if fault != "missing_manifest":
        manifest_path.write_text(
            "{" if fault == "invalid_json" else json.dumps(manifest), encoding="utf-8"
        )
    monkeypatch.setattr(words, "WORDS_PATH", words_path)
    monkeypatch.setattr(words, "MANIFEST_PATH", manifest_path)
    words.get_words.cache_clear()
    score = Mock(side_effect=AssertionError("사전이 준비되지 않으면 모델을 호출하면 안 됩니다."))
    monkeypatch.setattr(engine, "score", score)
    response = submit(client, day, "모니터")
    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "dictionary_unavailable"
    score.assert_not_called()
    assert_unchanged(client, previous, records)


def test_legacy_garbage_is_preserved_but_resubmission_cannot_move_or_count_it(runtime, monkeypatch):
    client, clock, engine = runtime
    day, started = begin(client)
    old_word = "우러ㅏㄴ러ㅣㅜㅎ"
    with db.connect() as conn:
        record = conn.execute(
            "SELECT id FROM games WHERE user_id = %s AND puzzle_date = %s",
            (started["user"]["id"], day),
        ).fetchone()
        conn.execute(
            """INSERT INTO guesses
            (game_id, word, similarity, attempt, is_correct, submitted_at, last_display_order)
            VALUES (%s, %s, %s, 1, false, %s, 1)""",
            (record["id"], old_word, 87.65, clock["now"]),
        )
        conn.execute(
            "UPDATE games SET attempts = 1, display_revision = 1 WHERE id = %s", (record["id"],)
        )
    assert submit(client, day, "산책").status_code == 200
    previous = client.get("/api/state").json()
    assert [item["word"] for item in previous["game"]["guesses"]] == ["산책", old_word]
    records = saved_records()
    score = Mock(side_effect=AssertionError("기존 미등록 기록을 재계산하면 안 됩니다."))
    monkeypatch.setattr(engine, "score", score)
    response = submit(client, day, old_word)
    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "unrecognized_word"
    score.assert_not_called()
    assert_unchanged(client, previous, records)


@pytest.mark.parametrize(
    "input_vector,expected", (((1.0, 0.0), 100.0), ((0.0, 1.0), 0.0), ((-1.0, 0.0), -100.0))
)
def test_similarity_uses_cosine_times_one_hundred(input_vector, expected, monkeypatch):
    # 모델을 내려받거나 로드하지 않고 score 공식만 검사합니다. 실제 품질 검사와 다릅니다.
    engine = SimilarityEngine.__new__(SimilarityEngine)
    engine.ready = True
    engine._np = np
    vectors = {
        "입력": np.asarray(input_vector, dtype=np.float32),
        "정답": np.asarray((1.0, 0.0), dtype=np.float32),
    }
    monkeypatch.setattr(engine, "vector", lambda text: vectors[text])
    assert engine.score("입력", "정답") == pytest.approx(expected)
