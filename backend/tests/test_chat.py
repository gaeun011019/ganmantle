"""3단계 채팅을 익명 세션과 실제 PostgreSQL의 임시 스키마에서 검사합니다.

기존 runtime을 재사용합니다. 모델은 게임 규칙용 모형이며 운영 DB에는 쓰지 않습니다.
SSE 무한 스트림은 TestClient로 열지 않고 인증·Origin 거절과 미들웨어만 검사합니다.
실제 스트림 전달·재연결 검사는 별도의 실행 확인에서 구분합니다.
"""
import asyncio
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from fastapi import Request, Response
from fastapi.testclient import TestClient

from test_rules import runtime, begin, submit
from app import db, main


PREFIX = "/api/chat"
GLOBAL = "00000000-0000-0000-0000-000000000001"


def register(client, nickname):
    response = client.post("/api/users", json={"nickname": nickname})
    assert response.status_code == 200, response.text
    return response.json()["user"]


def rooms(client):
    response = client.get(f"{PREFIX}/rooms")
    assert response.status_code == 200, response.text
    return response.json()


def send(client, room_id, body, client_id=None):
    return client.post(f"{PREFIX}/rooms/{room_id}/messages", json={
        "body": body, "client_id": client_id or str(uuid4()),
    })


def messages(client, room_id=GLOBAL, **params):
    response = client.get(f"{PREFIX}/rooms/{room_id}/messages", params=params)
    assert response.status_code == 200, response.text
    return response.json()


def direct(client, user_id):
    response = client.post(f"{PREFIX}/direct", json={"user_id": user_id})
    assert response.status_code == 200, response.text
    return response.json()["room"]


def group(client, name, invitees=()):
    response = client.post(f"{PREFIX}/rooms", json={"name": name, "invitee_ids": list(invitees)})
    assert response.status_code == 200, response.text
    return response.json()["room"]


def decide(client, room_id, accept):
    return client.post(f"{PREFIX}/invitations/{room_id}", json={"accept": accept})


def invite(client, room_id, user_id):
    return client.post(f"{PREFIX}/rooms/{room_id}/invitations", json={"user_id": user_id})


def test_anonymous_visitors_cannot_read_search_send_or_stream(runtime):
    client, _, _ = runtime
    for path in ("rooms", "users", f"rooms/{GLOBAL}/messages", "events"):
        response = client.get(f"{PREFIX}/{path}")
        assert response.status_code == 401, (path, response.text)
    assert send(client, GLOBAL, "인증 없이 보내기").status_code == 401
    assert client.post(f"{PREFIX}/direct", json={"user_id": str(uuid4())}).status_code == 401


def test_global_chat_is_shared_and_keeps_html_as_plain_message_text(runtime):
    client, _, _ = runtime
    author = register(client, "전체대화작성자")
    with TestClient(main.app) as other:
        peer = register(other, "전체대화상대")
        for current in (client, other):
            visible = rooms(current)["rooms"]
            assert any(room["id"] == GLOBAL and room["kind"] == "global" for room in visible)
        body = '<img src=x onerror="alert(1)"> & <script>test</script>'
        first = send(client, GLOBAL, body)
        assert first.status_code == 200, first.text
        second = send(other, GLOBAL, "안녕하세요")
        assert second.status_code == 200, second.text
        saved = messages(other)["messages"]
        assert [message["body"] for message in saved] == [body, "안녕하세요"]
        assert [message["sender_id"] for message in saved] == [author["id"], peer["id"]]
        assert [message["nickname"] for message in saved] == [author["nickname"], peer["nickname"]]
        assert all(isinstance(message["id"], str) for message in saved)
        assert all(message["room_id"] == GLOBAL for message in saved)
        assert all(set(message) == {"id", "room_id", "sender_id", "nickname", "body", "created_at"} for message in saved)
        assert "session_hash" not in str(saved)
        assert client.cookies["ganmantle_session"] not in str(saved)


def test_direct_room_is_unique_for_user_pair_and_hidden_from_third_user(runtime):
    client, _, _ = runtime
    author = register(client, "개인대화작성자")
    with TestClient(main.app) as peer, TestClient(main.app) as outsider:
        target = register(peer, "개인대화상대")
        register(outsider, "개인대화외부인")
        first = direct(client, target["id"])
        assert first["kind"] == "direct"
        assert direct(client, target["id"])["id"] == first["id"]
        assert direct(peer, author["id"])["id"] == first["id"]
        assert send(client, first["id"], "두 사람만 읽는 내용").status_code == 200
        assert messages(peer, first["id"])["messages"][0]["body"] == "두 사람만 읽는 내용"
        assert first["id"] not in {room["id"] for room in rooms(outsider)["rooms"]}
        assert outsider.get(f"{PREFIX}/rooms/{first['id']}/messages").status_code == 404
        assert send(outsider, first["id"], "침입").status_code == 404


def test_simultaneous_direct_creation_from_both_users_creates_one_room(runtime):
    client, _, _ = runtime
    author = register(client, "동시개인작성자")
    with TestClient(main.app) as peer:
        target = register(peer, "동시개인상대")
        requests = [(client, target["id"]), (peer, author["id"])] * 2
        with ThreadPoolExecutor(max_workers=4) as pool:
            created = list(pool.map(lambda request: direct(*request), requests))
        assert len({room["id"] for room in created}) == 1
        assert len([room for room in rooms(client)["rooms"] if room["kind"] == "direct"]) == 1
        assert len([room for room in rooms(peer)["rooms"] if room["kind"] == "direct"]) == 1


def test_group_invitation_requires_acceptance_and_only_recipient_can_accept(runtime):
    client, _, _ = runtime
    owner = register(client, "그룹방장")
    with TestClient(main.app) as member, TestClient(main.app) as outsider:
        target = register(member, "그룹초대상대")
        stranger = register(outsider, "그룹외부인")
        room = group(client, "함께 푸는 방", [target["id"]])
        room_id = room["id"]
        assert room["kind"] == "group" and room["owner_id"] == owner["id"]
        assert send(client, room_id, "초대 전 대화").status_code == 200
        pending = rooms(member)
        assert room_id not in {item["id"] for item in pending["rooms"]}
        invitation = next(item for item in pending["invitations"] if item["room_id"] == room_id)
        assert invitation["room_name"] == "함께 푸는 방"
        assert invitation["inviter_nickname"] == owner["nickname"]
        assert member.get(f"{PREFIX}/rooms/{room_id}/messages").status_code == 404
        assert send(member, room_id, "아직 미수락").status_code == 404
        assert decide(outsider, room_id, True).status_code == 404
        assert decide(member, room_id, True).status_code == 200
        assert room_id in {item["id"] for item in rooms(member)["rooms"]}
        assert room_id not in {item["room_id"] for item in rooms(member)["invitations"]}
        assert messages(member, room_id)["messages"][0]["body"] == "초대 전 대화"
        assert send(member, room_id, "수락한 뒤 대화").status_code == 200
        assert invite(member, room_id, stranger["id"]).status_code in {403, 404}
        assert invite(client, room_id, stranger["id"]).status_code == 200
        assert decide(outsider, room_id, True).status_code == 200
        assert len(messages(outsider, room_id)["messages"]) == 2


def test_declined_invitation_does_not_grant_membership_and_can_be_reinvited(runtime):
    client, _, _ = runtime
    register(client, "재초대방장")
    with TestClient(main.app) as other:
        target = register(other, "초대거절상대")
        room_id = group(client, "다음에 참가", [target["id"]])["id"]
        assert decide(other, room_id, False).status_code == 200
        current = rooms(other)
        assert room_id not in {room["id"] for room in current["rooms"]}
        assert room_id not in {item["room_id"] for item in current["invitations"]}
        assert other.get(f"{PREFIX}/rooms/{room_id}/messages").status_code == 404
        assert send(other, room_id, "거절 뒤 전송").status_code == 404
        assert decide(other, room_id, False).status_code == 200
        assert decide(other, room_id, True).status_code == 409
        assert invite(client, room_id, target["id"]).status_code == 200
        assert decide(other, room_id, True).status_code == 200
        assert decide(other, room_id, True).status_code == 200
        assert decide(other, room_id, False).status_code == 409
        assert send(other, room_id, "재초대 수락").status_code == 200


def test_message_normalization_length_and_control_character_validation(runtime):
    client, _, _ = runtime
    register(client, "본문검증")
    for body in ("", " \n ", "가" * 1001, "가\x00나", "가\x01나", "가\x7f나", "가\t나"):
        rejected = send(client, GLOBAL, body)
        assert rejected.status_code in {400, 422}, (repr(body), rejected.text)
    assert messages(client)["messages"] == []
    expected = "한글\n줄바꿈"
    normalized = send(client, GLOBAL, "  " + unicodedata.normalize("NFD", expected) + "  ")
    assert normalized.status_code == 200, normalized.text
    assert normalized.json()["message"]["body"] == expected
    boundary = send(client, GLOBAL, "가" * 1000)
    assert boundary.status_code == 200, boundary.text
    assert len(messages(client)["messages"]) == 2


def test_invalid_identifiers_search_and_client_forged_fields_are_rejected(runtime):
    client, _, _ = runtime
    register(client, "검색검증작성자")
    with TestClient(main.app) as other:
        target = register(other, "검색상대고유이름")
        found = client.get(f"{PREFIX}/users", params={"q": "상대고유"})
        assert found.status_code == 200, found.text
        assert any(user == target for user in found.json()["users"])
        assert all(set(user) == {"id", "nickname"} for user in found.json()["users"])
        injection = client.get(f"{PREFIX}/users", params={"q": "' OR 1=1 --"})
        assert injection.status_code == 200, injection.text
        assert injection.json()["users"] == []
    for path in ("rooms/not-a-uuid/messages",):
        assert client.get(f"{PREFIX}/{path}").status_code == 422
    assert client.post(f"{PREFIX}/direct", json={"user_id": "not-a-uuid"}).status_code == 422
    assert send(client, GLOBAL, "유효하지 않은 전송번호", "not-a-uuid").status_code == 422
    forged = client.post(f"{PREFIX}/rooms/{GLOBAL}/messages", json={
        "body": "다른 작성자 사칭", "client_id": str(uuid4()), "sender_id": str(uuid4()),
    })
    assert forged.status_code == 422
    assert messages(client)["messages"] == []


def test_room_and_history_bounds_reject_invalid_requests(runtime):
    client, _, _ = runtime
    register(client, "범위검증")
    for name in ("", "   ", "가" * 41):
        response = client.post(f"{PREFIX}/rooms", json={"name": name, "invitee_ids": []})
        assert response.status_code in {400, 422}, response.text
    too_many = client.post(f"{PREFIX}/rooms", json={
        "name": "초대 인원 제한", "invitee_ids": [str(uuid4()) for _ in range(21)],
    })
    assert too_many.status_code == 422
    missing_user = client.post(f"{PREFIX}/rooms", json={
        "name": "없는 사용자 초대", "invitee_ids": [str(uuid4())],
    })
    assert missing_user.status_code == 404
    assert [room["kind"] for room in rooms(client)["rooms"]] == ["global"]
    for query in ({"limit": 0}, {"limit": 101}, {"before": "abc"}, {"before": 0},
                  {"before": -1}, {"before": str(2 ** 63)}):
        response = client.get(f"{PREFIX}/rooms/{GLOBAL}/messages", params=query)
        assert response.status_code == 422, (query, response.text)
    for query in ("", "한"):
        response = client.get(f"{PREFIX}/users", params={"q": query})
        assert response.status_code == 200
        assert response.json()["users"] == []


def test_concurrent_retries_are_idempotent_and_conflicting_reuse_is_rejected(runtime):
    client, _, _ = runtime
    register(client, "전송중복작성자")
    client_id = str(uuid4())
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses = list(pool.map(lambda _: send(client, GLOBAL, "한 번만 저장", client_id), range(4)))
    assert all(response.status_code == 200 for response in responses), [response.text for response in responses]
    assert len({response.json()["message"]["id"] for response in responses}) == 1
    assert len(messages(client)["messages"]) == 1
    assert send(client, GLOBAL, "같은 번호로 다른 내용", client_id).status_code == 409
    with TestClient(main.app) as other:
        target = register(other, "전송중복상대")
        room_id = direct(client, target["id"])["id"]
        assert send(client, room_id, "한 번만 저장", client_id).status_code == 409
        assert messages(client, room_id)["messages"] == []
        # 다른 작성자는 자신의 전송 번호를 독립적으로 사용할 수 있습니다.
        assert send(other, GLOBAL, "다른 작성자의 같은 번호", client_id).status_code == 200
    assert len(messages(client)["messages"]) == 2


def test_history_cursor_keeps_every_message_in_stable_order(runtime):
    client, _, _ = runtime
    register(client, "더보기검증")
    expected_ids = []
    for index in range(7):
        response = send(client, GLOBAL, f"기록 {index}")
        assert response.status_code == 200
        expected_ids.append(response.json()["message"]["id"])
    collected = []
    before = None
    for page_number in range(4):
        result = messages(client, limit=3, **({"before": before} if before else {}))
        page = result["messages"]
        ids = [item["id"] for item in page]
        assert ids == sorted(ids, key=int)
        assert len(ids) <= 3
        assert not set(ids).intersection(collected)
        collected = ids + collected
        next_before = result["next_before"]
        if next_before is None:
            break
        assert isinstance(next_before, str)
        assert next_before == ids[0]
        if before is not None:
            assert int(next_before) < int(before)
        before = next_before
    else:
        raise AssertionError("과거 기록 커서가 끝나지 않았습니다.")
    assert page_number == 2
    assert collected == expected_ids


def test_reconnect_and_application_lifespan_restart_preserve_chat(runtime):
    client, _, _ = runtime
    register(client, "재접속작성자")
    with TestClient(main.app) as other:
        target = register(other, "재접속상대")
        room_id = direct(client, target["id"])["id"]
        assert send(client, GLOBAL, "전체 기록 유지").status_code == 200
        assert send(client, room_id, "개인 기록 유지").status_code == 200
        original_rooms = rooms(client)
        global_history = messages(client)
        direct_history = messages(client, room_id)
        # 새 TestClient는 앱 lifespan/migration을 다시 실행하며 동일 DB를 조회합니다.
        # 운영체제 프로세스 재시작 자체를 검증하는 테스트는 아닙니다.
        with TestClient(main.app, cookies=dict(client.cookies)) as reconnect:
            assert rooms(reconnect) == original_rooms
            assert messages(reconnect) == global_history
            assert messages(reconnect, room_id) == direct_history


def test_chat_never_changes_game_answer_attempts_timer_or_ranking(runtime):
    client, clock, _ = runtime
    day, _ = begin(client, "게임보존작성자")
    assert submit(client, day, "산책").status_code == 200
    with TestClient(main.app) as other:
        _, target = begin(other, "게임보존상대")
        clock["now"] += timedelta(seconds=12)
        assert submit(other, day, "사과").status_code == 200
        state_before = client.get("/api/state").json()
        with db.connect() as conn:
            records_before = {table: conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                              for table in ("puzzles", "games", "guesses")}
        assert send(client, GLOBAL, "게임과 별개의 대화").status_code == 200
        direct_room = direct(client, target["user"]["id"])
        assert send(other, direct_room["id"], "개인 대화").status_code == 200
        group_room = group(client, "게임 보존 방", [target["user"]["id"]])
        assert decide(other, group_room["id"], True).status_code == 200
        assert send(other, group_room["id"], "방 대화").status_code == 200
        assert client.get("/api/state").json() == state_before
        with db.connect() as conn:
            records_after = {table: conn.execute(f"SELECT * FROM {table} ORDER BY 1").fetchall()
                             for table in ("puzzles", "games", "guesses")}
        assert records_after == records_before


def test_chat_rejects_cross_origin_requests_including_sse(runtime, monkeypatch):
    client, _, _ = runtime
    register(client, "출처검증")
    for path in ("rooms", "users", f"rooms/{GLOBAL}/messages", "events"):
        for headers in ({"origin": "https://another.example"}, {"sec-fetch-site": "cross-site"}):
            response = client.get(f"{PREFIX}/{path}", headers=headers)
            assert response.status_code == 403, (path, response.text)
    rejected = client.post(f"{PREFIX}/rooms/{GLOBAL}/messages", json={
        "body": "외부 전송", "client_id": str(uuid4()),
    }, headers={"origin": "https://another.example"})
    assert rejected.status_code == 403
    accepted = client.post(f"{PREFIX}/rooms/{GLOBAL}/messages", json={
        "body": "같은 출처 전송", "client_id": str(uuid4()),
    }, headers={"origin": "http://testserver"})
    assert accepted.status_code == 200, accepted.text
    monkeypatch.setenv("APP_ORIGIN", "https://ganmantle.example")
    assert client.get(f"{PREFIX}/rooms", headers={"origin": "http://testserver"}).status_code == 403
    assert client.get(f"{PREFIX}/rooms", headers={"origin": "https://ganmantle.example"}).status_code == 200

    # 정상 SSE를 열면 테스트가 끝나지 않으므로 허용 출처의 미들웨어 통과만 별도 검사합니다.
    async def allowed_sse_passes_middleware():
        called = []
        request = Request({
            "type": "http", "method": "GET", "path": f"{PREFIX}/events",
            "scheme": "https", "server": ("ganmantle.example", 443),
            "query_string": b"", "headers": [(b"origin", b"https://ganmantle.example")],
        })

        async def next_handler(received):
            called.append(received.url.path)
            return Response("stream placeholder", media_type="text/event-stream")

        response = await main.protect_origin(request, next_handler)
        assert response.status_code == 200
        assert called == [f"{PREFIX}/events"]
        assert response.headers["Cache-Control"] == "no-store"

    asyncio.run(allowed_sse_passes_middleware())
