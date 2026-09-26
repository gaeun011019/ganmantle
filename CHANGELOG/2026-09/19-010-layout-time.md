# 2026-09-19 — 본문 여백 확대와 공동 순위의 시간 표시

- 기록 ID: 2026-09-19-010
- 분야: 화면 / 검사 / 문서
- 유형: 변경
- 구현 상태: 구현·검증·로컬 반영 완료
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

사용자 요청으로 데스크톱 본문을 좁혀 양옆 여백을 늘리고 게임의 시간 표시를 숨겼습니다. 시간을 보여 줄 조건은 사용자가 선택한 **실제로 같은 순위 번호를 받은 사람**으로 확정했습니다. 시도 횟수가 같아도 시간 차이로 순위가 갈리면 시간은 표시하지 않습니다.

| 변경 전 | 변경 후 |
|---|---|
| 본문 최대 1040px, 데스크톱 최소 좌우 여백 24px | 최대 860px, 최소 좌우 여백 32px. 넓은 화면에서는 중앙 정렬로 여백 확대 |
| 진행 중 경과 시간과 정답 완료 시 소요 시간 표시 | 게임 화면에는 시도 횟수와 진행·완료 상태 표시 |
| 완료한 모든 사람의 풀이 시간 표시 | 같은 순위 번호가 2명 이상인 행에만 시간 표시 |
| 시작 화면에서 시간 경과 안내 | 단어의 유사도를 보며 추리하는 게임 안내 |

서버는 기존처럼 시작·완료 시각을 저장하고 시도 횟수, 원래 풀이 시간 순으로 순위를 계산합니다. 횟수와 원래 시간이 모두 같아야 공동 순위입니다. 720px 이하 모바일 본문 너비와 채팅 구조는 유지했습니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 역할·변경 내용 |
|---|---|---|
| [frontend/src/styles.css](../../frontend/src/styles.css) | `main`, `.site-header`, `.game-summary .timer` | 본문과 헤더 여백 조정, 사용하지 않는 타이머 스타일 정리 |
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | `anchor`, `.game-summary`, `.start-panel`, `.success-panel` | 경과 시간 표시·표시용 계산 제거. 서버 시각으로 자정을 확인하는 처리는 유지 |
| [frontend/src/ranking/Ranking.tsx](../../frontend/src/ranking/Ranking.tsx) | `rankCounts`, `.ranking-player-time`, `ranking-time-note` | 실제 공동 순위에만 시간 표시, 안내 문구 일치 |
| [scripts/check_ui.mjs](../../scripts/check_ui.mjs) | `installFixture`, 시간 표시·완료 화면·본문 너비 검사 | 공동/단독/같은 횟수의 다른 순위/도전 중을 분리해 검증 |
| [README.md](../../README.md), [GANMANTLE_SPEC.md](../../GANMANTLE_SPEC.md) | 최신 요청·시간 표시 규칙 | 초기 명세의 타이머 표시와 현재 요청 구분 |
| [docs/VALIDATION.md](../../docs/VALIDATION.md) | 최신 화면 검사 | 이번 결과와 이전 채팅 검사 구분 |
| [전체 목록](../README.md), [월별 목록](README.md) | 010 링크 | 파일별 변경 기록 연결 |

## 어떤 코드인가요?

기존에는 `elapsed_ms !== null`인 완료자 모두에게 시간을 보여 줬습니다. 현재는 서버가 정한 같은 `rank`가 두 번 이상 등장할 때만 표시합니다. 순위를 화면에서 다시 계산하지 않습니다.

```tsx
player.rank !== null &&
(rankCounts.get(player.rank) ?? 0) > 1 &&
player.elapsed_ms !== null
```

본문 너비는 아래 한 곳에서 조정합니다. 모바일 미디어 쿼리는 기존대로 별도 적용합니다.

```css
main { width: min(860px, calc(100% - 64px)); margin: 36px auto 106px; }
```

게임의 `duration()`과 표시용 `elapsed` 계산을 제거했지만 `anchor.at`, `resetAfter`, `dateDue`와 자정 확인 주기는 유지합니다. API의 시간 필드는 그대로이므로 이 변경은 화면 표시 정책입니다.

## 어떻게 확인했나요?

| 확인 | 결과 |
|---|---|
| `docker compose build app` | TypeScript와 Vite 7.3.6 빌드 통과 |
| `node scripts/check_ui.mjs` | **11개 통과**, JavaScript 오류 0. 기존 8개에 시간 표시·본문 여백·완료 화면 검사 추가 |
| 시간 조건 | 공동 1위 2명만 `1분 33초` 표시. 같은 8회이지만 단독 3위인 사람, 단독 4위, 도전 중인 사람은 숨김 |
| 게임 시간 숨김 | 진행 중·정답 완료 화면 모두 경과 시간 없음. 완료 시 시도 횟수 표시 유지 |
| 화면 배치 | Chrome 153.0.8010.48, 1600×1500에서 본문 860px·양옆 약 362.5px 확인. 390×844 모바일 너비·입력·채팅 경계 통과 |
| 기존 입력·팝업 | 거절 후 자동 비움·포커스·안내 유지, 정상 제출, 채팅 닫기·Escape·게임 너비 유지 통과 |
| 로컬 실행 | `docker compose up -d --no-deps app` 반영. `/api/health` ok, 모델 준비 정상 |

화면 검사는 실제 빌드에 검사 전용 API 응답을 넣으며 운영 DB에는 쓰지 않습니다. 결과와 캡처는 제외 폴더 `test-results/`에 있습니다. 첫 시도는 Chrome 제어 초기화(`Page.enable`)가 시간 초과되어 검사 시작 전에 종료됐고, 별도 프로필로 다시 실행해 11개를 통과했습니다. 서버 계산식·DB 변경이 없어 이전 백엔드 58개와 실제 채팅 9개 검사는 이번에 반복하지 않았습니다. 실제 모바일 기기·Mac·Safari는 미검증입니다.

## 영향과 남은 일

- DB 구조·내용을 바꾸는 코드, 서버 순위 계산, 모델, 의존성 변경 없음.
- 화면 적용은 `docker compose up -d --build` 후 브라우저 새로고침으로 확인합니다.
- 실제 Mac/arm64·모바일 기기·Safari 검증과 명세 4단계 배포 준비는 기존 미완료 범위입니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
