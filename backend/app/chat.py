"""3단계 채팅: 방·초대·메시지는 PostgreSQL에, 다시 조회하라는 SSE 신호만 메모리에 둡니다."""
import asyncio
from datetime import UTC
import os
from threading import Lock
import unicodedata
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from . import db, users

HEARTBEAT_SECONDS = 15
MAX_MESSAGE_ID = 9223372036854775807


def error(code: str, message: str, status: int = 400):
    raise HTTPException(status, detail={"code": code, "message": message})


def check_origin(request: Request):
    """SSE는 GET이므로 기존 POST 보호와 별도로 같은 출처를 검사합니다."""
    origin = request.headers.get("origin")
    allowed = os.getenv("APP_ORIGIN", "").rstrip("/") or f"{request.url.scheme}://{request.url.netloc}"
    if (origin and origin.rstrip("/") != allowed) or request.headers.get("sec-fetch-site") == "cross-site":
        error("invalid_origin", "이 주소에서의 요청은 허용하지 않아요.", 403)


router = APIRouter(prefix="/api/chat", tags=["채팅"], dependencies=[Depends(check_origin)])


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class DirectInput(ChatInput):
    user_id: UUID


class RoomInput(ChatInput):
    name: str = Field(max_length=200)
    invitee_ids: list[UUID] = Field(default_factory=list, max_length=20)


class InvitationInput(ChatInput):
    user_id: UUID


class InvitationResponse(ChatInput):
    accept: bool = Field(strict=True)


class MessageInput(ChatInput):
    body: str = Field(max_length=4000)
    client_id: UUID


class RefreshHub:
    """한 프로세스의 접속 목록. sync API 스레드에서 각 SSE 이벤트 루프로 안전하게 알립니다."""
    def __init__(self):
        self._lock = Lock()
        self._subscribers: dict[str, dict[str, tuple[asyncio.AbstractEventLoop, asyncio.Queue]]] = {}

    def subscribe(self, user_id):
        loop = asyncio.get_running_loop()
        queue = asyncio.Queue(maxsize=1)
        subscription_id = uuid4().hex
        with self._lock:
            self._subscribers.setdefault(str(user_id), {})[subscription_id] = (loop, queue)
        return subscription_id, queue

    def unsubscribe(self, user_id, subscription_id):
        with self._lock:
            connections = self._subscribers.get(str(user_id))
            if connections is not None:
                connections.pop(subscription_id, None)
                if not connections:
                    self._subscribers.pop(str(user_id), None)

    def notify(self, user_ids=None):
        # 알림은 본문/방 ID 없는 새로고침 신호입니다. 느린 연결에는 한 개만 쌓습니다.
        with self._lock:
            recipients = list(self._subscribers) if user_ids is None else {str(value) for value in user_ids}
            connections = [(user_id, key, loop, queue)
                           for user_id in recipients
                           for key, (loop, queue) in self._subscribers.get(user_id, {}).items()]
        for user_id, subscription_id, loop, queue in connections:
            def enqueue(target=queue):
                if not target.full():
                    target.put_nowait(None)
            try:
                loop.call_soon_threadsafe(enqueue)
            except RuntimeError:  # 이미 닫힌 브라우저 이벤트 루프
                self.unsubscribe(user_id, subscription_id)


hub = RefreshHub()


def require_user(conn, request: Request):
    # 상대방을 참조하는 FK가 있으므로 게임의 사용자 FOR UPDATE 잠금을 재사용하지 않습니다.
    # A→B, B→A 동시 개인방 생성 때 서로의 사용자 잠금을 기다리는 교착을 피합니다.
    user = users.find_user(conn, request.cookies.get(users.COOKIE_NAME))
    if not user:
        error("nickname_required", "닉네임을 먼저 설정해 주세요.", 401)
    return user


ROOM_SELECT = """
    SELECT r.id, r.kind, r.owner_id,
           CASE WHEN r.kind = 'direct' THEN peer.nickname ELSE r.name END AS name
    FROM chat_rooms r
    LEFT JOIN users peer ON peer.id = CASE
        WHEN r.direct_user_low = %s THEN r.direct_user_high ELSE r.direct_user_low END
"""
MESSAGE_SELECT = """
    SELECT m.id, m.room_id, m.sender_id, u.nickname, m.body, m.created_at
    FROM chat_messages m JOIN users u ON u.id = m.sender_id
"""


def room_json(room):
    return {"id": str(room["id"]), "kind": room["kind"], "name": room["name"],
            "owner_id": str(room["owner_id"]) if room["owner_id"] else None}


def message_json(message):
    return {"id": str(message["id"]), "room_id": str(message["room_id"]),
            "sender_id": str(message["sender_id"]), "nickname": message["nickname"],
            "body": message["body"], "created_at": message["created_at"].astimezone(UTC).isoformat()}


def accessible_room(conn, room_id: UUID, user_id: UUID):
    room = conn.execute(ROOM_SELECT + """
        WHERE r.id = %s AND (r.kind = 'global' OR EXISTS (
            SELECT 1 FROM chat_members cm WHERE cm.room_id = r.id AND cm.user_id = %s
        ))
    """, (user_id, room_id, user_id)).fetchone()
    if not room:
        # 존재하지 않는 방과 권한 없는 방을 구별하지 않습니다.
        error("room_not_found", "대화방을 찾을 수 없어요.", 404)
    return room


def require_existing_user(conn, user_id: UUID):
    if not conn.execute("SELECT 1 FROM users WHERE id = %s", (user_id,)).fetchone():
        error("user_not_found", "사용자를 찾을 수 없어요.", 404)


def room_recipients(conn, room):
    if room["kind"] == "global":
        return None  # 전체 채팅은 현재 연결된 등록 사용자에게만 알립니다.
    return {str(row["user_id"]) for row in conn.execute(
        "SELECT user_id FROM chat_members WHERE room_id = %s", (room["id"],)).fetchall()}


def validate_name(raw: str):
    if not users.valid_text(raw):
        error("invalid_room_name", "방 이름은 제어 문자 없이 1~40자로 입력해 주세요.")
    name = users.normalize(raw)
    if not 1 <= len(name) <= 40:
        error("invalid_room_name", "방 이름은 제어 문자 없이 1~40자로 입력해 주세요.")
    return name


def validate_body(raw: str):
    # trim 전에 검사하여 양끝에 숨긴 탭/CR도 허용하지 않습니다. 일반 줄바꿈 LF만 허용합니다.
    if any(unicodedata.category(char).startswith("C") and char != "\n" for char in raw):
        error("invalid_message", "메시지에는 줄바꿈 외의 제어 문자를 사용할 수 없어요.")
    body = users.normalize(raw)
    if not 1 <= len(body) <= 1000:
        error("invalid_message", "메시지는 1~1000자로 입력해 주세요.")
    return body


def invite(conn, room_id: UUID, owner_id: UUID, invitee_id: UUID):
    """이미 참여/대기 중이면 그대로, 거절했던 사용자는 소유자가 다시 초대할 수 있습니다."""
    if invitee_id == owner_id:
        return False
    require_existing_user(conn, invitee_id)
    if conn.execute("SELECT 1 FROM chat_members WHERE room_id = %s AND user_id = %s",
                    (room_id, invitee_id)).fetchone():
        return False
    changed = conn.execute("""
        INSERT INTO chat_invitations (room_id, invitee_id, inviter_id)
        VALUES (%s, %s, %s)
        ON CONFLICT (room_id, invitee_id) DO UPDATE
        SET status = 'pending', inviter_id = EXCLUDED.inviter_id,
            created_at = clock_timestamp(), responded_at = NULL
        WHERE chat_invitations.status = 'declined'
        RETURNING invitee_id
    """, (room_id, invitee_id, owner_id)).fetchone()
    return changed is not None


@router.get("/rooms")
def list_rooms(request: Request):
    with db.connect() as conn:
        user = require_user(conn, request)
        rooms = conn.execute(ROOM_SELECT + """
            WHERE r.kind = 'global' OR EXISTS (
                SELECT 1 FROM chat_members cm WHERE cm.room_id = r.id AND cm.user_id = %s
            )
            ORDER BY CASE r.kind WHEN 'global' THEN 0 WHEN 'direct' THEN 1 ELSE 2 END,
                     r.created_at, r.id
        """, (user["id"], user["id"])).fetchall()
        invitations = conn.execute("""
            SELECT i.room_id, r.name AS room_name, u.nickname AS inviter_nickname
            FROM chat_invitations i JOIN chat_rooms r ON r.id = i.room_id
            JOIN users u ON u.id = i.inviter_id
            WHERE i.invitee_id = %s AND i.status = 'pending'
            ORDER BY i.created_at, i.room_id
        """, (user["id"],)).fetchall()
    return {"rooms": [room_json(room) for room in rooms],
            "invitations": [{**item, "room_id": str(item["room_id"])} for item in invitations]}


@router.get("/users")
def search_users(request: Request, q: str = Query(default="", max_length=100)):
    with db.connect() as conn:
        user = require_user(conn, request)
        query = users.normalize(q)
        if len(query) < 2:
            return {"users": []}
        if len(query) > 20 or not users.valid_text(query):
            error("invalid_search", "닉네임 검색어는 제어 문자 없이 2~20자로 입력해 주세요.")
        key = unicodedata.normalize("NFC", query.casefold())
        # strpos는 %, _를 와일드카드로 해석하지 않으며 SQL 값은 매개변수로 전달합니다.
        found = conn.execute("""
            SELECT id, nickname FROM users
            WHERE id <> %s AND strpos(nickname_key, %s) > 0
            ORDER BY nickname_key, id LIMIT 20
        """, (user["id"], key)).fetchall()
    return {"users": [{"id": str(item["id"]), "nickname": item["nickname"]} for item in found]}


@router.post("/direct")
def create_direct(payload: DirectInput, request: Request):
    recipients = set()
    with db.connect() as conn:
        user = require_user(conn, request)
        if payload.user_id == user["id"]:
            error("invalid_direct_user", "자기 자신과의 개인 대화는 만들 수 없어요.")
        require_existing_user(conn, payload.user_id)
        low, high = sorted((user["id"], payload.user_id))
        created = conn.execute("""
            INSERT INTO chat_rooms (id, kind, name, direct_user_low, direct_user_high)
            VALUES (%s, 'direct', '개인 대화', %s, %s)
            ON CONFLICT (direct_user_low, direct_user_high) DO NOTHING RETURNING id
        """, (uuid4(), low, high)).fetchone()
        if created:
            room_id = created["id"]
            conn.execute("INSERT INTO chat_members (room_id, user_id) VALUES (%s, %s), (%s, %s)",
                         (room_id, low, room_id, high))
            recipients = {str(low), str(high)}
        else:
            room_id = conn.execute("SELECT id FROM chat_rooms WHERE direct_user_low = %s AND direct_user_high = %s",
                                   (low, high)).fetchone()["id"]
        result = room_json(accessible_room(conn, room_id, user["id"]))
    # 다른 연결의 GET이 새 방을 읽을 수 있도록 커밋된 뒤에만 신호를 보냅니다.
    if recipients:
        hub.notify(recipients)
    return {"room": result}


@router.post("/rooms")
def create_room(payload: RoomInput, request: Request):
    with db.connect() as conn:
        user = require_user(conn, request)
        name = validate_name(payload.name)
        invitees = set(payload.invitee_ids) - {user["id"]}
        room_id = uuid4()
        conn.execute("INSERT INTO chat_rooms (id, kind, name, owner_id) VALUES (%s, 'group', %s, %s)",
                     (room_id, name, user["id"]))
        conn.execute("INSERT INTO chat_members (room_id, user_id) VALUES (%s, %s)", (room_id, user["id"]))
        # 대상 확인은 invite()에서 한 번만 합니다. 실패하면 방 생성도 함께 취소됩니다.
        for user_id in invitees:
            invite(conn, room_id, user["id"], user_id)
        result = room_json(accessible_room(conn, room_id, user["id"]))
        recipients = {str(value) for value in invitees | {user["id"]}}
    hub.notify(recipients)
    return {"room": result}


@router.post("/rooms/{room_id}/invitations")
def invite_user(room_id: UUID, payload: InvitationInput, request: Request):
    with db.connect() as conn:
        user = require_user(conn, request)
        room = accessible_room(conn, room_id, user["id"])
        if room["kind"] != "group":
            error("invalid_room_type", "단체방에서만 사람을 초대할 수 있어요.")
        if room["owner_id"] != user["id"]:
            error("invitation_forbidden", "방을 만든 사람만 초대할 수 있어요.", 403)
        changed = invite(conn, room_id, user["id"], payload.user_id)
    if changed:
        hub.notify({str(user["id"]), str(payload.user_id)})
    return {"ok": True}


@router.post("/invitations/{room_id}")
def respond_to_invitation(room_id: UUID, payload: InvitationResponse, request: Request):
    recipients = set()
    with db.connect() as conn:
        user = require_user(conn, request)
        invitation = conn.execute("""
            SELECT * FROM chat_invitations WHERE room_id = %s AND invitee_id = %s FOR UPDATE
        """, (room_id, user["id"])).fetchone()
        if not invitation:
            error("invitation_not_found", "초대를 찾을 수 없어요.", 404)
        wanted = "accepted" if payload.accept else "declined"
        if invitation["status"] != "pending":
            if invitation["status"] != wanted:
                error("invitation_closed", "이미 응답한 초대예요. 새로운 초대를 받아 주세요.", 409)
        else:
            if payload.accept:
                conn.execute("INSERT INTO chat_members (room_id, user_id) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                             (room_id, user["id"]))
            conn.execute("""
                UPDATE chat_invitations SET status = %s, responded_at = clock_timestamp()
                WHERE room_id = %s AND invitee_id = %s
            """, (wanted, room_id, user["id"]))
            recipients = {str(user["id"]), str(invitation["inviter_id"])}
            if payload.accept:
                recipients.update(str(item["user_id"]) for item in conn.execute(
                    "SELECT user_id FROM chat_members WHERE room_id = %s", (room_id,)).fetchall())
    if recipients:
        hub.notify(recipients)
    return {"ok": True}


@router.get("/rooms/{room_id}/messages")
def list_messages(room_id: UUID, request: Request,
                  before: str | None = Query(default=None, max_length=19, pattern=r"^[1-9][0-9]*$"),
                  limit: int = Query(default=50, ge=1, le=100)):
    cursor = int(before) if before is not None else None
    if cursor is not None and cursor > MAX_MESSAGE_ID:
        error("invalid_cursor", "이전 메시지 위치가 올바르지 않아요.", 422)
    with db.connect() as conn:
        user = require_user(conn, request)
        accessible_room(conn, room_id, user["id"])
        query = MESSAGE_SELECT + " WHERE m.room_id = %s"
        params = [room_id]
        if cursor is not None:
            query += " AND m.id < %s"
            params.append(cursor)
        query += " ORDER BY m.id DESC LIMIT %s"
        params.append(limit + 1)
        newest = conn.execute(query, params).fetchall()
    page = newest[:limit]
    next_before = str(page[-1]["id"]) if len(newest) > limit else None
    return {"messages": [message_json(item) for item in reversed(page)], "next_before": next_before}


@router.post("/rooms/{room_id}/messages")
def send_message(room_id: UUID, payload: MessageInput, request: Request):
    recipients = set()
    with db.connect() as conn:
        user = require_user(conn, request)
        room = accessible_room(conn, room_id, user["id"])
        body = validate_body(payload.body)
        inserted = conn.execute("""
            INSERT INTO chat_messages (room_id, sender_id, client_id, body)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (sender_id, client_id) DO NOTHING RETURNING id
        """, (room_id, user["id"], payload.client_id, body)).fetchone()
        if inserted:
            saved = conn.execute(MESSAGE_SELECT + " WHERE m.id = %s", (inserted["id"],)).fetchone()
            recipients = room_recipients(conn, room)
        else:
            saved = conn.execute(MESSAGE_SELECT + " WHERE m.sender_id = %s AND m.client_id = %s",
                                 (user["id"], payload.client_id)).fetchone()
            if saved["room_id"] != room_id or saved["body"] != body:
                error("message_conflict", "같은 전송 번호로 다른 메시지를 보낼 수 없어요.", 409)
        result = message_json(saved)
    if recipients is None or recipients:
        hub.notify(recipients)
    return {"message": result}


@router.get("/events")
async def events(request: Request):
    def authenticate():
        with db.connect() as conn:
            return str(require_user(conn, request)["id"])
    user_id = await asyncio.to_thread(authenticate)

    async def stream():
        subscription_id, queue = hub.subscribe(user_id)
        try:
            # 연결/재연결 시 놓친 신호가 있어도 DB 상태를 다시 읽게 합니다.
            yield "retry: 3000\nevent: refresh\ndata: {}\n\n"
            while not await request.is_disconnected():
                try:
                    await asyncio.wait_for(queue.get(), timeout=HEARTBEAT_SECONDS)
                except TimeoutError:
                    yield ": heartbeat\n\n"
                else:
                    yield "event: refresh\ndata: {}\n\n"
        finally:
            hub.unsubscribe(user_id, subscription_id)

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})
