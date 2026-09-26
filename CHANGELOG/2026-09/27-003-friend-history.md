# 2026-09-27 — 정답 후 친구 추측 기록 열람

- 기록 ID: 2026-09-27-003
- 분야: 게임 / 화면 / 검사 / 문서
- 유형: 추가 / 변경
- 구현 상태: 완료
- 관련 커밋: 미기록 (이번 작업에서 커밋·업로드하지 않음)

## 무엇이 달라졌나요?

정답을 맞힌 뒤 친구가 어떤 단어를 거쳐 정답에 도달했는지 볼 수 있게 합니다. 내가 오늘 문제를 완료한 후 랭킹의 닉네임을 누르면 추측 기록이 열립니다.

| 변경 전 | 변경 후 |
|---|---|
| 랭킹 닉네임은 개인 대화 선택으로만 연결 | 정답 전에는 기존 대화, 정답 후에는 추측 기록을 먼저 표시하고 창 안의 ‘대화하기’로 연결 |
| 다른 사람의 추측은 항상 숨김 | 내가 오늘 정답을 맞힌 경우만 상대의 오늘 기록 조회 가능 |
| 본인 게임 표는 최근 입력·유사도순 | 친구 기록 창은 풀이 흐름을 알 수 있게 최초 시도 순서로 표시. 본인 게임 표 정렬은 유지 |

도전 중인 사람은 조회 시점까지의 기록을 볼 수 있습니다. 자정에는 오늘 완료 여부를 새로 판단하며, 어제 완료한 권한으로 오늘 기록을 열 수 없습니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 변경 내용 |
|---|---|---|
| [backend/app/game.py](../../backend/app/game.py) | `friend_history()` | 현재 날짜·조회자의 완료 확인 후 대상의 저장된 추측을 최초 시도순으로 조회하고 같은 모델의 단어 순위 계산 |
| [backend/app/main.py](../../backend/app/main.py) | `/api/ranking/{user_id}/guesses` | 세션·UUID·날짜를 검증하는 조회 API |
| [frontend/src/api.ts](../../frontend/src/api.ts) | `PlayerGuessHistory` | 기록 조회에 필요한 최소 데이터 정의 |
| [frontend/src/ranking/Ranking.tsx](../../frontend/src/ranking/Ranking.tsx) | `Ranking` / `canViewHistory` | 본인 완료 여부에 따라 기록 또는 기존 대화 열기 |
| [frontend/src/ranking/GuessHistory.tsx](../../frontend/src/ranking/GuessHistory.tsx) | `GuessHistory` | 입력 순서·단어·유사도·단어 순위, 조회 오류·재시도·닫기·대화 연결 |
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | Ranking 연결 | 오늘 날짜·완료 여부·사용자 변경을 기록 창에 연결 |
| [frontend/src/styles.css](../../frontend/src/styles.css) | 기록 창 스타일 | 기존 흰색·하늘색, 좁은 화면에서도 읽을 수 있는 표 |
| [backend/tests/test_friend_history.py](../../backend/tests/test_friend_history.py) | API·규칙 검사 | 접근 권한·날짜·원래 순서·중복·점수·개인 기록 범위 검사 |
| [scripts/check_ui.mjs](../../scripts/check_ui.mjs) | 브라우저 검사 | 닉네임 클릭·기록 창·재시도·닫기·자정·모바일 검사 |
| [scripts/check_release.mjs](../../scripts/check_release.mjs) | 실제 모델 검사 | 독립 DB의 두 사용자로 접근 차단·풀이 과정·실제 점수/순위 일치 확인 |
| [README.md](../../README.md), [GANMANTLE_SPEC.md](../../GANMANTLE_SPEC.md) | 게임 규칙 | 완료 후 열람으로 변경된 공개 범위와 사용법 기록 |

## 핵심 동작

- 서버의 본인 세션과 오늘 완료 기록으로 권한을 판단합니다. 다른 사용자의 ID를 보내는 것만으로 완료 권한을 얻지 못합니다.
- 기록은 DB에 저장된 `attempt` 오름차순입니다. 중복 입력으로 최근 표시 순서가 바뀌어도 원래 풀이 순서와 시도 수는 유지됩니다.
- 일반 `/api/state`의 랭킹에는 추측 단어를 계속 넣지 않습니다. 별도 권한 검사 API에서만 제공합니다.
- 풀이 시간·세션 토큰·다른 날짜의 기록·개인 채팅은 이 응답에 넣지 않습니다.

## 핵심 코드

`game.py`는 현재 날짜를 확인한 다음 본인의 완료 상태를 검사하고, 그 뒤에만 대상 기록과 모델을 조회합니다 (일부 발췌).

```python
if not viewer or viewer["status"] != "completed":
    raise GameError("game_not_completed", "오늘 정답을 맞히면 친구의 추측 기록을 볼 수 있어요.", 403)
```

대상 게임을 `FOR SHARE OF g`로 잠근 동안 `ORDER BY attempt`로 추측을 읽습니다. 친구가 동시에 새 단어를 제출해도 횟수와 목록이 서로 다른 순간의 데이터가 되지 않게 합니다.

`App.tsx`는 `canViewHistory={completed && !dateDue}`로 정답 전과 자정 전환 중에는 기록 창을 열지 않습니다. `GuessHistory`는 닫기·날짜 변경 때 `AbortController`로 요청을 취소하여 늦게 도착한 이전 응답을 표시하지 않습니다.

## 어떻게 확인했나요?

| 확인 방법 | 이번 실행 결과 |
|---|---|
| 실제 PostgreSQL 임시 스키마의 전체 백엔드 검사 | **288개 통과**, 171.15초. 기존 268개에 친구 기록 검사 20개 추가. 기존 TestClient AnyIO 별칭 폐기 예정 경고 1개 |
| TypeScript 검사·Vite Docker 빌드 | 통과. localhost 앱에 반영하고 app·db healthy 확인 |
| Windows Chrome 화면·상호작용 검사 | **33개 통과**, JavaScript 오류 0. 정답 전 채팅 유지/기록 요청 없음, 정답 후 본인·친구 기록, 최초 순서, 오류 재시도, Escape·초점 복귀, 채팅 연결 확인 |
| 자정·응답 지연 검사 | 친구 기록 로딩 중 닫기/다른 친구 선택/자정 전환 후 늦게 도착한 이전 응답이 표시되지 않음 |
| 반응형 화면 | 데스크톱 1600×1500, 390×844, 320×844 통과. 친구 기록 창의 가로 넘침 없음. 데스크톱·320px 캡처도 직접 검토 |
| 독립 DB와 실제 fastText 통합 검사 | **8개 묶음 통과**. 미등록401·미완료403·완료 후 친구 조회, 도전 중→완료 기록 전환, 중복 횟수 유지, 최초 순서, 실제 점수·순위 일치, 재접속 확인 |
| 기록 보존 | 실제 모델 검사에서 조회 전후 DB 내용 동일. 기존 게임·채팅 저장/재시작, 논리 백업·새 DB 복원 검사도 통과. 실사용자 DB를 변경하지 않음 |
| 검사 정리·코드 | 검사용 DB·컨테이너·설정·Chrome 프로필 제거, 기존 모델 보존. 스크립트 구문 검사·`git diff --check`·문서 상대 링크 확인 통과 |

첫 브라우저 실행은 검사 스크립트의 중첩 문자열 인용 오류로 중단됐습니다. 선택자 2곳을 고치고 내장 JavaScript 문자열 198개를 구문 검사한 뒤 전체 33개를 다시 실행해 통과했습니다. 이 수정은 운영 앱 동작 변경이 아닙니다.

화면 검사는 명시된 TEST ONLY 모의 자료를, 모델·DB 검사는 별도 DB의 실제 계산을 사용합니다. 캡처는 Git에서 제외한 `test-results/ui-friend-history-desktop.png`, `ui-friend-history-390.png`, `ui-friend-history-320.png`에 있습니다. 이전 완료 화면 작업의 결과는 [27-002](27-002-completion-panel.md)에 별도로 남깁니다.

## 영향과 남은 일

- DB 테이블·마이그레이션·모델·의존성 추가 없음. 기존 사용자 기록 유지.
- GitHub 업로드·공개 배포 없음.
- 실제 Mac·Safari·실물 모바일 검사는 수행하지 않음.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
