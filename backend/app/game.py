"""게임 규칙: 한국 자정, 한 번만 시작, 실제 유사도, 중복 재표시, 서버 시간."""
import logging
import math
import secrets
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .users import UserError, normalize, valid_text
from .words import WordsUnavailableError, is_allowed_word
from .similarity import ModelUnavailableError, VectorUnavailableError
from .word_ranks import rank_for_score

SEOUL = ZoneInfo("Asia/Seoul")
ANSWER_PATH = Path(__file__).with_name("answers.txt")
logger = logging.getLogger(__name__)
DATE_MESSAGE = "날짜가 바뀌어 어제의 도전이 종료되었어요. 오늘의 새 단어에 도전해 보세요."

class GameError(UserError):
    pass

def utcnow() -> datetime:
    # 테스트에서는 이 함수만 교체합니다. 클라이언트가 시간을 지정할 수는 없습니다.
    return datetime.now(UTC)

def puzzle_date(now: datetime) -> date:
    return now.astimezone(SEOUL).date()

def next_reset(now: datetime) -> datetime:
    return datetime.combine(puzzle_date(now) + timedelta(days=1), time.min, SEOUL).astimezone(UTC)

def close_expired(conn, now: datetime, user_id=None):
    # 접속하지 않은 사용자도 서버 자정 작업/재시작에서 정리됩니다. 완료 기록은 보존합니다.
    query = """UPDATE games SET status = 'incomplete',
               closed_at = ((puzzle_date + 1)::timestamp AT TIME ZONE 'Asia/Seoul')
               WHERE status = 'playing' AND puzzle_date < %s"""
    params = [puzzle_date(now)]
    if user_id is not None:
        query += " AND user_id = %s"
        params.append(user_id)
    conn.execute(query, params)

def ensure_date(expected: date, now: datetime):
    if expected != puzzle_date(now):
        raise GameError("date_changed", DATE_MESSAGE, 409)

def model_status(conn, day: date, engine):
    status = {"ready": bool(engine.ready), "name": engine.name, "error": engine.error, "scores_updated_at": None,
              "supports_oov": bool(getattr(engine, "supports_oov", False))}
    saved = conn.execute("SELECT model_fingerprint, scores_updated_at FROM puzzles WHERE puzzle_date = %s", (day,)).fetchone()
    if saved and saved["scores_updated_at"]:
        status["scores_updated_at"] = saved["scores_updated_at"].isoformat()
    if status["ready"] and saved and saved["model_fingerprint"] != engine.fingerprint:
        status.update(ready=False, error="오늘 문제와 모델 버전이 달라요. 기존 모델을 복구하거나 한국 시간 자정 이후 새 모델을 사용하세요.")
    return status

def require_model(conn, day: date, engine):
    status = model_status(conn, day, engine)
    if not status["ready"]:
        raise GameError("model_unavailable", status["error"] or "유사도 모델을 아직 준비하지 못했어요.", 503)

def ensure_puzzle(conn, day: date, engine):
    require_model(conn, day, engine)
    saved = conn.execute("SELECT * FROM puzzles WHERE puzzle_date = %s", (day,)).fetchone()
    if not saved:
        try:
            answers = sorted({normalize(line) for line in ANSWER_PATH.read_text(encoding="utf-8-sig").splitlines() if line.strip() and not line.lstrip().startswith("#")})
            if not answers:
                raise ValueError("정답 목록이 비어 있습니다.")
        except (OSError, ValueError) as exc:
            logger.exception("정답 목록 준비 실패")
            raise GameError("answers_unavailable", "정답 후보 파일을 읽을 수 없어요. 서버의 answers.txt를 확인해 주세요.", 503) from exc
        # 최초 생성 때만 무작위 선택합니다. 날짜/정답/모델은 DB에 고정되어 재시작에도 유지됩니다.
        conn.execute("INSERT INTO puzzles (puzzle_date, answer, model_fingerprint) VALUES (%s, %s, %s) ON CONFLICT (puzzle_date) DO NOTHING", (day, secrets.choice(answers), engine.fingerprint))
        saved = conn.execute("SELECT * FROM puzzles WHERE puzzle_date = %s", (day,)).fetchone()
    if saved["model_fingerprint"] != engine.fingerprint:
        raise GameError("model_unavailable", "오늘 문제의 모델 버전과 서버 모델 버전이 달라요.", 503)
    return saved

def elapsed_ms(start: datetime, end: datetime) -> int:
    delta = end - start
    return max(0, delta.days * 86400000 + delta.seconds * 1000 + delta.microseconds // 1000)

def word_rankings(engine, answer: str, expected: date | None = None):
    """실제 모델과 같은 사전 벡터에서 만든 순위만 사용합니다. 정답은 응답에 넣지 않습니다."""
    try:
        result = engine.rankings(answer)
    except ModelUnavailableError:
        if expected is not None:
            ensure_date(expected, utcnow())
        raise GameError("model_unavailable", "단어 순위 자료를 준비하지 못했어요. 준비가 끝난 뒤 다시 시도해 주세요.", 503) from None
    if expected is not None:
        ensure_date(expected, utcnow())
    return result


def ranking(conn, day: date, user_id=None, indexed=None):
    """오늘 참가자를 한 번에 조회합니다. 순위에는 반올림 전 DB 시간을 씁니다."""
    rows = conn.execute("""
        SELECT g.user_id, u.nickname, g.attempts, g.status,
               g.started_at, g.completed_at,
               (SELECT MAX(gs.similarity) FROM guesses gs WHERE gs.game_id = g.id) AS best_similarity,
               (SELECT gs.word FROM guesses gs WHERE gs.game_id = g.id
                ORDER BY gs.similarity DESC, gs.is_correct DESC, gs.attempt LIMIT 1) AS best_word,
               CASE WHEN g.status = 'completed' THEN
                   RANK() OVER (
                       PARTITION BY g.status
                       ORDER BY g.attempts, g.completed_at - g.started_at
                   )
               ELSE NULL END AS rank
        FROM games g JOIN users u ON u.id = g.user_id
        WHERE g.puzzle_date = %s AND g.status IN ('completed', 'playing')
        ORDER BY CASE WHEN g.status = 'completed' THEN 0 ELSE 1 END,
                 CASE WHEN g.status = 'completed' THEN g.attempts END,
                 CASE WHEN g.status = 'completed' THEN g.completed_at - g.started_at END,
                 u.nickname_key, u.id
    """, (day,)).fetchall()
    result = {"completed": [], "playing": []}
    for row in rows:
        complete = row["status"] == "completed"
        best_rank = rank_for_score(indexed, row["best_word"], row["best_similarity"])
        # 추측 단어·정답·세션·상대방의 시작 시각은 공개하지 않습니다.
        result[row["status"]].append({
            "user_id": str(row["user_id"]), "nickname": row["nickname"],
            "attempts": row["attempts"], "rank": row["rank"],
            "best_similarity": row["best_similarity"],
            "best_similarity_rank": best_rank,
            "elapsed_ms": elapsed_ms(row["started_at"], row["completed_at"]) if complete else None,
            "is_me": row["user_id"] == user_id,
        })
    return result


def state(conn, user, engine, client_date: date | None = None):
    now = utcnow()
    day = puzzle_date(now)
    model = model_status(conn, day, engine)
    indexed = None
    reference = {"ready": False, "error": None, "vocabulary_size": None,
                 "top1": None, "top10": None, "top1000": None}
    try:
        # 기준 점수는 첫 화면부터 필요합니다. 문제만 고정하고 사용자 도전은 만들지 않습니다.
        puzzle = ensure_puzzle(conn, day, engine)
        indexed = word_rankings(engine, puzzle["answer"])
        for key in ("vocabulary_size", "top1", "top10", "top1000"):
            reference[key] = indexed["reference"][key]
        reference["ready"] = True
    except GameError as error:
        model.update(ready=False, error=error.message)
        reference["error"] = error.message
    refreshed_now = utcnow()
    if puzzle_date(refreshed_now) != day:
        return state(conn, user, engine, client_date)
    now = refreshed_now
    # 요청 날짜가 아니라 서버의 오늘 기준입니다. 어제 문제가 없으면 다른 날짜로 대체하지 않습니다.
    yesterday = conn.execute("SELECT answer FROM puzzles WHERE puzzle_date = %s", (day - timedelta(days=1),)).fetchone()
    record = None
    if user:
        close_expired(conn, now, user["id"])
        saved = conn.execute("SELECT * FROM games WHERE user_id = %s AND puzzle_date = %s", (user["id"], day)).fetchone()
        if saved:
            guesses = conn.execute("SELECT word, similarity, attempt, is_correct FROM guesses WHERE game_id = %s ORDER BY last_display_order DESC, attempt DESC", (saved["id"],)).fetchall()
            for guess in guesses:
                guess["similarity_rank"] = rank_for_score(indexed, guess["word"], guess["similarity"])
            end = saved["completed_at"] or saved["closed_at"] or now
            record = {
                "status": saved["status"], "started_at": saved["started_at"].isoformat(),
                "completed_at": saved["completed_at"].isoformat() if saved["completed_at"] else None,
                "elapsed_ms": elapsed_ms(saved["started_at"], end), "attempts": saved["attempts"], "guesses": guesses,
            }
    return {
        "server_now": now.isoformat(), "puzzle_date": day.isoformat(), "next_reset_at": next_reset(now).isoformat(),
        "yesterday_answer": yesterday["answer"] if yesterday else None,
        "user": {"id": str(user["id"]), "nickname": user["nickname"]} if user else None,
        "game": record, "model": model, "similarity_reference": reference,
        "ranking": ranking(conn, day, user["id"] if user else None, indexed),
        "date_changed": client_date is not None and client_date != day,
    }

def start(conn, user, expected: date, engine):
    now = utcnow()
    close_expired(conn, now, user["id"])
    ensure_date(expected, now)
    existing = conn.execute("SELECT id FROM games WHERE user_id = %s AND puzzle_date = %s", (user["id"], expected)).fetchone()
    if existing:
        return  # 시작을 반복해도 처음 시작 시각을 유지합니다.
    puzzle = ensure_puzzle(conn, expected, engine)
    word_rankings(engine, puzzle["answer"], expected)
    started_at = utcnow()
    ensure_date(expected, started_at)
    conn.execute("INSERT INTO games (user_id, puzzle_date, started_at) VALUES (%s, %s, %s) ON CONFLICT (user_id, puzzle_date) DO NOTHING", (user["id"], expected, started_at))

def guess(conn, user, expected: date, raw_word: str, engine, submitted_at: datetime | None = None) -> bool:
    now = utcnow()
    submitted_at = submitted_at or now
    close_expired(conn, now, user["id"])
    ensure_date(expected, now)
    word = normalize(raw_word)
    if not 1 <= len(word) <= 40 or not valid_text(word):
        raise GameError("invalid_word", "단어는 제어 문자 없이 1~40자로 입력해 주세요.")
    saved = conn.execute("SELECT * FROM games WHERE user_id = %s AND puzzle_date = %s FOR UPDATE", (user["id"], expected)).fetchone()
    if not saved:
        raise GameError("not_started", "오늘 게임 시작 버튼을 먼저 눌러 주세요.", 409)
    # 새 요청은 예전에 저장된 중복이라도 현재 입력 규칙을 적용합니다.
    # fastText는 완성형 한글의 미등록 단어도 실제 subword 벡터로 계산합니다.
    try:
        allowed = is_allowed_word(word, allow_oov=getattr(engine, "supports_oov", False))
    except WordsUnavailableError as exc:
        raise GameError("dictionary_unavailable", str(exc), 503) from exc
    if not allowed:
        message = ("입력할 수 없는 단어예요. 공백·숫자·자모 없이 완성된 한글 단어를 입력해 주세요."
                   if getattr(engine, "supports_oov", False) else "입력할 수 없는 단어예요. 사전에 등록된 한국어 단어를 입력해 주세요.")
        raise GameError("unrecognized_word", message)
    previous = conn.execute("SELECT id FROM guesses WHERE game_id = %s AND word = %s", (saved["id"], word)).fetchone()
    revision = saved["display_revision"] + 1
    if previous:
        # 완료 후 재전송도 기존 결과를 되돌립니다. 모델을 다시 계산하지 않습니다.
        ensure_date(expected, utcnow())
        conn.execute("UPDATE guesses SET last_display_order = %s WHERE id = %s", (revision, previous["id"]))
        conn.execute("UPDATE games SET display_revision = %s WHERE id = %s", (revision, saved["id"]))
        return True
    if saved["status"] != "playing":
        raise GameError("game_completed", "오늘의 정답을 이미 맞혔어요. 다음 문제는 자정에 열립니다.", 409)
    require_model(conn, expected, engine)
    puzzle = conn.execute("SELECT answer FROM puzzles WHERE puzzle_date = %s", (expected,)).fetchone()
    word_rankings(engine, puzzle["answer"], expected)
    try:
        score = float(engine.score(word, puzzle["answer"]))
        if not math.isfinite(score) or not -100 <= score <= 100:
            raise ValueError("모델이 유효하지 않은 유사도를 반환했습니다.")
    except VectorUnavailableError as exc:
        ended_at = utcnow()
        if puzzle_date(ended_at) != expected:
            close_expired(conn, ended_at, user["id"])
            raise GameError("date_changed", DATE_MESSAGE, 409) from exc
        raise GameError("unrecognized_word", "입력할 수 없는 단어예요. 이 모델에 단어·서브워드 정보가 없어 유사도를 계산할 수 없어요.") from exc
    except Exception as exc:
        ended_at = utcnow()
        if puzzle_date(ended_at) != expected:
            close_expired(conn, ended_at, user["id"])
            raise GameError("date_changed", DATE_MESSAGE, 409) from exc
        # 입력 내용과 정답은 로그에 남기지 않습니다. 실패를 임의 점수로 바꾸지 않습니다.
        logger.error("유사도 계산 실패 (%s)", type(exc).__name__)
        raise GameError("similarity_failed", "이 입력의 유사도를 계산하지 못했어요. 시도 횟수에는 포함하지 않았어요.", 503) from exc
    finished_processing_at = utcnow()
    if puzzle_date(finished_processing_at) != expected:
        close_expired(conn, finished_processing_at, user["id"])
        raise GameError("date_changed", DATE_MESSAGE, 409)
    correct = word == normalize(puzzle["answer"])
    attempt = saved["attempts"] + 1
    # 완료 시간은 계산 종료가 아니라 서버가 제출을 받은 시간입니다.
    submitted_at = max(submitted_at, saved["started_at"])
    conn.execute("""INSERT INTO guesses (game_id, word, similarity, attempt, is_correct, submitted_at, last_display_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)""", (saved["id"], word, score, attempt, correct, submitted_at, revision))
    conn.execute("""UPDATE games SET attempts = %s, display_revision = %s,
                    status = %s, completed_at = %s WHERE id = %s""",
                 (attempt, revision, "completed" if correct else "playing", submitted_at if correct else None, saved["id"]))
    return False
