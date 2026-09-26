// 서버가 정한 단어 순위를 표시합니다. 같은 색의 막대 길이를 상위 1,000위 안의 순위로 채웁니다.
export default function WordRank({ rank, ready, bar = false }: { rank: number | null; ready: boolean; bar?: boolean }) {
  const correct = ready && rank === 0;
  const inRange = ready && rank !== null && rank >= 1 && rank <= 1000;
  const label = correct ? '정답' : !ready ? '—' : inRange ? `${rank.toLocaleString('ko-KR')}위` : '1,000위 밖';
  const fill = correct ? 100 : inRange ? ((1001 - rank) / 1000) * 100 : 0;
  const rankValue = correct ? '0' : !ready ? 'unavailable' : inRange ? String(rank) : 'outside';

  return <span className={bar ? 'similarity-visual' : 'word-rank-result'} data-similarity-rank={rankValue}>
    <span className={bar ? 'word-rank' : 'word-rank-label'}>{label}</span>
    {bar && <span className={`rank-track${fill > 0 ? ' has-rank' : ''}`} aria-hidden="true"><span className="rank-fill" style={{ width: `${fill}%` }} /></span>}
  </span>;
}
