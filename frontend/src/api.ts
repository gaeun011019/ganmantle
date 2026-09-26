// 서버 요청과 응답 타입. 닉네임·시간·점수를 브라우저 저장값으로 만들지 않는다.
export type Guess = { word: string; similarity: number; similarity_rank: number | null; attempt: number; is_correct: boolean };
type RankingPlayer = {
  user_id: string; nickname: string; attempts: number; is_me: boolean;
  best_similarity: number | null;
  best_similarity_rank: number | null;
};
export type DailyRanking = {
  completed: (RankingPlayer & { elapsed_ms: number; rank: number })[];
  playing: (RankingPlayer & { elapsed_ms: null; rank: null })[];
};
export type State = {
  server_now: string;
  puzzle_date: string;
  yesterday_answer: string | null;
  next_reset_at: string;
  user: { id: string; nickname: string } | null;
  game: {
    status: 'playing' | 'completed' | 'incomplete';
    started_at: string; completed_at: string | null; elapsed_ms: number;
    attempts: number; guesses: Guess[];
  } | null;
  model: { ready: boolean; name: string; error: string | null; scores_updated_at?: string | null; supports_oov?: boolean };
  similarity_reference: {
    ready: boolean; error: string | null; vocabulary_size: number | null;
    top1: number | null; top10: number | null; top1000: number | null;
  };
  ranking: DailyRanking;
  date_changed?: boolean;
  duplicate?: boolean;
};
export class ApiError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
export async function request(path: string, body?: object): Promise<State> {
  const response = await fetch(`/api${path}`, {
    method: body ? 'POST' : 'GET', credentials: 'same-origin', cache: 'no-store',
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
    signal: AbortSignal.timeout(45000),
  });
  let data;
  try { data = await response.json(); }
  catch { throw new ApiError(response.status, 'invalid_response', '서버 응답을 확인할 수 없어요. 잠시 후 다시 연결해 주세요.'); }
  if (!response.ok) {
    const detail = data.detail;
    throw new ApiError(response.status, detail?.code || 'request_failed',
      typeof detail?.message === 'string' ? detail.message : '요청을 처리하지 못했어요. 입력을 확인하고 다시 시도해 주세요.');
  }
  return data as State;
}
