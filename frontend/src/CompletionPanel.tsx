// 정답을 맞힌 뒤의 안내·내 통계·상위 유사 단어 목록을 표시합니다.
import { useEffect, useRef, useState } from 'react';
import { ApiError, request, type PlayerStats, type RelatedWords } from './api';

type Props = {
  puzzleDate: string;
  nextResetAt: string;
  answer: string;
  attempts: number;
  stats: PlayerStats | null;
};

export default function CompletionPanel({
  puzzleDate,
  nextResetAt,
  answer,
  attempts,
  stats,
}: Props) {
  const [showWords, setShowWords] = useState(false);
  const [words, setWords] = useState<RelatedWords['words'] | null>(null);
  const [loading, setLoading] = useState(false);
  const [wordError, setWordError] = useState('');
  const [retry, setRetry] = useState(0);
  const wordsLink = useRef<HTMLAnchorElement>(null);
  // 다음 문제 날짜도 서버가 준 시각을 한국 시간으로 표시합니다.
  const nextDate = new Intl.DateTimeFormat('ko-KR', {
    timeZone: 'Asia/Seoul',
    month: 'long',
    day: 'numeric',
  }).format(new Date(nextResetAt));

  useEffect(() => {
    if (!showWords || words) return;
    const controller = new AbortController();
    setLoading(true);
    setWordError('');
    void request<RelatedWords>(
      `/related-words?puzzle_date=${encodeURIComponent(puzzleDate)}`,
      undefined,
      controller.signal,
    )
      .then((result) => {
        if (controller.signal.aborted) return;
        if (result.puzzle_date !== puzzleDate) throw new Error('다른 날짜의 응답');
        // words가 바뀌면 effect가 정리되므로 로딩도 같은 콜백에서 끝냅니다.
        setLoading(false);
        setWords(result.words);
      })
      .catch((cause: unknown) => {
        if (controller.signal.aborted) return;
        setLoading(false);
        setWordError(
          cause instanceof ApiError
            ? cause.message
            : '단어 목록을 불러오지 못했어요. 다시 시도해 주세요.',
        );
      });
    // 닫기·자정 전환 때 이전 요청의 결과가 새 화면에 남지 않게 합니다.
    return () => controller.abort();
  }, [showWords, words, puzzleDate, retry]);

  function closeWords() {
    setShowWords(false);
    wordsLink.current?.focus();
  }

  return (
    <section className="success-panel" aria-labelledby="completion-title">
      <p className="completion-summary" role="status">
        <strong id="completion-title">정답 단어를 맞혔습니다!</strong> {attempts}번째 추측 만에 ‘
        {answer}’를 맞혔어요!
      </p>
      <p className="completion-related">
        정답 단어와 비슷한{' '}
        <a
          ref={wordsLink}
          href="#related-words"
          className="completion-link"
          aria-expanded={showWords}
          aria-controls="related-words"
          onClick={(event) => {
            event.preventDefault();
            setShowWords(true);
          }}
        >
          상위 1,000개의 단어
        </a>
        를 확인해 보세요.
      </p>
      {showWords && (
        <div className="related-words" id="related-words">
          <div className="related-words-heading">
            <h3>정답과 비슷한 단어</h3>
            <button type="button" className="completion-link" onClick={closeWords}>
              닫기
            </button>
          </div>
          <p className="related-words-status" role="status">
            {loading
              ? '단어 목록을 불러오는 중…'
              : wordError || (words ? `정답을 제외한 ${words.length.toLocaleString()}개 단어` : '')}
          </p>
          {wordError && (
            <button
              type="button"
              className="completion-link"
              onClick={() => setRetry((value) => value + 1)}
            >
              다시 불러오기
            </button>
          )}
          {words && (
            <div className="related-words-scroll" tabIndex={0} aria-label="유사 단어 목록">
              <table className="related-words-table">
                <thead>
                  <tr>
                    <th scope="col">순위</th>
                    <th scope="col">단어</th>
                    <th scope="col">유사도 (%)</th>
                  </tr>
                </thead>
                <tbody>
                  {words.map((item) => (
                    <tr key={item.word}>
                      <td>{item.rank.toLocaleString()}</td>
                      <th scope="row">{item.word}</th>
                      <td>{item.similarity.toFixed(2)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
      <p className="completion-next">
        다음 간맨틀은 <time dateTime={nextResetAt}>{nextDate} 00:00</time>에 열립니다. (한국 시간)
      </p>
      {stats && (
        <div className="completion-history">
          <h3>나의 플레이 기록</h3>
          <dl className="player-stats">
            <dt>도전한 게임 횟수</dt>
            <dd>{stats.games_played.toLocaleString()}회</dd>
            <dt>정답 횟수</dt>
            <dd>{stats.games_completed.toLocaleString()}회</dd>
            <dt>연속 정답 횟수</dt>
            <dd>{stats.current_streak.toLocaleString()}회</dd>
            <dt>미완료 횟수</dt>
            <dd>{stats.games_incomplete.toLocaleString()}회</dd>
            <dt>지금까지 추측한 단어</dt>
            <dd>{stats.total_guesses.toLocaleString()}개</dd>
          </dl>
        </div>
      )}
    </section>
  );
}
