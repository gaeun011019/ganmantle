// 기본 게임 화면. 규칙과 기록은 서버가 결정하고, 이 파일은 표시와 입력을 담당한다.
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type KeyboardEvent,
} from 'react';
import { ApiError, request, type Guess, type State } from './api';
import CompletionPanel from './CompletionPanel';
import Ranking from './ranking/Ranking';
import WordRank from './ranking/WordRank';
import ChatPanel from './chat/ChatPanel';
import type { ChatUser } from './chat/api';

const DATE_KEY = 'ganmantle:last-puzzle-date';
function savedDate(): string | null {
  try {
    return localStorage.getItem(DATE_KEY);
  } catch {
    return null;
  }
}
function errorMessage(error: unknown): string {
  return error instanceof ApiError ? error.message : '서버에 연결할 수 없어요. 다시 시도해 주세요.';
}
// 한글 조합을 확정하는 Enter가 곧바로 폼 제출로 이어지지 않게 한다.
function keepImeInput(event: KeyboardEvent<HTMLInputElement>) {
  if (event.key === 'Enter' && (event.nativeEvent.isComposing || event.nativeEvent.keyCode === 229))
    event.preventDefault();
}
export default function App() {
  const [state, setState] = useState<State | null>(null);
  const [chatContact, setChatContact] = useState<ChatUser | null>(null);
  const [nickname, setNickname] = useState('');
  const [word, setWord] = useState('');
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [offline, setOffline] = useState(!navigator.onLine);
  const [error, setError] = useState('');
  const [wordNotice, setWordNotice] = useState('');
  const focusAfterReject = useRef(false);
  const [, checkDate] = useState(0);
  const dateHint = useRef(savedDate());
  const anchor = useRef({ at: performance.now(), resetAfter: Infinity });
  const revision = useRef(0);
  const mutating = useRef(false);
  const refreshing = useRef(false);
  const input = useRef<HTMLInputElement>(null);
  const channel = useRef<BroadcastChannel | null>(null);

  const accept = useCallback((next: State) => {
    if (next.date_changed || (dateHint.current && dateHint.current !== next.puzzle_date)) {
      setWord('');
      setWordNotice('');
    }
    dateHint.current = next.puzzle_date;
    try {
      localStorage.setItem(DATE_KEY, next.puzzle_date);
    } catch {
      /* 저장 차단 시에도 서버 기록으로 게임한다. */
    }
    // 기기 시계 변경과 무관하게 서버 기준의 자정 전환을 확인합니다.
    anchor.current = {
      at: performance.now(),
      resetAfter: Math.max(0, Date.parse(next.next_reset_at) - Date.parse(next.server_now)),
    };
    setState(next);
  }, []);

  const refresh = useCallback(async () => {
    if (refreshing.current || mutating.current || !navigator.onLine) {
      setLoading(false);
      return;
    }
    refreshing.current = true;
    const requestRevision = ++revision.current;
    const date = dateHint.current;
    try {
      const next = await request(`/state${date ? `?puzzle_date=${encodeURIComponent(date)}` : ''}`);
      // 늦게 도착한 조회가 더 최근의 입력 결과를 덮어쓰지 않게 한다.
      if (requestRevision === revision.current && !mutating.current) {
        accept(next);
        setError('');
      }
    } catch (cause) {
      if (requestRevision === revision.current) setError(errorMessage(cause));
    } finally {
      refreshing.current = false;
      setLoading(false);
    }
  }, [accept]);

  useEffect(() => {
    void refresh();
    // 랭킹 조회는 30초마다 하고, 입력·탭 복귀·재접속은 즉시 반영합니다.
    const poll = window.setInterval(() => {
      if (!document.hidden) void refresh();
    }, 30000);
    const onFocus = () => {
      if (!document.hidden) void refresh();
    };
    const onOnline = () => {
      setOffline(false);
      void refresh();
    };
    const onOffline = () => setOffline(true);
    window.addEventListener('focus', onFocus);
    window.addEventListener('online', onOnline);
    window.addEventListener('offline', onOffline);
    document.addEventListener('visibilitychange', onFocus);
    if ('BroadcastChannel' in window) {
      channel.current = new BroadcastChannel('ganmantle:changed');
      channel.current.onmessage = () => void refresh();
    }
    return () => {
      window.clearInterval(poll);
      window.removeEventListener('focus', onFocus);
      window.removeEventListener('online', onOnline);
      window.removeEventListener('offline', onOffline);
      document.removeEventListener('visibilitychange', onFocus);
      channel.current?.close();
    };
  }, [refresh]);

  useEffect(() => {
    if (!state) return;
    // 숨긴 경과 시간을 위해 화면 전체를 반복 렌더링하지 않고 서버 자정에 한 번 확인합니다.
    const remaining = anchor.current.resetAfter - (performance.now() - anchor.current.at);
    const timer = window.setTimeout(() => checkDate((n) => n + 1), Math.max(0, remaining) + 1);
    return () => window.clearTimeout(timer);
  }, [state]);

  const dateDue =
    state !== null && performance.now() - anchor.current.at >= anchor.current.resetAfter;
  useEffect(() => {
    if (dateDue) void refresh();
  }, [dateDue, refresh]);
  useEffect(() => {
    if (!busy && focusAfterReject.current) {
      focusAfterReject.current = false;
      input.current?.focus();
    }
  }, [busy]);

  async function mutate(path: string, body: object): Promise<boolean> {
    if (mutating.current || !navigator.onLine) return false;
    mutating.current = true;
    ++revision.current;
    setBusy(true);
    setError('');
    if (path === '/guesses') setWordNotice('');
    let success = false;
    let reconcile = false;
    try {
      const next = await request(path, body);
      accept(next);
      channel.current?.postMessage('changed');
      success = true;
    } catch (cause) {
      if (
        path === '/guesses' &&
        cause instanceof ApiError &&
        ['invalid_word', 'unrecognized_word'].includes(cause.code)
      ) {
        setWord('');
        setWordNotice(cause.message);
        focusAfterReject.current = true;
      } else {
        // 날짜가 바뀐 경우에는 별도 배너 없이 새 문제를 불러옵니다.
        if (!(cause instanceof ApiError && cause.code === 'date_changed'))
          setError(errorMessage(cause));
        // 응답을 놓쳤어도 서버가 처리했을 수 있다. 다시 조회하여 저장된 결과를 확인한다.
        reconcile = true;
      }
    } finally {
      if (reconcile) {
        const date = dateHint.current;
        try {
          accept(await request(`/state${date ? `?puzzle_date=${encodeURIComponent(date)}` : ''}`));
        } catch {
          /* 원래 오류를 유지하고 다음 재접속에서 다시 조회한다. */
        }
      }
      // 오류 뒤 상태 확인까지 한 요청으로 취급하여 늦은 조회와 새 입력의 경합을 막는다.
      mutating.current = false;
      setBusy(false);
    }
    return success;
  }

  async function createUser(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    await mutate('/users', { nickname: nickname.trim().normalize('NFC') });
  }
  async function start() {
    if (!state) return;
    if (await mutate('/start', { puzzle_date: state.puzzle_date }))
      requestAnimationFrame(() => input.current?.focus());
  }
  async function guess(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!state || !word.trim() || dateDue || busy) return;
    const submitted = word.trim().normalize('NFC');
    if (await mutate('/guesses', { puzzle_date: state.puzzle_date, word: submitted })) {
      setWord('');
      requestAnimationFrame(() => input.current?.focus());
    }
  }

  const game = state?.game;
  const completed = game?.status === 'completed';
  const playing = game?.status === 'playing';
  const disabled = busy || offline || dateDue;
  const correct = game?.guesses.find((item) => item.is_correct);
  // 날짜는 기기 시계로 계산하지 않고 서버의 한국 날짜를 그대로 표시합니다.
  const dateParts = state?.puzzle_date.split('-');
  const formattedDate = dateParts
    ? `${dateParts[0]}년 ${Number(dateParts[1])}월 ${Number(dateParts[2])}일`
    : '';
  const similarityReference = state?.similarity_reference;
  const wordRanksReady = similarityReference?.ready === true;
  const referenceScore = (value: number | null | undefined) =>
    wordRanksReady && typeof value === 'number' ? value.toFixed(2) : '—';
  const latestGuess = game?.guesses[0];
  // 서버의 최근 입력 순서는 보존하고, 최근 한 행을 제외한 복사본만 점수순으로 정렬합니다.
  const previousGuesses =
    game?.guesses.slice(1).sort((a, b) => b.similarity - a.similarity || a.attempt - b.attempt) ||
    [];
  const guessRow = (item: Guess, recent = false) => (
    <tr key={item.word} className={item.is_correct ? 'correct-row' : recent ? 'recent-row' : ''}>
      <td className="attempt">{item.attempt}</td>
      <th scope="row" className="guess-word">
        {item.word}
        {item.is_correct && <span className="correct-label">정답</span>}
      </th>
      <td className="score">{item.similarity.toFixed(2)}</td>
      <td>
        <WordRank rank={item.similarity_rank} ready={wordRanksReady} bar />
      </td>
    </tr>
  );

  return (
    <>
      <header className="site-header">
        <a className="brand" href="/" aria-label="간맨틀 홈">
          <img src="/brand-mark.svg" alt="" width="52" height="52" />
          <span>간맨틀</span>
        </a>
      </header>
      <main>
        <section className="game-card" aria-labelledby="game-title">
          <div className="similarity-reference" aria-label="정답을 제외한 사전 단어의 기준 유사도">
            <span className="reference-title">기준 유사도 (%)</span>
            <span className="reference-item">
              <span>1위</span>
              <strong data-reference-rank="1">{referenceScore(similarityReference?.top1)}</strong>
            </span>
            <span className="reference-item">
              <span>10위</span>
              <strong data-reference-rank="10">{referenceScore(similarityReference?.top10)}</strong>
            </span>
            <span className="reference-item">
              <span>1,000위</span>
              <strong data-reference-rank="1000">
                {referenceScore(similarityReference?.top1000)}
              </strong>
            </span>
          </div>
          {state && !wordRanksReady && (
            <p className="reference-status" role="status">
              {similarityReference?.error ||
                '단어 유사도 순위 기준을 불러오지 못했어요. 잠시 후 다시 확인해 주세요.'}
            </p>
          )}
          <div className="card-heading">
            <h1 id="game-title">오늘의 단어를 맞혀보세요</h1>
            {state && (
              <div className="puzzle-meta">
                <time className="puzzle-date" dateTime={state.puzzle_date}>
                  {formattedDate}
                </time>
                {state.yesterday_answer && (
                  <p className="yesterday-answer">
                    어제의 정답: <strong>{state.yesterday_answer}</strong>
                  </p>
                )}
              </div>
            )}
          </div>
          {state?.user && (
            <div className="game-summary" aria-live="off">
              {game && (
                <>
                  <span>
                    <strong>{game.attempts}</strong>회 시도
                  </span>
                  <span className="summary-dot" aria-hidden="true">
                    ·
                  </span>
                  <span className={completed ? 'completed-status' : ''}>
                    {completed ? '정답 완료' : '도전 중'}
                  </span>
                </>
              )}
              <span className="player-name">
                {state.user.nickname}
                <span> 님</span>
              </span>
            </div>
          )}
          {loading && (
            <p className="message" role="status">
              불러오는 중…
            </p>
          )}
          {offline && (
            <p className="message warning" role="status">
              인터넷 연결을 확인해 주세요.
            </p>
          )}
          {error && (
            <div className="message error" role="alert">
              <p>{error}</p>
              <button
                className="text-button"
                type="button"
                onClick={() => void refresh()}
                disabled={busy || offline}
              >
                다시 연결
              </button>
            </div>
          )}
          {state && !state.model.ready && (
            <p className="message warning" role="status">
              게임을 준비하고 있어요. 잠시 후 다시 확인해 주세요.
            </p>
          )}
          {state && !state.user && (
            <div className="welcome-panel">
              <form onSubmit={createUser} className="input-row">
                <div className="input-wrap">
                  <label className="sr-only" htmlFor="nickname">
                    닉네임
                  </label>
                  <input
                    id="nickname"
                    name="nickname"
                    onKeyDown={keepImeInput}
                    placeholder="닉네임을 입력해 주세요"
                    value={nickname}
                    onChange={(event) => setNickname(event.target.value)}
                    minLength={2}
                    maxLength={20}
                    required
                    autoComplete="nickname"
                    disabled={busy || offline}
                    aria-describedby="nickname-help"
                  />
                </div>
                <button type="submit" disabled={busy || offline || nickname.trim().length < 2}>
                  {busy ? '저장 중…' : '닉네임 설정'}
                </button>
              </form>
              <p className="field-help" id="nickname-help">
                2~20자
              </p>
            </div>
          )}
          {state?.user && !game && (
            <div className="start-panel">
              <button
                className="start-button"
                type="button"
                onClick={() => void start()}
                disabled={disabled || !state.model.ready}
              >
                {busy ? '시작하는 중…' : '오늘 게임 시작'}
                <span aria-hidden="true">→</span>
              </button>
            </div>
          )}
          {game && state && (
            <>
              {dateDue && (
                <p className="message" role="status">
                  새 문제를 불러오는 중…
                </p>
              )}
              <form onSubmit={guess} className="input-row guess-form">
                <div className="input-wrap">
                  <label className="sr-only" htmlFor="guess">
                    추측할 단어
                  </label>
                  <input
                    ref={input}
                    id="guess"
                    name="guess"
                    onKeyDown={keepImeInput}
                    value={word}
                    onChange={(event) => setWord(event.target.value)}
                    placeholder={
                      completed ? '오늘의 도전을 완료했어요' : '추측할 단어를 입력하세요'
                    }
                    maxLength={40}
                    required
                    autoComplete="off"
                    spellCheck={false}
                    disabled={disabled || !playing || !state.model.ready}
                  />
                </div>
                <button
                  type="submit"
                  disabled={disabled || !playing || !state.model.ready || !word.trim()}
                >
                  {busy ? '계산 중…' : '추측하기'}
                </button>
              </form>
              {wordNotice && (
                <p className="message warning" role="alert">
                  {wordNotice}
                </p>
              )}
              {completed && correct && (
                <CompletionPanel
                  key={`${state.user?.id}:${state.puzzle_date}:${state.model.scores_updated_at || ''}`}
                  puzzleDate={state.puzzle_date}
                  nextResetAt={state.next_reset_at}
                  answer={correct.word}
                  attempts={game.attempts}
                  stats={state.player_stats}
                />
              )}
              <div className="guess-table-wrap">
                <table className="guess-table">
                  <caption className="sr-only">
                    추측한 단어와 실제 유사도, 최초 시도 번호. 최근 입력을 맨 위에 표시하고 나머지는
                    유사도가 높은 순서, 같은 점수는 최초 시도 번호순으로 표시합니다. 정답에 가까운
                    상위 1,000위 단어의 순위와 연속 막대를 표시합니다.
                  </caption>
                  <colgroup>
                    <col className="attempt-column" />
                    <col className="word-column" />
                    <col className="score-column" />
                    <col />
                  </colgroup>
                  <thead>
                    <tr>
                      <th scope="col">#</th>
                      <th scope="col">추측한 단어</th>
                      <th scope="col">유사도 (%)</th>
                      <th scope="col">단어 유사도 순위</th>
                    </tr>
                  </thead>
                  {latestGuess && (
                    <tbody className="latest-guess">{guessRow(latestGuess, true)}</tbody>
                  )}
                  {previousGuesses.length > 0 && (
                    <tbody className="previous-guesses">
                      {previousGuesses.map((item) => guessRow(item))}
                    </tbody>
                  )}
                  {!latestGuess && (
                    <tbody>
                      <tr>
                        <td colSpan={4} className="empty-guesses">
                          입력한 단어가 없어요.
                        </td>
                      </tr>
                    </tbody>
                  )}
                </table>
              </div>
            </>
          )}
        </section>
        {state && (
          <Ranking
            key={`${state.user?.id}:${state.puzzle_date}:${state.model.scores_updated_at || ''}`}
            puzzleDate={state.puzzle_date}
            viewerId={state.user?.id || null}
            canViewHistory={completed && !dateDue}
            ranking={state.ranking}
            wordRanksReady={wordRanksReady}
            onContact={setChatContact}
          />
        )}
      </main>
      <ChatPanel
        key={state?.user?.id || 'anonymous'}
        user={state?.user || null}
        contact={chatContact}
      />
    </>
  );
}
