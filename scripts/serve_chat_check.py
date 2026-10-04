"""실제 브라우저 채팅 검사용 임시 서버. 기존 앱 DB에는 기록을 쓰지 않습니다.

Docker에서 8001 포트를 로컬로 연결해 실행하며 Ctrl+C/SIGTERM으로 종료합니다.
이번 실행에서 만든 무작위 PostgreSQL 스키마만 사용하고 종료 시 정리합니다.
앱의 실제 모델·API·화면을 그대로 사용합니다. 공개 운영용 서버가 아닙니다.
"""

import os
import signal
import sys
from pathlib import Path
from uuid import uuid4

import psycopg
import uvicorn
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend"))


def run():
    original_url = os.environ["DATABASE_URL"]
    schema = "ganmantle_chat_browser_" + uuid4().hex
    with psycopg.connect(original_url, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    try:
        os.environ["DATABASE_URL"] = make_conninfo(original_url, options=f"-c search_path={schema}")
        os.environ["COOKIE_SECURE"] = "false"
        os.environ.pop("APP_ORIGIN", None)
        from app.main import app

        # 본 앱에는 없는 검사 전용 표식. 브라우저 도구는 이것을 확인한 경우만 쓰기 검사합니다.
        def test_context():
            return {
                "isolated_chat_check": True,
                "instance": schema.removeprefix("ganmantle_chat_browser_"),
            }

        app.add_api_route("/api/test-context", test_context, methods=["GET"])
        app.router.routes.insert(0, app.router.routes.pop())

        # Uvicorn이 종료 신호를 원래 핸들러에 다시 전달해도 finally 정리가 실행되게 합니다.
        def stop(*_):
            raise KeyboardInterrupt

        signal.signal(signal.SIGTERM, stop)
        print("검사 전용 서버: 임시 스키마 사용, 종료 시 정리합니다.", flush=True)
        uvicorn.run(
            app,
            host="0.0.0.0",
            port=8001,
            workers=1,
            log_level="warning",
            access_log=False,
            timeout_graceful_shutdown=5,
        )
    finally:
        os.environ["DATABASE_URL"] = original_url
        with psycopg.connect(original_url, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
        print(
            "브라우저 검사 임시 스키마 정리 완료. 기존 앱 DB 기록은 사용하지 않았습니다.",
            flush=True,
        )


if __name__ == "__main__":
    try:
        run()
    except Exception as error:
        # DB 연결 문자열·쿠키·대화 내용이 오류 출력에 섞이지 않게 합니다.
        print(f"검사 서버 실패: {type(error).__name__}", file=sys.stderr)
        sys.exit(1)
