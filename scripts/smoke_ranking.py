"""실제 모델 + PostgreSQL로 2단계 랭킹을 검증합니다.

실행: docker compose exec -T app python scripts/smoke_ranking.py
DATABASE_URL의 DB 안에 무작위 임시 스키마만 만들고, 종료 시 그 스키마만 지웁니다.
모델 대체/가짜 점수/기존 public 테이블 접근은 사용하지 않습니다.
"""

import math
import os
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))
from app import db, main
from app.similarity import SimilarityEngine, get_engine
from app.word_ranks import rank_for_score
from app.words import get_words


class SmokeFailure(RuntimeError):
    """정답·쿠키·비밀값을 포함하지 않는 검사 실패 설명입니다."""


def require(condition, message):
    if not condition:
        raise SmokeFailure(message)


def post(client, path, payload):
    response = client.post(path, json=payload)
    require(response.status_code == 200, f"{path} 응답 실패: HTTP {response.status_code}")
    return response.json()


def state(client):
    response = client.get("/api/state")
    require(response.status_code == 200, "게임 상태 조회 실패")
    return response.json()


def run():
    original_url = os.getenv("DATABASE_URL")
    require(bool(original_url), "DATABASE_URL이 필요합니다. app 컨테이너에서 실행하세요.")
    engine = get_engine()
    require(isinstance(engine, SimilarityEngine), "실제 SimilarityEngine이 아닙니다.")
    require(
        engine.ready is True, "실제 모델을 준비하지 못했습니다. 모델 파일과 앱 상태를 확인하세요."
    )
    require(
        len(engine.fingerprint) == 64
        and all(char in "0123456789abcdef" for char in engine.fingerprint),
        "실제 모델 fingerprint 확인 실패",
    )

    schema = "ganmantle_ranking_smoke_" + uuid4().hex
    with psycopg.connect(original_url, autocommit=True) as admin:
        admin.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        # public을 검색 경로에 넣으면 기존 schema_migrations/게임 표를 찾을 수 있으므로
        # 반드시 이번 실행에서 만든 스키마만 사용합니다. 서버 프로세스 환경에는 영향이 없습니다.
        os.environ["DATABASE_URL"] = make_conninfo(original_url, options=f"-c search_path={schema}")
        with (
            TestClient(main.app, base_url="https://testserver") as first,
            TestClient(main.app, base_url="https://testserver") as second,
        ):
            require(
                main.app.state.engine is engine, "앱이 확인한 실제 모델과 다른 모델을 사용합니다."
            )
            with db.connect() as conn:
                require(
                    conn.execute("SELECT current_schema() AS name").fetchone()["name"] == schema,
                    "DB 임시 스키마 격리 확인 실패",
                )
                require(
                    conn.execute("SELECT count(*) AS count FROM games").fetchone()["count"] == 0,
                    "임시 게임 테이블이 비어 있지 않습니다.",
                )

            initial = state(first)
            require(
                initial["similarity_reference"]["ready"] is True,
                "실제 어휘 순위 자료가 준비되지 않았습니다.",
            )
            require(
                initial["similarity_reference"]["vocabulary_size"] >= 1001,
                "상위 1000위 기준을 만들 어휘가 부족합니다.",
            )
            require(
                initial["ranking"] == {"completed": [], "playing": []},
                "새 스키마의 랭킹이 비어 있지 않습니다.",
            )
            post(first, "/api/users", {"nickname": "검증두번"})
            first_started = post(first, "/api/start", {"puzzle_date": initial["puzzle_date"]})
            day = first_started["puzzle_date"]
            require(
                first_started["model"]["ready"] is True, "게임에서 실제 모델을 사용할 수 없습니다."
            )
            # 거절한 입력은 실제 모델의 캐시 조회조차 하지 않아야 합니다.
            before_vectors = engine.vector.cache_info()
            invalid_inputs = ["우러ㅏㄴ러ㅣㅜㅎ", "산책 여행", "abc123", "abc", "123"]
            if not engine.supports_oov:
                invalid_inputs += ["유사도가이상한데", "새로지은달빛산책말"]
            for invalid in invalid_inputs:
                rejected = first.post("/api/guesses", json={"puzzle_date": day, "word": invalid})
                require(
                    rejected.status_code == 400
                    and rejected.json()["detail"]["code"] == "unrecognized_word",
                    "허용되지 않은 단어 거절 실패",
                )
            require(
                engine.vector.cache_info() == before_vectors,
                "거절한 입력으로 모델이 호출되었습니다.",
            )
            require(
                state(first)["game"]["attempts"] == 0 and state(first)["game"]["guesses"] == [],
                "거절한 입력이 시도/기록에 추가되었습니다.",
            )
            with db.connect() as conn:
                puzzle = conn.execute(
                    "SELECT answer, model_fingerprint FROM puzzles WHERE puzzle_date = %s", (day,)
                ).fetchone()
                require(
                    puzzle["model_fingerprint"] == engine.fingerprint,
                    "문제와 모델 fingerprint가 다릅니다.",
                )
                answer = puzzle["answer"]
            expected_index = engine.rankings(answer)
            require(
                initial["similarity_reference"]
                == {"ready": True, "error": None, **expected_index["reference"]},
                "API 기준 점수가 전체 어휘의 실제 순위 자료와 다릅니다.",
            )
            reference = initial["similarity_reference"]
            require(
                reference["top1"] >= reference["top10"] >= reference["top1000"],
                "실제 기준 점수의 순서가 잘못됐습니다.",
            )
            wrong = "산책" if answer != "산책" else "바다"
            if engine.supports_oov:
                # 입력 사전과 모델 단어 목록 모두에 없는 한글 조합을 실제 API에 제출합니다.
                wrong = next(
                    (
                        word
                        for word in (
                            "새로지은달빛산책말",
                            "초록구름산책냥",
                            "반짝달빛구름산책나들이말",
                        )
                        if word not in get_words() and engine.fasttext.word_id(word) == -1
                    ),
                    None,
                )
                require(
                    wrong is not None, "사전과 모델에 모두 없는 한글 검사 입력을 찾지 못했습니다."
                )
                require(engine.dimension == 300, "실제 fastText 모델의 차원 확인 실패")
            incorrect = post(first, "/api/guesses", {"puzzle_date": day, "word": wrong})
            score = incorrect["game"]["guesses"][0]["similarity"]
            require(math.isfinite(score) and -100 <= score <= 100, "실제 모델 점수 범위 확인 실패")
            require(
                math.isclose(score, engine.score(wrong, answer), rel_tol=0, abs_tol=1e-6),
                "API 점수가 실제 모델 계산과 다릅니다.",
            )
            a, b = engine.vector(wrong), engine.vector(answer)
            cosine = math.fsum(float(x) * float(y) for x, y in zip(a, b)) / math.sqrt(
                math.fsum(float(x) ** 2 for x in a) * math.fsum(float(x) ** 2 for x in b)
            )
            require(
                math.isclose(score, cosine * 100, rel_tol=0, abs_tol=0.0001),
                "실제 API 점수가 원래 코사인 유사도 × 100과 다릅니다.",
            )
            if engine.supports_oov:
                import numpy as np

                raw = engine.fasttext.get_word_vector(wrong)
                require(
                    len(a) == 300
                    and bool(np.isfinite(a).all())
                    and bool(np.array_equal(a, raw / np.linalg.norm(raw))),
                    "모델 미등록 입력의 실제 원본 bin 벡터 일치 확인 실패",
                )
            require(incorrect["game"]["status"] == "playing", "오답 이후 게임 상태 확인 실패")
            # OOV도 같은 고정 비교 사전의 원점수보다 높은 항목 수로 순위를 구합니다.
            calculated_rank = 1 + sum(
                float(value) > score for value in expected_index["sorted_scores"]
            )
            expected_wrong_rank = calculated_rank if calculated_rank <= 1000 else None
            require(
                rank_for_score(expected_index, wrong, score) == expected_wrong_rank,
                "실제 점수의 독립 비교 순위 계산 실패",
            )
            require(
                incorrect["game"]["guesses"][0]["similarity_rank"] == expected_wrong_rank,
                "API 입력 순위가 전체 어휘의 실제 순위와 다릅니다.",
            )
            require(
                incorrect["ranking"]["playing"][0]["best_similarity_rank"] == expected_wrong_rank,
                "랭킹의 최고 유사도 순위가 실제 입력 순위와 다릅니다.",
            )

            post(second, "/api/users", {"nickname": "검증한번"})
            second_started = post(second, "/api/start", {"puzzle_date": day})
            second_finished = post(second, "/api/guesses", {"puzzle_date": day, "word": answer})
            require(second_finished["game"]["status"] == "completed", "정답 판정 실패")
            require(
                second_finished["game"]["guesses"][0]["similarity_rank"] == 0,
                "정답의 별도 0위 표시 실패",
            )
            mixed = second_finished["ranking"]
            require(
                len(mixed["completed"]) == 1 and len(mixed["playing"]) == 1,
                "완료/도전 중 분리 실패",
            )
            require(
                mixed["playing"][0]["rank"] is None and mixed["playing"][0]["elapsed_ms"] is None,
                "도전 중 순위/완료 시간 표시 규칙 실패",
            )

            finished = post(first, "/api/guesses", {"puzzle_date": day, "word": answer})
            rows = finished["ranking"]["completed"]
            require(
                [row["user_id"] for row in rows]
                == [second_started["user"]["id"], first_started["user"]["id"]],
                "시도 횟수 우선 정렬 실패",
            )
            require(
                [row["attempts"] for row in rows] == [1, 2]
                and [row["rank"] for row in rows] == [1, 2],
                "시도 횟수/순위 확인 실패",
            )
            require(
                all(row["best_similarity_rank"] == 0 for row in rows),
                "완료자의 최고 유사도 순위 표시 실패",
            )
            require([row["is_me"] for row in rows] == [False, True], "첫 사용자 본인 표시 실패")
            require(
                [row["is_me"] for row in state(second)["ranking"]["completed"]] == [True, False],
                "두 번째 사용자 본인 표시 실패",
            )

            with TestClient(
                main.app, base_url="https://testserver", cookies=dict(first.cookies)
            ) as reconnect:
                restored = state(reconnect)
                require(
                    restored["user"] == finished["user"]
                    and restored["ranking"] == finished["ranking"],
                    "같은 쿠키로 재접속한 기록/랭킹 복원 실패",
                )
                require(restored["game"] == finished["game"], "재접속한 시간/입력 기록 복원 실패")
                duplicate = post(reconnect, "/api/guesses", {"puzzle_date": day, "word": wrong})
                require(
                    duplicate["duplicate"] is True and duplicate["ranking"] == finished["ranking"],
                    "중복 입력으로 순위가 바뀌었습니다.",
                )
                require(
                    duplicate["game"]["attempts"] == 2
                    and duplicate["game"]["elapsed_ms"] == finished["game"]["elapsed_ms"],
                    "중복 입력으로 횟수 또는 시간이 바뀌었습니다.",
                )
                require(duplicate["game"]["guesses"][0]["word"] == wrong, "중복 입력 재표시 실패")
                require(
                    duplicate["game"]["guesses"][0]["similarity_rank"] == expected_wrong_rank,
                    "중복 재표시의 실제 유사도 순위가 바뀌었습니다.",
                )
                require(
                    restored["similarity_reference"] == initial["similarity_reference"],
                    "재접속 후 기준 점수가 바뀌었습니다.",
                )
    finally:
        os.environ["DATABASE_URL"] = original_url
        # 사용자 입력으로 받은 이름이 아니라 위에서 생성한 스키마 하나만 삭제합니다.
        with psycopg.connect(original_url, autocommit=True) as admin:
            admin.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))

    input_result = (
        "fastText 사전·모델 미등록 입력 계산 및 형식 오류 차단"
        if engine.supports_oov
        else "미등록 입력 차단"
    )
    print(
        f"실제 모델 검사 통과: {input_result}·코사인×100·전체 어휘 순위/기준 점수·정답 0위·두 익명 사용자·랭킹·재접속·중복 불변·임시 스키마 정리"
    )


if __name__ == "__main__":
    try:
        run()
    except SmokeFailure as error:
        print(f"실제 모델 랭킹 검사 실패: {error}", file=sys.stderr)
        sys.exit(1)
    except Exception as error:
        # 연결 오류 등에 포함될 수 있는 비밀값이나 입력값을 콘솔에 노출하지 않습니다.
        print(
            f"실제 모델 랭킹 검사 실패: {type(error).__name__} (DB 연결·권한·모델 준비 상태를 확인하세요.)",
            file=sys.stderr,
        )
        sys.exit(1)
