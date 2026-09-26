-- 간맨틀 3단계: 대화방·참여자·초대·메시지. 기존 사용자와 게임 기록은 그대로 둡니다.
CREATE TABLE chat_rooms (
    id uuid PRIMARY KEY,
    kind text NOT NULL CHECK (kind IN ('global', 'direct', 'group')),
    name text NOT NULL CHECK (char_length(name) BETWEEN 1 AND 40),
    owner_id uuid REFERENCES users(id),
    direct_user_low uuid REFERENCES users(id),
    direct_user_high uuid REFERENCES users(id),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (direct_user_low, direct_user_high),
    CHECK (
        (kind = 'global' AND owner_id IS NULL AND direct_user_low IS NULL AND direct_user_high IS NULL)
        OR (kind = 'direct' AND owner_id IS NULL AND direct_user_low IS NOT NULL
            AND direct_user_high IS NOT NULL AND direct_user_low < direct_user_high)
        OR (kind = 'group' AND owner_id IS NOT NULL AND direct_user_low IS NULL AND direct_user_high IS NULL)
    )
);
CREATE UNIQUE INDEX chat_one_global_room_idx ON chat_rooms(kind) WHERE kind = 'global';

CREATE TABLE chat_members (
    room_id uuid NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
    user_id uuid NOT NULL REFERENCES users(id),
    joined_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (room_id, user_id)
);
CREATE INDEX chat_members_user_idx ON chat_members(user_id, room_id);

CREATE TABLE chat_invitations (
    room_id uuid NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
    invitee_id uuid NOT NULL REFERENCES users(id),
    inviter_id uuid NOT NULL REFERENCES users(id),
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'declined')),
    created_at timestamptz NOT NULL DEFAULT now(),
    responded_at timestamptz,
    PRIMARY KEY (room_id, invitee_id),
    CHECK (invitee_id <> inviter_id),
    CHECK ((status = 'pending') = (responded_at IS NULL))
);
CREATE INDEX chat_invitations_pending_idx ON chat_invitations(invitee_id, created_at) WHERE status = 'pending';

CREATE TABLE chat_messages (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    room_id uuid NOT NULL REFERENCES chat_rooms(id) ON DELETE CASCADE,
    sender_id uuid NOT NULL REFERENCES users(id),
    client_id uuid NOT NULL,
    body text NOT NULL CHECK (char_length(body) BETWEEN 1 AND 1000),
    created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (sender_id, client_id)
);
CREATE INDEX chat_messages_room_page_idx ON chat_messages(room_id, id DESC);

-- 전체 채팅에는 별도 가입 행을 만들지 않습니다. 안전한 세션이 있는 사용자 모두 접근합니다.
INSERT INTO chat_rooms (id, kind, name)
VALUES ('00000000-0000-0000-0000-000000000001', 'global', '전체 채팅');
