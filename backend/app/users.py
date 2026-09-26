"""닉네임과 익명 세션. 닉네임만으로 기존 기록에 접근할 수 없습니다."""
import hashlib
import secrets
import unicodedata
from uuid import uuid4
from psycopg.errors import UniqueViolation

COOKIE_NAME = "ganmantle_session"
COOKIE_MAX_AGE = 365 * 24 * 60 * 60

class UserError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status

def normalize(value: str) -> str:
    return unicodedata.normalize("NFC", value.strip())

def valid_text(value: str) -> bool:
    return not any(unicodedata.category(char).startswith("C") for char in value)

def session_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

def find_user(conn, token: str | None, *, lock: bool = False):
    if not token or len(token) > 128:
        return None
    return conn.execute(
        "SELECT id, nickname FROM users WHERE session_hash = %s" + (" FOR UPDATE" if lock else ""),
        (session_hash(token),),
    ).fetchone()

def require_user(conn, token: str | None):
    # 같은 사용자의 동시 시작/제출을 이 행 잠금으로 직렬화합니다.
    user = find_user(conn, token, lock=True)
    if not user:
        raise UserError("nickname_required", "닉네임을 먼저 설정해 주세요.", 401)
    return user

def register(conn, nickname: str, token: str | None):
    nickname = normalize(nickname)
    if not 2 <= len(nickname) <= 20 or not valid_text(nickname):
        raise UserError("invalid_nickname", "닉네임은 제어 문자 없이 2~20자로 입력해 주세요.")
    key = unicodedata.normalize("NFC", nickname.casefold())
    user = find_user(conn, token, lock=True)
    try:
        # 저장점 덕분에 중복 오류가 나도 바깥 연결에서 오류 응답을 구성할 수 있습니다.
        with conn.transaction():
            if user:
                conn.execute("UPDATE users SET nickname = %s, nickname_key = %s WHERE id = %s", (nickname, key, user["id"]))
                user["nickname"] = nickname
                return user, None
            new_token = secrets.token_urlsafe(32)
            user = conn.execute(
                "INSERT INTO users (id, nickname, nickname_key, session_hash) VALUES (%s, %s, %s, %s) RETURNING id, nickname",
                (uuid4(), nickname, key, session_hash(new_token)),
            ).fetchone()
            return user, new_token
    except UniqueViolation:
        raise UserError("nickname_taken", "이미 사용 중인 닉네임이에요. 다른 닉네임을 골라 주세요.", 409) from None
