# 2026-09-19 — 기본 게임 화면과 시간 표시

- 기록 ID: 2026-09-19-002
- 분야: 화면
- 유형: 초기 구현 기록
- 근거: 현재 소스와 기존 검증 기록. 이번에 화면 동작을 바꾼 기록은 아닙니다.

## 무엇이 추가되었나요?

참고 이미지의 중앙 게임 카드와 녹색 계열을 바탕으로 닉네임 설정 → 시작 → 단어 입력 → 정답 완료 화면을 구성했습니다. 앱 이름은 간맨틀로 통일했습니다.

| 상황 | 구현한 동작 |
|---|---|
| 게임 진행 | 시도 횟수·시간·단어·유사도·최초 시도 번호 표시 |
| 중복 입력 | 서버의 기존 결과를 맨 위로 표시하고 안내 |
| 서버 응답이 늦게 도착 | 오래된 조회가 최신 입력 결과를 덮지 않도록 확인 |
| 탭 복귀·온라인 전환 | 서버 기록과 날짜를 다시 조회 |
| 한국어 조합 중 Enter | 글자 조합 확정이 즉시 제출로 이어지지 않게 처리 |
| 모델 준비 실패·통신 오류 | 오류 안내. 임의 점수 표시 없음 |

## 어디에 구현했나요?

| 파일 | 코드 위치 | 추가한 처리 |
|---|---|---|
| [App.tsx](../../frontend/src/App.tsx) | `App()`, `createUser()`, `start()`, `guess()` | 닉네임·시작·입력·완료 흐름 |
| [App.tsx](../../frontend/src/App.tsx) | `accept()`, `anchor`, `elapsed`, `duration()` | 서버의 경과 시간에 화면에서 흐른 시간을 더해 표시 |
| [App.tsx](../../frontend/src/App.tsx) | `refresh()`, `mutate()`, `revision`, `mutating` | 늦은 응답 경합 방지. 오류 뒤 상태 확인까지 입력 잠금 유지 |
| [App.tsx](../../frontend/src/App.tsx) | `useEffect`, `dateDue`, `DATE_NOTICE` | 10초 조회, 탭·접속 복구, BroadcastChannel, 자정 안내 |
| [App.tsx](../../frontend/src/App.tsx) | `keepImeInput()` | 한국어 IME 조합 중 Enter 제출 방지 |
| [api.ts](../../frontend/src/api.ts) | `State`, `Guess`, `ApiError`, `request()` | API 타입, 쿠키 요청, 45초 제한과 오류 메시지 |
| [styles.css](../../frontend/src/styles.css) | `.game-card`, `.stats`, `.guess-table`, `@media` | 카드·시간·결과 표·작은 화면 배치 |
| [main.tsx](../../frontend/src/main.tsx), [index.html](../../frontend/index.html) | React 진입점, `<title>` | 화면 시작, 한국어 문서와 간맨틀 제목 |
| [vite.config.ts](../../frontend/vite.config.ts) | `server.proxy` | 개발 화면의 `/api`를 FastAPI로 전달 |

## 핵심 코드

`App.tsx`의 시간 표시는 서버에서 받은 경과 시간을 기준으로 합니다.

```typescript
const elapsed = anchor.current.elapsed + (playing ? Math.max(0, performance.now() - anchor.current.at) : 0);
```

완료 상태에서는 화면 시간이 더 증가하지 않습니다. 실제 기록은 [game.py](../../backend/app/game.py)의 서버 시각을 사용합니다.

`refresh()`의 일부입니다.

```typescript
if (requestRevision === revision.current && !mutating.current) {
  accept(next);
  setError('');
}
```

이전 조회가 늦게 돌아왔거나 입력 요청이 진행 중이면 그 응답으로 화면을 덮지 않습니다. 실패한 입력 뒤 재조회도 `mutate()`의 `finally` 안에서 마친 다음 잠금을 해제합니다.

## 어떻게 확인했나요?

기존 [검증 기록](../../docs/VALIDATION.md): TypeScript 검사와 Vite 빌드 통과, HTML·정적 파일 제공 확인. 브라우저 제어 도구가 연결되지 않아 클릭·시각·모바일 검사는 미검증입니다. 이번에는 파일·함수 위치를 확인했으며 앱 검사는 다시 실행하지 않았습니다.

## 영향과 남은 일

랭킹과 채팅의 가짜 데이터를 넣지 않았습니다. 실제 브라우저·모바일·IME 동작 확인은 후속 작업입니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
