"""PostgreSQL 연결과 순서가 있는 SQL 변경 이력 적용만 담당합니다."""

import hashlib
import os
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

MIGRATIONS = Path(__file__).resolve().parents[1] / "migrations"


def connect():
    """요청마다 짧은 연결을 사용합니다. with가 정상 종료되면 함께 커밋됩니다."""
    url = os.getenv("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL을 .env 또는 실행 환경에 설정하세요.")
    return psycopg.connect(url, row_factory=dict_row, connect_timeout=10)


def migrate():
    """이미 적용한 파일은 수정하지 않고 새 SQL 파일을 추가합니다."""
    with connect() as conn:
        # 여러 실행이 겹쳐도 같은 DB 변경을 중복 적용하지 않습니다.
        conn.execute("SELECT pg_advisory_xact_lock(71492601)")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_migrations (
                filename text PRIMARY KEY,
                sha256 text NOT NULL,
                applied_at timestamptz NOT NULL DEFAULT now()
            )
        """)
        for path in sorted(MIGRATIONS.glob("*.sql")):
            content = path.read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            applied = conn.execute(
                "SELECT sha256 FROM schema_migrations WHERE filename = %s",
                (path.name,),
            ).fetchone()
            if applied:
                if applied["sha256"] != digest:
                    raise RuntimeError(f"이미 적용된 DB 변경 파일이 수정되었습니다: {path.name}")
                continue
            conn.execute(content.decode("utf-8"))
            conn.execute(
                "INSERT INTO schema_migrations (filename, sha256) VALUES (%s, %s)",
                (path.name, digest),
            )
