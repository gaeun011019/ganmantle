// 서버 요청과 응답 타입. 닉네임·시간·점수를 브라우저 저장값으로 만들지 않는다.
export type Guess = {
  word: string;
  similarity: number;
  similarity_rank: number | null;
  attempt: number;
  is_correct: boolean;
};
type RankingPlayer = {
  user_id: string;
  nickname: string;
  attempts: number;
  is_me: boolean;
  best_similarity: number | null;
  best_similarity_rank: number | null;
};
export type DailyRanking = {
  completed: (RankingPlayer & { elapsed_ms: number; rank: number })[];
  playing: (RankingPlayer & { elapsed_ms: null; rank: null })[];
};
export type PlayerStats = {
  first_played_date: string | null;
  games_played: number;
  games_completed: number;
  current_streak: number;
  games_incomplete: number;
  total_guesses: number;
};
export type RelatedWords = {
  puzzle_date: string;
  words: { word: string; similarity: number; rank: number }[];
};
export type PlayerGuessHistory = {
  puzzle_date: string;
  user: { id: string; nickname: string };
  status: 'playing' | 'completed';
  attempts: number;
  guesses: Guess[];
};
export type State = {
  server_now: string;
  puzzle_date: string;
  yesterday_answer: string | null;
  next_reset_at: string;
  user: { id: string; nickname: string } | null;
  player_stats: PlayerStats | null;
  game: {
    status: 'playing' | 'completed' | 'incomplete';
    started_at: string;
    completed_at: string | null;
    elapsed_ms: number;
    attempts: number;
    guesses: Guess[];
  } | null;
  model: {
    ready: boolean;
    name: string;
    error: string | null;
    scores_updated_at?: string | null;
    supports_oov?: boolean;
  };
  similarity_reference: {
    ready: boolean;
    error: string | null;
    vocabulary_size: number | null;
    top1: number | null;
    top10: number | null;
    top1000: number | null;
  };
  ranking: DailyRanking;
  date_changed?: boolean;
  duplicate?: boolean;
};
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}

type RequestOptions = {
  timeoutMs?: number;
  invalidResponseMessage?: string;
  failureCode?: string;
  failureMessage?: string;
};

export async function request<T = State>(
  path: string,
  body?: object,
  signal?: AbortSignal,
  {
    timeoutMs = 45000,
    invalidResponseMessage = '서버 응답을 확인할 수 없어요. 잠시 후 다시 연결해 주세요.',
    failureCode = 'request_failed',
    failureMessage = '요청을 처리하지 못했어요. 입력을 확인하고 다시 시도해 주세요.',
  }: RequestOptions = {},
): Promise<T> {
  // Safari에서도 요청 제한 시간과 호출한 화면의 취소를 함께 처리합니다.
  const controller = new AbortController();
  const timeout = setTimeout(
    () => controller.abort(new DOMException('Request timed out', 'TimeoutError')),
    timeoutMs,
  );
  const abortFromCaller = () => controller.abort(signal?.reason);
  if (signal?.aborted) {
    abortFromCaller();
  } else {
    signal?.addEventListener('abort', abortFromCaller, { once: true });
  }

  try {
    const response = await fetch(`/api${path}`, {
      method: body ? 'POST' : 'GET',
      credentials: 'same-origin',
      cache: 'no-store',
      headers: body ? { 'Content-Type': 'application/json' } : undefined,
      body: body ? JSON.stringify(body) : undefined,
      signal: controller.signal,
    });
    let data;
    try {
      data = await response.json();
    } catch {
      throw new ApiError(response.status, 'invalid_response', invalidResponseMessage);
    }
    if (!response.ok) {
      const detail = data.detail;
      throw new ApiError(
        response.status,
        detail?.code || failureCode,
        typeof detail?.message === 'string' ? detail.message : failureMessage,
      );
    }
    return data as T;
  } finally {
    clearTimeout(timeout);
    signal?.removeEventListener('abort', abortFromCaller);
  }
}
