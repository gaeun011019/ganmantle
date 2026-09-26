"""간맨틀 FastAPI 시작점. API와 빌드된 React 화면을 한 서버에서 제공합니다."""
import asyncio
import contextlib
import logging
import os
from contextlib import asynccontextmanager
from datetime import date
from pathlib import Path
from uuid import UUID

from fastapi import FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field
from psycopg import Error as DatabaseError

from . import db, game, users
from .chat import router as chat_router
from .similarity import get_engine

logger = logging.getLogger(__name__)


def close_all_expired():
    with db.connect() as conn:
        game.close_expired(conn, game.utcnow())


async def midnight_maintenance():
    while True:
        now = game.utcnow()
        await asyncio.sleep(max(0.1, (game.next_reset(now) - now).total_seconds()))
        try:
            await asyncio.to_thread(close_all_expired)
        except Exception:
            logger.exception("자정 기록 정리 실패: 다음 요청 또는 재시작 때 다시 처리합니다.")
            await asyncio.sleep(30)


@asynccontextmanager
async def lifespan(application: FastAPI):
    db.migrate()
    application.state.engine = get_engine()
    close_all_expired()
    maintenance = asyncio.create_task(midnight_maintenance())
    try:
        yield
    finally:
        maintenance.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await maintenance


app = FastAPI(title="간맨틀", lifespan=lifespan, docs_url="/api/docs", openapi_url="/api/openapi.json", redoc_url=None)


@app.middleware("http")
async def protect_origin(request: Request, call_next):
    if request.method in {"POST", "PUT", "PATCH", "DELETE"}:
        origin = request.headers.get("origin")
        allowed = os.getenv("APP_ORIGIN", "").rstrip("/") or f"{request.url.scheme}://{request.url.netloc}"
        if (origin and origin.rstrip("/") != allowed) or request.headers.get("sec-fetch-site") == "cross-site":
            return JSONResponse(status_code=403, content={"detail": {"code": "invalid_origin", "message": "이 주소에서의 요청은 허용하지 않아요."}})
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.exception_handler(RequestValidationError)
async def invalid_request(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"detail": {"code": "invalid_request", "message": "입력 형식이 맞지 않아요. 페이지를 새로고침한 뒤 다시 시도해 주세요."}})


class NicknameInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    nickname: str = Field(max_length=100)


class StartInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    puzzle_date: date


class GuessInput(StartInput):
    word: str = Field(max_length=200)


def fail(error: users.UserError):
    raise HTTPException(error.status, detail={"code": error.code, "message": error.message})


def current_engine(request: Request):
    return request.app.state.engine


@app.get("/api/health")
def health(request: Request):
    try:
        with db.connect() as conn:
            # 조회만 하며 문제나 사용자를 만들지 않습니다.
            model = game.model_status(conn, game.puzzle_date(game.utcnow()), current_engine(request))
    except DatabaseError as error:
        # 연결 문자열이나 SQL 오류 본문 대신 예외 타입만 기록합니다.
        logger.error("상태 검사 중 DB 확인 실패 (%s)", type(error).__name__)
        return JSONResponse(status_code=503, content={
            "status": "database_unavailable", "database": False,
            "message": "데이터베이스 상태를 확인하지 못했어요.",
        })
    if not model["ready"]:
        # Docker도 HTTP 상태로 게임 준비 실패를 감지합니다. 내부 경로는 공개하지 않습니다.
        return JSONResponse(status_code=503, content={
            "status": "model_unavailable", "database": True,
            "model": {**model, "error": "유사도 모델을 사용할 준비가 되지 않았어요."},
        })
    return {"status": "ok", "database": True, "model": model}


@app.get("/api/state")
def state(request: Request, puzzle_date: date | None = None):
    with db.connect() as conn:
        user = users.find_user(conn, request.cookies.get(users.COOKIE_NAME), lock=True)
        return game.state(conn, user, current_engine(request), puzzle_date)


@app.post("/api/users")
def set_nickname(payload: NicknameInput, request: Request, response: Response):
    try:
        with db.connect() as conn:
            user, new_token = users.register(conn, payload.nickname, request.cookies.get(users.COOKIE_NAME))
            result = game.state(conn, user, current_engine(request))
        if new_token:
            response.set_cookie(users.COOKIE_NAME, new_token, max_age=users.COOKIE_MAX_AGE,
                                httponly=True, samesite="lax", secure=os.getenv("COOKIE_SECURE", "false").lower() == "true", path="/")
        return result
    except users.UserError as error:
        fail(error)


@app.get("/api/related-words")
def related_words(request: Request, puzzle_date: date):
    try:
        with db.connect() as conn:
            user = users.require_user(conn, request.cookies.get(users.COOKIE_NAME))
            return game.related_words(conn, user, puzzle_date, current_engine(request))
    except users.UserError as error:
        fail(error)


@app.get("/api/ranking/{user_id}/guesses")
def friend_history(user_id: UUID, request: Request, puzzle_date: date):
    try:
        with db.connect() as conn:
            user = users.require_user(conn, request.cookies.get(users.COOKIE_NAME))
            return game.friend_history(conn, user, user_id, puzzle_date, current_engine(request))
    except users.UserError as error:
        fail(error)

def mutate(request: Request, operation, expected: date):
    error = None
    result = None
    user = None
    with db.connect() as conn:
        try:
            user = users.require_user(conn, request.cookies.get(users.COOKIE_NAME))
            duplicate = operation(conn, user, current_engine(request))
            result = game.state(conn, user, current_engine(request), expected)
            if duplicate is not None:
                result["duplicate"] = duplicate
        except users.UserError as caught:
            # 게임 오류 전 처리한 전날 마감은 커밋합니다. 실패한 입력은 아직 저장하지 않았습니다.
            if user:
                game.close_expired(conn, game.utcnow(), user["id"])
            error = caught
    if error:
        fail(error)
    return result


@app.post("/api/start")
def start(payload: StartInput, request: Request):
    return mutate(request, lambda conn, user, engine: game.start(conn, user, payload.puzzle_date, engine), payload.puzzle_date)


@app.post("/api/guesses")
def guess(payload: GuessInput, request: Request):
    submitted_at = game.utcnow()
    return mutate(request, lambda conn, user, engine: game.guess(conn, user, payload.puzzle_date, payload.word, engine, submitted_at), payload.puzzle_date)


app.include_router(chat_router)

# Docker에서는 화면을 먼저 빌드합니다. 개발 시 Vite가 /api 요청을 이 서버로 보냅니다.
frontend_dist = Path(os.getenv("FRONTEND_DIST", str(Path(__file__).resolve().parents[2] / "frontend" / "dist")))
if frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
