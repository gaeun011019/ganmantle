// 정답을 맞힌 뒤에만 여는 친구의 기록. 서버가 허용한 오늘 기록을 최초 입력 순서로 표시한다.
import { useEffect, useRef, useState } from 'react';
import { ApiError, request, type PlayerGuessHistory } from '../api';
import type { ChatUser } from '../chat/api';
import WordRank from './WordRank';

export default function GuessHistory({
  person,
  puzzleDate,
  isMe,
  onClose,
  onContact,
}: {
  person: ChatUser;
  puzzleDate: string;
  isMe: boolean;
  onClose: () => void;
  onContact: (person: ChatUser) => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [history, setHistory] = useState<PlayerGuessHistory | null>(null);
  const [error, setError] = useState('');
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const element = dialog.current;
    const trigger = document.activeElement;
    element?.showModal();
    return () => {
      element?.close();
      if (trigger instanceof HTMLElement && trigger.isConnected) trigger.focus();
    };
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setHistory(null);
    setError('');
    void request<PlayerGuessHistory>(
      `/ranking/${encodeURIComponent(person.id)}/guesses?puzzle_date=${encodeURIComponent(puzzleDate)}`,
      undefined,
      controller.signal,
    ).then(
      (result) => {
        if (!controller.signal.aborted) setHistory(result);
      },
      (cause: unknown) => {
        if (!controller.signal.aborted)
          setError(
            cause instanceof ApiError
              ? cause.message
              : '기록을 불러오지 못했어요. 다시 시도해 주세요.',
          );
      },
    );
    return () => controller.abort();
  }, [person.id, puzzleDate, retry]);

  const nickname = history?.user.nickname || person.nickname;

  return (
    <dialog
      ref={dialog}
      className="guess-history"
      aria-labelledby="guess-history-title"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header className="guess-history-heading">
        <h2 id="guess-history-title">{nickname}님의 추측 기록</h2>
        <button type="button" className="guess-history-close" onClick={onClose}>
          닫기
        </button>
      </header>
      {history ? (
        <>
          <p className="guess-history-status">
            {history.attempts}회 시도 · {history.status === 'completed' ? '정답 완료' : '도전 중'}
          </p>
          <div className="guess-history-table-wrap">
            <table className="guess-history-table">
              <caption className="sr-only">최초 시도 순서대로 표시한 오늘의 추측 기록</caption>
              <colgroup>
                <col className="history-attempt-column" />
                <col />
                <col className="history-score-column" />
                <col className="history-rank-column" />
              </colgroup>
              <thead>
                <tr>
                  <th scope="col">#</th>
                  <th scope="col">추측한 단어</th>
                  <th scope="col">유사도 (%)</th>
                  <th scope="col">유사도 순위</th>
                </tr>
              </thead>
              <tbody>
                {history.guesses.map((guess) => (
                  <tr
                    key={guess.attempt}
                    className={guess.is_correct ? 'history-correct' : undefined}
                  >
                    <td>{guess.attempt}</td>
                    <th scope="row">{guess.word}</th>
                    <td>{guess.similarity.toFixed(2)}</td>
                    <td>
                      <WordRank rank={guess.similarity_rank} ready />
                    </td>
                  </tr>
                ))}
                {history.guesses.length === 0 && (
                  <tr>
                    <td colSpan={4} className="guess-history-empty">
                      입력한 단어가 없어요.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </>
      ) : error ? (
        <div className="guess-history-error" role="alert">
          <p>{error}</p>
          <button
            type="button"
            className="guess-history-retry"
            onClick={() => setRetry((n) => n + 1)}
          >
            다시 불러오기
          </button>
        </div>
      ) : (
        <p className="guess-history-status" role="status">
          기록을 불러오는 중…
        </p>
      )}
      {!isMe && (
        <footer className="guess-history-actions">
          <button
            type="button"
            className="guess-history-chat"
            onClick={() => onContact(history?.user || person)}
          >
            대화하기
          </button>
        </footer>
      )}
    </dialog>
  );
}
