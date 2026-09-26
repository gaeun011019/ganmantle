# 2026-09-19 — 흰색·파란색 화면과 실제 최고 유사도 표시

- 기록 ID: 2026-09-19-008
- 분야: 게임 / 화면 / 문서
- 유형: 추가 / 수정
- 구현 상태: UI 변경 완료 (전체 어휘 순위·채팅 전송은 준비 중)
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

사용자가 제공한 [새 UI 참고 이미지](../../docs/UI_REFERENCE_BLUE.png)에 맞춰 흰 배경과 파란 버튼, 로고, 유사도 막대, 게임 아래 랭킹, 오른쪽 아래 채팅 팝업을 적용했습니다. 기존 게임·입력 검증 규칙을 유지하면서 랭킹에 각 게임의 실제 최고 유사도를 추가했습니다. 이미지의 예시 점수·순위·대화나 시간 주석을 실제 기록 또는 새 게임 규칙으로 사용하지 않습니다.

| 변경 전 | 변경 후 |
|---|---|
| 초기 명세의 녹색 중심 화면 | 새 참고 이미지의 흰색·파란색 배치, 로고와 파비콘 |
| 입력 단어·점수 중심의 기록 표시 | 최초 시도 번호, 단어, 실제 점수, 양수 유사도 막대와 최근 입력 표시 |
| 랭킹에 최고 유사도 항목 없음 | 게임별 저장 점수의 원본 `MAX`, 아직 입력하지 않았으면 `—` |
| 전체 어휘의 기준 유사도·유사도 순위 미구현 | 관련 위치를 마련하되 숫자 대신 `준비 중`과 `—` 표시 |
| 실제 채팅 미구현 | 열기·닫기·Escape가 동작하는 팝업 틀. 전송·대화 선택은 비활성화 |

유사도 막대는 양수 점수를 0~100% 길이로 표현합니다. 표의 실제 점수는 음수를 포함해 소수점 두 자리로 표시하며, 코사인 × 100 계산식은 그대로입니다. 랭킹은 최고 유사도로 정렬하지 않으며 기존 시도 횟수 → 원래 풀이 시간 → 공동 순위 규칙을 유지합니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 역할과 변경 |
|---|---|---|
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | `App`, `.similarity-reference`, 추측 결과 표, `mutate()` | 로고·게임·기준 점수 영역·양수 막대 배치. 기존 시간·자정·거절 입력 비움/포커스 처리를 유지하고 준비 중 기능을 구분 |
| [frontend/src/styles.css](../../frontend/src/styles.css) | `:root`, `.game-card`, `.score-track`, `.ranking-table`, `.chat-dock`, 미디어 쿼리 | 흰 배경·파란 강조색·카드·입력·표·고정 팝업과 작은 화면 배치. 표 스크롤 영역에 위치 기준을 지정해 모바일 넘침 수정 |
| [frontend/src/ranking/Ranking.tsx](../../frontend/src/ranking/Ranking.tsx) | `Ranking`, `players`, `.ranking-best-score` | 서버 순서를 유지하며 완료/도전 중·공동 순위·본인 표시·최고 점수와 풀이 시간 표시 |
| [frontend/src/chat/ChatPanel.tsx](../../frontend/src/chat/ChatPanel.tsx) | `ChatPanel`, `open`, `dismiss()`, Escape 처리 | 오른쪽 아래 팝업 열기/닫기, 포커스 복귀. 예시 대화 없이 준비 안내와 비활성 입력/전송 버튼 |
| [frontend/src/api.ts](../../frontend/src/api.ts) | `RankingPlayer.best_similarity` | 서버의 `number \| null` 최고 점수 응답 타입 |
| [frontend/public/brand-mark.svg](../../frontend/public/brand-mark.svg), [frontend/index.html](../../frontend/index.html) | SVG 도형, `icon`, `theme-color`, `title` | 파란 로고·파비콘과 테마 색. 화면과 문서 이름은 간맨틀 유지 |
| [backend/app/game.py](../../backend/app/game.py) | `ranking()` | 각 게임의 `guesses.similarity` 최댓값만 조회해 `best_similarity`로 반환. 순위와 게임당 한 행 유지 |
| [backend/tests/test_ranking.py](../../backend/tests/test_ranking.py) | 공개 필드·미입력·중복 검사, `test_best_similarity_is_raw_max_for_each_game_before_and_after_completion()` | 최고 점수 `None`·음수·원본 정밀도·낮은 후속 점수·중복·완료 후 MAX 검증. 랭킹 검사 총 7개 |
| [scripts/check_ui.mjs](../../scripts/check_ui.mjs) | `installFixture()`, `layout()`, `screenshot()`, 화면별 검사 | 독립된 헤드리스 Chrome에서 검사 전용 자료로 입력·표·팝업·포커스·화면 경계 확인. 실제 게임 API 쓰기 요청은 차단 |
| [docs/UI_REFERENCE_BLUE.png](../../docs/UI_REFERENCE_BLUE.png) | 참고 이미지 | 사용자의 확장자 없는 PNG 파일 `GANMANTLE_UI`를 PNG 확장자로 복사해 보관. 원본과 복사본 SHA-256 일치 확인 |
| [README.md](../../README.md), [GANMANTLE_SPEC.md](../../GANMANTLE_SPEC.md), [docs/VALIDATION.md](../../docs/VALIDATION.md) | 화면 수정 위치·사용자 UI 변경 요청·검증 범위 | 초기 녹색 설명보다 새 UI 요청을 우선하고 구현/준비 중/미확인 범위를 구분 |
| [전체 목록](../README.md), [월별 목록](README.md), [이 기록](19-008-blue-ui.md) | 008 연결·다음 번호 | 새 변경 기록을 최신 항목으로 연결하고 다음 예시 번호를 009로 수정 |

## 어떤 코드인가요?

확인한 변경 전 동작과 변경 후 핵심 코드만 기록합니다. 화면 전체의 줄 단위 이전 diff는 확인하지 않았습니다. 아래 코드는 모두 일부 발췌입니다.

기존 랭킹 응답에는 최고 점수 필드가 없었습니다. `game.py`의 `ranking()`은 다음 조회를 추가해 게임당 한 행을 유지합니다. 입력이 없으면 PostgreSQL의 `MAX`가 `NULL`을 반환합니다.

```sql
(SELECT MAX(gs.similarity) FROM guesses gs WHERE gs.game_id = g.id) AS best_similarity,
```

```python
"best_similarity": row["best_similarity"],
```

`Ranking.tsx`는 없는 점수를 임의로 채우지 않고, 값이 있을 때만 두 자리로 표시합니다.

```tsx
{player.best_similarity === null ? '—' : player.best_similarity.toFixed(2)}
```

`App.tsx`는 원본 점수 표시와 막대 길이를 구분합니다. 막대의 너비 제한은 화면 표현이며 DB 점수나 정답 판정을 바꾸지 않습니다.

```tsx
<td className="score">{item.similarity.toFixed(2)}</td>
<span style={{ width: `${Math.max(0, Math.min(100, item.similarity))}%` }} />
```

`ChatPanel.tsx`는 팝업 상태만 다루며 메시지를 전송하는 것처럼 꾸미지 않습니다.

```tsx
const [open, setOpen] = useState(false);
```

```tsx
<input id="chat-message" placeholder="채팅 준비 중" disabled />
<button type="button" disabled>보내기</button>
```

## 어떻게 확인했나요?

아래 서버·빌드·HTTP 결과는 2026-09-19 같은 UI 변경 작업에서 수행한 검사 결과입니다. 이 변경 기록을 정리하면서 해당 검사를 별도로 다시 실행하지는 않았습니다. 상세 범위는 [검증 문서](../../docs/VALIDATION.md)에 함께 기록합니다.

| 이번 작업의 확인 | 결과 |
|---|---|
| 실제 PostgreSQL 임시 스키마의 백엔드 검사 | **44 passed**, 65.91초. 기존 게임·세션·사전·자정·랭킹 검사와 최고 점수 검사 포함 |
| TypeScript `tsc --noEmit` + Vite **7.3.6** 빌드 | 통과 |
| `/api/health`, DB·모델 상태 | 정상 확인 |
| 화면 `/`, `/brand-mark.svg` | HTTP **200** 확인 |
| 앱 반영 | 앱 컨테이너만 재시작. PostgreSQL과 저장 볼륨은 그대로 유지 |
| 참고 이미지 보관 | 확장자 없는 원본 PNG와 `docs/UI_REFERENCE_BLUE.png` 복사본 해시 일치 |
| `scripts/check_ui.mjs` 브라우저 검사 | **8개 통과**, JavaScript 오류 0. 입력 거절·비움·포커스·안내 유지, 정상 제출, 공동 순위/본인 표시, 채팅 닫기·Escape와 게임 너비 유지 |
| 데스크톱·모바일 화면 | Chrome 153.0.8010.48의 1600×1500·390×844 캡처 확인. 가로 넘침 없음, 표 내부 스크롤, 모바일 배율 1·화면 이동 0 |
| 실제 Mac·Apple Silicon `arm64` 실행 | 미확인. 이번 Windows 환경의 검사와 구분 |

브라우저 검사의 점수·순위는 `TEST ONLY`로 표시한 검사 자료이며 실제 모델 결과나 사용자 기록이 아닙니다. 모든 `/api` 요청을 가로채 실제 DB에는 쓰지 않습니다. 결과와 캡처는 제외 폴더인 `test-results/`에 있습니다. 실제 모바일 기기·가상 키보드·한국어 IME나 실제 API와 연결한 브라우저 전체 흐름을 검증한 것은 아닙니다.

초기에는 모바일 문서가 635px로 늘어났는데 검사 기준도 늘어난 `innerWidth`를 사용해 이를 놓쳤습니다. 이후 요청한 390×844와 문서·body·visualViewport·배율·화면 이동을 직접 비교하도록 검사를 강화했습니다. 숨긴 표 설명이 스크롤 영역 안에 머물도록 아래 CSS를 추가하고 다시 빌드·검사해 통과했습니다.

```css
.guess-table-wrap, .ranking-table-wrap { position: relative; }
```

Chrome 초기 실행 중 임시 포트 파일을 읽을 때 Windows의 일시적인 `EBUSY`가 발생하면 15초 제한 안에서 다시 읽도록 검사 도구도 보완했습니다.

## 영향과 남은 일

- DB 구조·migration·모델·점수 계산식·당일 정답·기존 저장 기록은 변경하지 않았습니다. 서버 변경은 저장된 최고 점수의 조회 필드 추가입니다.
- 입력 단어 검사, 중복 재표시, 정답 판정, 서버 시작/완료 시간, 한국 시간 자정 전환은 유지합니다. 현재 유효한 [입력 검증 변경 요청](19-007-word-validation.md)도 그대로 적용합니다.
- 새 화면은 앱 이미지를 빌드하고 앱 컨테이너를 교체하면 반영됩니다. DB나 모델을 다시 준비할 필요는 없습니다.
- 전체 어휘의 유사도 순위·기준 점수는 준비 중입니다. 이미지의 예시 숫자를 실제 값으로 넣지 않았습니다.
- 채팅은 팝업 틀만 구현했습니다. 전체·방·개인 대화, 메시지 전송·저장·접근 권한은 3단계 작업입니다.
- 실제 모바일 기기·Safari·Mac·arm64 실행 검증이 남아 있습니다. GitHub 업로드나 공개 배포는 하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
