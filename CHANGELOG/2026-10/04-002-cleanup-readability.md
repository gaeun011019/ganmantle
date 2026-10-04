# 2026-10-04 — 폴더 점검·임시 파일 정리·코드 가독성 개선

- 기록 ID: 2026-10-04-002
- 분야: 화면 / 서버 / 검사 / 환경 / 문서
- 유형: 정리 / 변경 / 수정
- 구현 상태: 완료
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

현재 폴더와 소스·스크립트의 사용처를 확인하고, 게임·채팅 요청의 중복 처리와 읽기 어려운 긴 구문을 정리했습니다. 입력창 모양·게임 규칙·점수 계산·DB 기록·모델·ngrok 인증 설정은 유지합니다. 앞선 [닉네임 입력창 테두리 변경](04-001-nickname-input-border.md)도 보존했습니다.

| 변경 전 | 변경 후 |
|---|---|
| 게임·채팅이 fetch·JSON 파싱·오류 처리를 각각 구현 | 공통 `request()` 사용. 게임 45초·채팅 15초 제한과 각각의 오류 문구 유지 |
| 게임 상태 조회 URL 생성식이 두 곳에 반복 | `requestState()`에서 한 번만 정의 |
| Python·검사 스크립트의 인자·객체·조건문이 한 줄에 길게 붙음 | Python 4칸, TS/JS/CSS 2칸, 기본 100자 기준으로 줄바꿈·간격 정리 |
| 화면 검사에 과거 완료 문구와 통계 6개 기준이 남음 | 현재 완료 문구 및 실제 통계 5개 라벨·순서·값을 데스크톱·모바일에서 공통 검증 |
| 임시 도구·캐시·예전 검사 캡처와 결과가 남음 | 임시 파일 117개, 50,284,541바이트 제거. 이번 검사 결과만 새로 생성 |

## 폴더 점검과 삭제 범위

| 위치 | 확인 결과와 처리 |
|---|---|
| `frontend/src/`, `backend/app/` | 모듈·함수·CSS 사용처 확인. 확실하게 미사용인 소스 파일은 없어서 보존 |
| `scripts/` | 14개 모두 모델 준비·검증·백업·복원 등의 역할이나 문서 참조가 있어 보존 |
| `backend/migrations/`, `backend/app/dictionary/` | 적용된 SQL 체크섬과 사전·라이선스 자료 유지 |
| `docs/`, `GANMANTLE_SPEC.md`, `CHANGELOG/` | 과거 모델 명세·측정 JSON·UI 참고 이미지가 문서에서 인용되므로 보존 |
| `.cache/` | 일회성 검사 스크립트·npm/Prettier 캐시·이번에 사용한 Ruff 도구 등 88개, 49,216,222바이트 삭제 |
| `.ruff_cache/` | 서식 도구 캐시 3개, 674바이트 삭제 |
| 기존 `test-results/` | 과거 캡처·검사 결과 26개, 1,067,645바이트 삭제. 이후 이번 UI 검사 결과 15개를 새로 생성 |
| `frontend/node_modules/`, `frontend/dist/` | IDE·로컬 빌드에 쓰는 설치 의존성 유지. `dist`는 최종 코드로 다시 빌드 |
| `.git`, `.env`, `ngrok.local.yml`, DB·모델·백업 | 삭제·초기화하지 않음. 실제 비밀값을 읽거나 변경 기록에 복사하지 않음 |

삭제는 대상 절대 경로가 프로젝트 안의 지정 폴더인지 확인한 뒤 PowerShell `Remove-Item -LiteralPath`로 수행했습니다. Git에서 추적하는 소스 파일 삭제나 폴더 재배치는 없습니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 변경한 내용 |
|---|---|---|
| [api.ts](../../frontend/src/api.ts), [채팅 api.ts](../../frontend/src/chat/api.ts) | `RequestOptions`, `request()`, `chatRequest()` | 중복 HTTP 처리 통합. 타임아웃·취소·오류 문구를 옵션으로 유지 |
| [App.tsx](../../frontend/src/App.tsx) | `requestState()`, `refresh`, `mutate`, `keepImeInput`, `start` | 상태 URL 생성 중복 제거, 여러 줄 조건문에 중괄호 추가 |
| [ChatPanel.tsx](../../frontend/src/chat/ChatPanel.tsx), [Ranking.tsx](../../frontend/src/ranking/Ranking.tsx) | 저장값 읽기·초대 반복문·닉네임 클릭 처리 | 여러 줄 제어 흐름의 범위를 중괄호로 명시 |
| [CompletionPanel.tsx](../../frontend/src/CompletionPanel.tsx), [GuessHistory.tsx](../../frontend/src/ranking/GuessHistory.tsx), [main.tsx](../../frontend/src/main.tsx) | JSX·초기화·함수 사이 간격 | 표시 내용과 동작을 유지하는 줄바꿈 |
| [tsconfig.json](../../frontend/tsconfig.json), [vite.config.ts](../../frontend/vite.config.ts) | TypeScript 옵션·개발 프록시 | 옵션별로 줄을 나누어 표시 |
| [chat.py](../../backend/app/chat.py), [game.py](../../backend/app/game.py), [main.py](../../backend/app/main.py), [users.py](../../backend/app/users.py) | 함수 인자·조건·SQL 호출·반환 사전 | 100자 기준 포맷, 긴 SQL을 동일한 값의 인접 문자열로 분리 |
| [fasttext_bin.py](../../backend/app/fasttext_bin.py), [model_files.py](../../backend/app/model_files.py), [similarity.py](../../backend/app/similarity.py), [word_ranks.py](../../backend/app/word_ranks.py), [words.py](../../backend/app/words.py) | 모델 읽기·검증·벡터·단어 검사 함수 | 인자·조건·컴프리헨션 줄바꿈. 실행 구조 유지 |
| [backend/tests/](../../backend/tests/) | 기존 테스트 함수·fixture·assert | 검사 내용과 fixture 의존성을 유지하며 서식 통일 |
| [benchmark_model.py](../../scripts/benchmark_model.py), [check_fasttext.py](../../scripts/check_fasttext.py), [smoke_ranking.py](../../scripts/smoke_ranking.py) | 벤치마크·실제 모델 검증 | 긴 호출·자료 구조·결과 출력의 줄바꿈 |
| [prepare_dictionary.py](../../scripts/prepare_dictionary.py), [prepare_model.py](../../scripts/prepare_model.py), [prepare_word_ranks.py](../../scripts/prepare_word_ranks.py) | 준비·검증 함수 | 조건·인자·반환값 서식 통일 |
| [recalculate_scores.py](../../scripts/recalculate_scores.py), [serve_chat_check.py](../../scripts/serve_chat_check.py), [setup_env.py](../../scripts/setup_env.py) | 운영 도구 함수 | 실행 동작을 유지하는 포맷 |
| [check_ui.mjs](../../scripts/check_ui.mjs) | `completionLayout()`, 완료 화면 검사, 전체 서식 | 오래된 `.` 기대값을 현재 `!`로 수정. 공통 함수가 정확한 통계 5개를 검증하며 중복 검사 제거 |
| [check_chat_ui.mjs](../../scripts/check_chat_ui.mjs), [check_release.mjs](../../scripts/check_release.mjs) | 전체 검사 함수 | 긴 문장·객체·조건을 줄별로 표시 |
| [db.ps1](../../scripts/db.ps1), [db.sh](../../scripts/db.sh) | 백업·복원 조건·분기·Docker 명령 | 압축된 분기와 긴 명령을 펼침. 안전 검사·명령 인자는 유지 |
| [Dockerfile](../../Dockerfile), [compose.yaml](../../compose.yaml) | `ENV`, `RUN`, `CMD`, `healthcheck.test` | 실행 인자와 설정값을 바꾸지 않고 줄바꿈 |
| [README](../../README.md), [공유 안내](../../docs/DEPLOYMENT.md), [월별 목록](README.md), [전체 목록](../README.md) | 최신 변경·폴더 역할·공유 상태 | 현재 작업과 연결하고 사용자 확인 결과를 구분해 기록 |

## 어떤 코드인가요?

채팅 요청은 자체 fetch 구현 대신 공통 함수를 사용합니다. 일부 발췌입니다.

```ts
export function chatRequest<T>(path: string, body?: object): Promise<T> {
  return request<T>(`/chat${path}`, body, undefined, {
    timeoutMs: 15000,
    invalidResponseMessage: '채팅 응답을 확인하지 못했어요. 잠시 후 다시 시도해 주세요.',
    failureCode: 'chat_failed',
    failureMessage: '채팅 요청을 처리하지 못했어요. 다시 확인해 주세요.',
  });
}
```

모든 Python 변경은 구문 트리(AST)가 변경 전과 같습니다. DB의 SQL 문자열 값·잠금·트랜잭션·마이그레이션 순서와 모델 계산은 바뀌지 않습니다. 긴 URL·고정 해시·원문 SQL 등 줄바꿈으로 의미가 바뀔 수 있는 값은 그대로 둡니다.

## 어떻게 확인했나요?

| 확인 방법 | 실제 결과 |
|---|---|
| Python 34개 파일의 Git HEAD 대비 AST 비교 | 차이 없음. 백엔드·테스트·Python 운영 스크립트 포함 |
| 변경 전후 HTTP 요청 비교 | 18개 통과. GET/POST 옵션, 게임·채팅 타임아웃, 취소 신호, JSON·서버·네트워크 오류 처리 비교 |
| JS 3개 `node --check` 및 실행 코드 정규화 비교 | 통과. 알려진 화면 검사 기준 수정은 별도로 구분 |
| PowerShell 파서·실행 토큰 비교, `sh -n` | 통과. 백업·복원 스크립트는 실제 실행하지 않음 |
| Ruff 0.16.10·기존 Prettier 3.6.2 서식 검사 | 통과. Python 100자·py312, TS/JS/CSS 100자 기준. 도구는 임시 캐시에서 사용 후 제거 |
| Compose 해석값·Dockerfile 명령 비교 | 원본과 동일. 비밀값이 없는 `.env.example` 및 보간 비활성화로 비교 |
| `npm.cmd run build`, `docker compose build app` | TypeScript·Vite·최종 이미지 빌드 통과 |
| 임시 PostgreSQL 스키마의 백엔드 전체 검사 | **288개 통과**, 기존 Starlette/anyio 사용 중단 예정 경고 1개 |
| 로컬 미리보기의 `node scripts/check_ui.mjs` | **33개 통과**. 기존 화면 기준 불일치 수정 후 전체 재실행. 실제 사용자 DB를 쓰지 않는 검사 자료 사용 |
| 코드 교차 검토 | 미사용으로 오인하기 쉬운 pytest fixture·운영 함수 보존, 민감 데이터 파일·SQL 이력·의존성 파일 변경 없음 확인 |
| 현재 실행 중인 앱 확인 | 컨테이너 정상 상태, `/api/health` 및 첫 화면 HTTP 200. 제공 중인 JS·CSS가 최종 빌드 파일과 정확히 일치 |
| `git diff --check` 및 수정 문서의 로컬 링크 검사 | 공백 오류 없음. 로컬 링크 79개 정상, 임시 캐시 삭제와 로컬 설정 파일 보존 확인 |

이번 UI 결과와 화면 캡처만 `test-results/`에 남겼습니다. 패키지·잠금 파일은 변경하지 않았고, 임시로 받은 Ruff는 공식 PyPI의 SHA-256과 일치하는지 확인했습니다.

## 영향과 남은 일

- DB·모델·환경변수·의존성 변경 없음. 사용자 기록 초기화 없음.
- 현재 앱에 반영하고 정상 준비 상태와 HTTP 응답을 확인했습니다. 기존 이미지는 로컬 복구 태그로 보존했습니다.
- 실제 Mac·Safari·새로운 친구 기기에서의 채팅 검증은 이번 코드 정리 검사의 범위에 포함하지 않습니다.
- Git 커밋·GitHub 업로드는 실행하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
