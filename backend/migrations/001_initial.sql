-- 간맨틀 1단계: 익명 사용자, 날짜별 고정 정답, 도전, 중복 없는 입력 기록.
CREATE TABLE users (
    id uuid PRIMARY KEY,
    nickname text NOT NULL,
    nickname_key text NOT NULL UNIQUE,
    session_hash text NOT NULL UNIQUE,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE puzzles (
    puzzle_date date PRIMARY KEY,
    answer text NOT NULL,
    model_fingerprint text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE games (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id uuid NOT NULL REFERENCES users(id),
    puzzle_date date NOT NULL REFERENCES puzzles(puzzle_date),
    status text NOT NULL DEFAULT 'playing' CHECK (status IN ('playing', 'completed', 'incomplete')),
    started_at timestamptz NOT NULL,
    completed_at timestamptz,
    closed_at timestamptz,
    attempts integer NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    display_revision bigint NOT NULL DEFAULT 0 CHECK (display_revision >= 0),
    UNIQUE (user_id, puzzle_date),
    CHECK ((status = 'completed') = (completed_at IS NOT NULL)),
    CHECK ((status = 'incomplete') = (closed_at IS NOT NULL)),
    CHECK (completed_at IS NULL OR completed_at >= started_at),
    CHECK (closed_at IS NULL OR closed_at >= started_at)
);
CREATE TABLE guesses (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    game_id bigint NOT NULL REFERENCES games(id),
    word text NOT NULL,
    similarity double precision NOT NULL CHECK (similarity BETWEEN -100 AND 100),
    attempt integer NOT NULL CHECK (attempt > 0),
    is_correct boolean NOT NULL,
    submitted_at timestamptz NOT NULL,
    last_display_order bigint NOT NULL,
    UNIQUE (game_id, word),
    UNIQUE (game_id, attempt)
);
CREATE INDEX games_open_date_idx ON games(puzzle_date) WHERE status = 'playing';
