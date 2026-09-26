// 오늘의 전체 랭킹. 서버 순서대로 완료자를 먼저, 도전 중인 사람을 뒤에 보여 준다.
import type { DailyRanking } from '../api';
import type { ChatUser } from '../chat/api';
import WordRank from './WordRank';

function duration(milliseconds: number): string {
  // 공동 순위에만 보여 주며 초 미만은 생략한다. 순위 비교는 서버의 원래 기록을 사용한다.
  const seconds = Math.max(0, Math.floor(milliseconds / 1000));
  const hours = Math.floor(seconds / 3600);
  return `${hours ? `${hours}시간 ` : ''}${Math.floor((seconds % 3600) / 60)}분 ${seconds % 60}초`;
}

export default function Ranking({ ranking, wordRanksReady, onContact }: { ranking: DailyRanking; wordRanksReady: boolean; onContact: (person: ChatUser) => void }) {
  const rankCounts = new Map<number, number>();
  for (const player of ranking.completed) rankCounts.set(player.rank, (rankCounts.get(player.rank) ?? 0) + 1);
  const players = [...ranking.completed, ...ranking.playing];

  return <section className="ranking-card" aria-labelledby="ranking-title">
    <div className="ranking-heading">
      <h2 id="ranking-title">오늘의 전체 랭킹</h2>
    </div>
    <div className="ranking-table-wrap">
    <table className="ranking-table">
      <caption className="sr-only">오늘의 전체 랭킹. 완료 {ranking.completed.length}명, 도전 중 {ranking.playing.length}명. 완료자는 시도 횟수가 적은 순, 같으면 풀이 시간이 짧은 순으로 표시합니다.</caption>
      <colgroup><col className="rank-column" /><col /><col className="tries-column" /><col className="similarity-column" /><col className="similarity-rank-column" /></colgroup>
      <thead><tr><th scope="col">순위</th><th scope="col">닉네임</th><th scope="col">시도 횟수</th><th scope="col">최고 유사도 (%)</th><th scope="col">단어 유사도 순위</th></tr></thead>
      <tbody>
        {players.map(player => <tr key={player.user_id} className={player.is_me ? 'my-ranking-row' : undefined}>
          <td className="rank-value">{player.rank === null ? <span className="playing-status">도전 중</span> : <>{(rankCounts.get(player.rank) ?? 0) > 1 && <span className="joint-rank">공동 </span>}{player.rank}위</>}</td>
          <th scope="row" className="ranking-name">
            <span className="ranking-player-name">{player.is_me ? player.nickname : <button type="button" className="ranking-nickname" aria-label={`${player.nickname} 님과 대화 선택`} onClick={() => onContact({ id: player.user_id, nickname: player.nickname })}>{player.nickname}</button>}{player.is_me && <span className="me-label">나</span>}</span>
            {player.rank !== null && (rankCounts.get(player.rank) ?? 0) > 1 && player.elapsed_ms !== null && <span className="ranking-player-time">풀이 {duration(player.elapsed_ms)}</span>}
          </th>
          <td className="ranking-number">{player.attempts}회</td>
          <td className="ranking-number ranking-best-score">{player.best_similarity === null ? '—' : player.best_similarity.toFixed(2)}</td>
          <td className="ranking-similarity-rank">{player.best_similarity === null ? '—' : <WordRank rank={player.best_similarity_rank} ready={wordRanksReady} />}</td>
        </tr>)}
        {players.length === 0 && <tr><td colSpan={5} className="ranking-empty">아직 참여자가 없어요.</td></tr>}
      </tbody>
    </table>
    </div>
  </section>;
}
