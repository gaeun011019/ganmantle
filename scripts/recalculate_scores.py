"""오늘 저장된 유사도만 새 모델로 재계산합니다. 기본은 확인이며 --apply만 반영합니다.

사용 순서: 앱 정지 → 논리 백업 → 새 SQL 변경 이력 적용 → 이 도구 → 앱 재시작.
정답·입력·횟수·시각·순위 기준·사용자·채팅·과거 날짜는 변경하지 않습니다.
출력은 개수·모델 지문·점수 전체 분포뿐이며 입력과 정답을 출력하지 않습니다.
"""
from __future__ import annotations

import argparse
from collections.abc import Callable
from datetime import date, datetime
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from psycopg.errors import LockNotAvailable

from app import db, game


class ScoreUpdateError(RuntimeError):
    """입력 내용이나 연결 비밀값을 포함하지 않는 전환 오류입니다."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def distribution(values: list[float]) -> dict:
    """행별 점수 대신 전체 분포만 반환합니다. 빈 기록은 0점으로 대체하지 않습니다."""
    return {
        "count": len(values),
        "min": min(values) if values else None,
        "max": max(values) if values else None,
        "mean": statistics.fmean(values) if values else None,
    }


def valid_fingerprint(value: str) -> bool:
    # 지문은 불투명한 버전 식별자입니다. 테스트용 식별자도 같은 경로를 사용합니다.
    return isinstance(value, str) and 1 <= len(value) <= 256 and all(
        character.isprintable() and not character.isspace() for character in value
    )


def recalculate_scores(
    conn,
    engine,
    *,
    from_fingerprint: str,
    target_date: date | None = None,
    apply: bool = False,
    now: Callable[[], datetime] | None = None,
) -> dict:
    """전환 전체를 한 트랜잭션으로 처리합니다. 호출자가 오류를 잡아도 부분 반영하지 않습니다.

    앱을 정지한 뒤 새 연결로 호출합니다. NOWAIT 잠금이 실패하면 재시도하지 않고
    중단합니다. 같은 새 지문이 이미 저장됐다면 반복 실행도 모델 호출 없이 끝납니다.
    """
    clock = now or game.utcnow
    started = clock()
    day = target_date if target_date is not None else game.puzzle_date(started)
    if day != game.puzzle_date(started):
        raise ScoreUpdateError("wrong_date", "한국 시간 오늘의 문제만 전환할 수 있습니다.")
    if not valid_fingerprint(from_fingerprint):
        raise ScoreUpdateError("invalid_fingerprint", "기존 모델 지문을 지정해야 합니다.")
    if not engine.ready:
        raise ScoreUpdateError("model_unavailable", "새 모델이 준비되지 않았습니다. 모델 파일과 검증 결과를 확인하세요.")
    to_fingerprint = engine.fingerprint
    if not valid_fingerprint(to_fingerprint) or to_fingerprint == "unavailable":
        raise ScoreUpdateError("invalid_fingerprint", "새 모델의 지문이 유효하지 않습니다.")

    def check_date():
        current = clock()
        if game.puzzle_date(current) != day:
            raise ScoreUpdateError("date_changed", "전환 중 한국 시간 날짜가 바뀌어 전체 변경을 취소했습니다.")
        return current

    try:
        with conn.transaction():
            # 추론 중 새 시작/입력/자정 정리가 끼어들거나 조회가 반쪽 결과를 읽지 않게 합니다.
            # NOWAIT는 실행 중인 앱과 잠금 순서가 엇갈렸을 때 대기/교착을 피합니다.
            conn.execute("LOCK TABLE puzzles, games, guesses IN ACCESS EXCLUSIVE MODE NOWAIT")
            check_date()
            puzzle = conn.execute(
                "SELECT answer, model_fingerprint, scores_updated_at FROM puzzles WHERE puzzle_date = %s",
                (day,),
            ).fetchone()
            if puzzle is None:
                raise ScoreUpdateError("puzzle_missing", "오늘 저장된 문제가 없습니다. 전환할 기록이 없습니다.")
            previous_fingerprint = puzzle["model_fingerprint"]
            # 이미 반영된 명령을 같은 --from-fingerprint로 재실행해도 기록을 다시 쓰지 않습니다.
            already_current = previous_fingerprint == to_fingerprint
            if not already_current and previous_fingerprint != from_fingerprint:
                raise ScoreUpdateError("fingerprint_mismatch", "DB의 기존 모델 지문이 --from-fingerprint와 다릅니다. 변경하지 않았습니다.")
            count = conn.execute(
                "SELECT count(*) AS count FROM games WHERE puzzle_date = %s", (day,)
            ).fetchone()["count"]
            rows = conn.execute("""
                SELECT q.id, q.word, q.similarity
                FROM guesses q JOIN games g ON g.id = q.game_id
                WHERE g.puzzle_date = %s ORDER BY q.id
            """, (day,)).fetchall()
            old_values = [float(row["similarity"]) for row in rows]
            report = {
                "status": "already_current" if already_current else "dry_run",
                "puzzle_date": day.isoformat(),
                "from_fingerprint": previous_fingerprint,
                "to_fingerprint": to_fingerprint,
                "games_count": count,
                "guesses_count": len(rows),
                "updated_count": 0,
                "scores_updated_at": puzzle["scores_updated_at"].isoformat() if puzzle["scores_updated_at"] else None,
                "old_scores": distribution(old_values),
                "new_scores": distribution(old_values) if already_current else None,
            }
            if already_current:
                check_date()
                return report

            updates = []
            scores_by_word = {}
            for row in rows:
                check_date()
                word = row["word"]
                # 기존 입력도 삭제하거나 재판정하지 않습니다. 사용자들의 같은 입력은 한 번만 계산합니다.
                if word not in scores_by_word:
                    try:
                        value = float(engine.score(word, puzzle["answer"]))
                    except Exception:
                        check_date()
                        raise ScoreUpdateError("score_failed", "기존 입력의 재계산에 실패해 전체 작업을 중단했습니다. 기록은 변경하지 않았습니다.") from None
                    check_date()
                    if not math.isfinite(value) or not -100 <= value <= 100:
                        raise ScoreUpdateError("invalid_score", "재계산 결과가 유한한 -100~100 점수가 아닙니다. 기록은 변경하지 않았습니다.")
                    scores_by_word[word] = value
                updates.append((scores_by_word[word], row["id"]))
            check_date()
            if not engine.ready or engine.fingerprint != to_fingerprint:
                raise ScoreUpdateError("model_unavailable", "재계산 중 모델 상태가 바뀌어 작업을 중단했습니다.")
            report["new_scores"] = distribution([value for value, _ in updates])
            if apply:
                for value, guess_id in updates:
                    changed = conn.execute(
                        "UPDATE guesses SET similarity = %s WHERE id = %s", (value, guess_id)
                    ).rowcount
                    if changed != 1:
                        raise ScoreUpdateError("record_changed", "대상 기록이 바뀌어 전체 작업을 취소했습니다.")
                updated_at = check_date()
                changed = conn.execute("""
                    UPDATE puzzles SET model_fingerprint = %s, scores_updated_at = %s
                    WHERE puzzle_date = %s AND model_fingerprint = %s
                """, (to_fingerprint, updated_at, day, from_fingerprint)).rowcount
                if changed != 1:
                    raise ScoreUpdateError("record_changed", "대상 문제가 바뀌어 전체 작업을 취소했습니다.")
                report.update(status="applied", updated_count=len(updates), scores_updated_at=updated_at.isoformat())
            check_date()
            return report
    except LockNotAvailable:
        raise ScoreUpdateError("database_busy", "게임 DB가 사용 중입니다. 앱을 정지한 뒤 다시 실행해 주세요.") from None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from-fingerprint", required=True, help="오늘 문제에 저장된 변경 전 모델 지문")
    parser.add_argument("--date", type=date.fromisoformat, help="대상 날짜 YYYY-MM-DD. 생략하면 한국 시간 오늘")
    parser.add_argument("--apply", action="store_true", help="계산 결과를 실제 반영합니다. 생략하면 DB를 변경하지 않습니다.")
    args = parser.parse_args(argv)
    try:
        # CLI 인자를 검사한 뒤에만 모델을 읽습니다. DB 변경 이력을 자동 적용하지 않습니다.
        from app.similarity import get_engine
        with db.connect() as conn:
            report = recalculate_scores(
                conn, get_engine(), from_fingerprint=args.from_fingerprint,
                target_date=args.date, apply=args.apply,
            )
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0
    except ScoreUpdateError as error:
        print(json.dumps({"error": error.code, "message": str(error)}, ensure_ascii=False), file=sys.stderr)
    except Exception:
        # DB 오류에 SQL/연결 정보/입력이 포함돼도 사용자 기록을 로그에 출력하지 않습니다.
        print(json.dumps({"error": "operation_failed", "message": "처리에 실패했습니다. DB 연결, SQL 변경 이력, 모델 준비를 확인해 주세요."}, ensure_ascii=False), file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
