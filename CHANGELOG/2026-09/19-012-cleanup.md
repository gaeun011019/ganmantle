# 2026-09-19 — 불필요한 파일 정리·코드 단순화·전체 기록 초기화

- 기록 ID: 2026-09-19-012
- 분야: 서버 / 화면 / DB / 모델 / 검사 / 환경 / 문서
- 유형: 삭제 / 수정 / 변경
- 구현 상태: 완료
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

현재 기능에 사용하지 않는 모델·캐시·옛 검사 산출물·백업을 지우고, 읽지 않는 코드와 중복 처리를 정리했습니다. 사용자가 “현재 기록도 전부 초기화”라고 답한 범위에 따라 닉네임·게임·입력·채팅 기록을 삭제했습니다. 게임·순위·채팅의 기능과 폴더 구분은 유지합니다.

| 변경 전 | 변경 후 |
|---|---|
| E5와 현재 MiniLM 파일이 함께 있고 옛 검사 프로필·백업이 쌓임 | 현재 MiniLM의 필수 5개 파일만 유지하고 검사 프로필은 종료 후 자동 정리 |
| 쓰지 않는 채팅 타입·값·CSS, 초대 대상의 중복 DB 조회 | 기존 타입 재사용, 미사용 선언과 중복 조회 삭제 |
| 모델은 읽혔으나 오늘 문제의 모델 지문이 달라도 health가 준비 완료로 응답 | 게임과 동일한 모델 상태 검사로 불일치 안내 |
| IDE용 `node_modules`가 없는 상태 | 잠금 파일 기준 재설치, TypeScript 미사용 선언 검사 활성화 |
| 현재 게임·채팅 기록과 별도 복원 검사 DB가 남음 | 사용자 기록 전체 초기화, 복원 검사 DB 2개 삭제, 필요한 DB 구조 유지 |

## 삭제한 항목과 유지한 항목

삭제한 로컬 항목은 `models/multilingual-e5-small/`(135,390,915바이트), `.cache/`, `.pytest_cache/`, 기존 `test-results/`(약 188.74MiB), `backups/`의 기존 백업 3개, 미사용 `GANMANTLE_LOGO.png`, `scripts/smoke_test.py`, 호스트 빌드 후의 `frontend/dist/`입니다. 삭제 전에 절대 경로가 프로젝트 안인지와 링크 대상이 아닌지 확인했습니다. 새 검사 결과 JSON·캡처는 같은 `test-results/`에 다시 생성하며 Git/Docker에서는 제외합니다. Docker 이미지의 화면 빌드 결과는 앱 실행에 필요하므로 유지합니다.

사용 중인 컨테이너가 없는 것을 확인한 뒤 이전 프로젝트 이미지 `ganmantle-v1-app:before-model-20260919`와 `ganmantle-deps:local`도 삭제했습니다. 다른 프로젝트나 기반 이미지에 대한 일괄 정리는 하지 않았습니다.

`smoke_test.py`는 실제 앱에 검사 사용자를 남기는 초기 도구였습니다. 현재는 격리된 `smoke_ranking.py`, 규칙 검사, 실제 채팅 검사로 확인합니다. 삭제가 과거의 실제 컨테이너 재시작 검사까지 동일하게 대체한다는 뜻은 아닙니다.

현재 모델의 ONNX·tokenizer·사전 벡터·단어 목록·manifest 5개(합계 212,014,297바이트)는 실제 계산에 모두 필요합니다. 작은 E5 manifest·비교/벤치마크 JSON과 `compare_models.py`는 선정 근거 재현을 위해 유지합니다. IDE 타입 검사에 필요한 `frontend/node_modules`, 소스·사전 출처/라이선스·잠금 파일·검사 코드·SQL 이력·`.env.example`·사용자 UI 참고 이미지도 유지합니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 변경 내용 |
|---|---|---|
| [App.tsx](../../frontend/src/App.tsx) | `chatContact`, `onContact` | 별도 `ChatContact`와 사용하지 않는 `requestId`를 제거하고 `ChatUser`와 setter 재사용 |
| [ChatPanel.tsx](../../frontend/src/chat/ChatPanel.tsx), [chat/api.ts](../../frontend/src/chat/api.ts) | `contact` 타입 | 기존 사용자 타입으로 통일. 닉네임 클릭마다 새 객체를 전달하는 동작 유지 |
| [styles.css](../../frontend/src/styles.css) | `.pending-label`, `.chat-empty-icon`, `.chat-compose input`, `--muted` | 미사용 선택자·변수 제거, 중복 선언 정리, 최종 배치 유지 |
| [tsconfig.json](../../frontend/tsconfig.json) | `noUnusedLocals`, `noUnusedParameters` | 새 미사용 코드가 빌드에서 발견되도록 설정 |
| [main.py](../../backend/app/main.py) | `health()` | `game.model_status()`로 실제 오늘 문제와 모델 지문을 함께 검사. 중복 `SELECT 1` 제거 |
| [chat.py](../../backend/app/chat.py) | `create_room()`, 상수 | 미사용 `GLOBAL_ROOM_ID` 제거. `invite()`가 수행하는 사용자 존재 검사 중복 제거 |
| [test_rules.py](../../backend/tests/test_rules.py) | 기존 모델 불일치 검사 | health 응답도 같은 불일치를 보고하는지 확인 추가 |
| [test_chat.py](../../backend/tests/test_chat.py) | 기존 방 생성 입력 검사 | 없는 초대 대상일 때 404와 방 생성 전체 롤백 확인 추가 |
| [check_ui.mjs](../../scripts/check_ui.mjs), [check_chat_ui.mjs](../../scripts/check_chat_ui.mjs) | `finally`, `profileCreated`, `hasExited()` | 이번 Chrome의 종료 이벤트·코드·OS 프로세스 존재 확인 후 해당 프로필만 삭제. 경로 검증·실패 보고 추가. 실제 채팅 검사 전에 격리 서버의 모델·순위 준비 확인 |
| [db.sh](../../scripts/db.sh) | `restore`의 검증 `psql` | `-v ON_ERROR_STOP=1`로 조회 오류를 복원 성공으로 표시하지 않게 수정 |
| [README](../../README.md) | 현재 상태·파일 역할·실행 방법 | 반복된 과거 설명을 줄이고 현재 모델·필수 파일·IDE 준비·검사 순서 중심으로 정리. 복원 DB로 전환할 때 앱과 DB 컨테이너의 환경변수를 함께 갱신해 이후 백업 대상도 일치하도록 안내 |
| [MODEL](../../docs/MODEL.md), [SPEC](../../GANMANTLE_SPEC.md), [VALIDATION](../../docs/VALIDATION.md) | 현재 상태·검사 안내 | 삭제/유지 범위와 새 결과, 현재 검사 명령, 실제 미검증 환경 구분 |
| [001](19-001-game.md), [004](19-004-environment.md), [007](19-007-word-validation.md) | 삭제 도구의 과거 링크 | 당시 실행 사실을 유지하고 후속 삭제 안내와 링크 정정 |
| [월 목록](README.md), [전체 목록](../README.md) | 최신 012·다음 013 | 이번 변경 기록 연결 |

## 어떤 코드인가요?

`main.py`의 `health()` 일부입니다. 단순 모델 로딩 여부 대신 실제 게임에서 사용하는 상태 판단을 재사용합니다.

```python
with db.connect() as conn:
    model = game.model_status(conn, game.puzzle_date(game.utcnow()), current_engine(request))
return {"status": "ok" if model["ready"] else "model_unavailable", "database": True,
        "model": model}
```

화면은 기존의 `ChatUser`만 사용하고 `onContact={setChatContact}`로 연결합니다. 랭킹 닉네임을 누를 때마다 새 `{id, nickname}` 객체가 만들어지므로 같은 사람을 다시 눌러도 대화 선택 효과가 실행됩니다.

Chrome 검사 도구는 자신이 생성한 프로필을 표시하고, 자식 브라우저의 종료를 확인한 뒤 `realpath`로 `test-results`의 직접 자식인지 확인합니다. Windows에서 종료 이벤트가 늦으면 `process.kill(pid, 0)`으로 OS에도 PID가 없는지 확인하며 `ESRCH`만 종료로 판단합니다. 종료가 안 됐을 때 강제 종료 대상도 자신의 자식 PID로 한정합니다. 다른 실행의 프로필과 사용자 브라우저는 정리 대상이 아닙니다. 정리에 실패하면 `cleanup_error`와 실패 종료 코드를 남기며, stderr 핸들을 닫아 검사 프로세스가 무한 대기하지 않게 합니다.

## DB 초기화 범위

앱을 멈추고 `ganmantle` DB의 사용자·게임·입력·문제·채팅 메시지/초대/멤버/방을 한 트랜잭션에서 `TRUNCATE ... RESTART IDENTITY`로 비웠습니다. 전체 채팅에 필요한 기본 방 1개를 다시 넣었습니다. `schema_migrations`와 `001_initial.sql`·`002_chat.sql`·`003_score_update.sql`은 삭제하거나 수정하지 않았고 적용 파일·체크섬 불변을 확인했습니다.

연결이 없고 현재 DB가 아닌 것을 확인한 후 `ganmantle_restore_validation_20260919`와 `ganmantle_restore_validation_20260919_v2`를 삭제했습니다. 필수 앱 DB와 PostgreSQL 관리/템플릿 DB는 유지합니다. 이후 첫 조회에서 새 오늘의 문제 1개가 생성될 수 있으며 과거 기록 복원이 아닙니다. 데이터 폴더·Docker 볼륨을 복사하거나 초기화하지 않았습니다.

## 어떻게 확인했나요?

| 이번에 실행한 검사 | 결과 |
|---|---|
| 호스트 의존성·타입·화면 | `npm.cmd ci --no-audit --no-fund` 설치, `npm.cmd run build` 통과. 미사용 지역 변수/매개변수 검사 포함 |
| Docker 이미지 | TypeScript·Vite 빌드 및 최종 소스 반영 성공 |
| 서버 전체 회귀 | **114 passed, 235.13초**. 실제 PostgreSQL 임시 스키마, 규칙용 모델·시계 사용 |
| 이번 서버 수정 | 오늘 모델 지문 불일치가 health에도 반영, 없는 초대 대상의 404·방 생성 전체 롤백 통과 |
| 기존 게임·채팅 | 중복·정답·시간 유지·재접속·자정·순위 경계·동시성·권한 검사 통과 |
| 실제 모델·PostgreSQL | `smoke_ranking.py` 통과. 미등록 입력 차단, 독립 코사인×100, 전체 사전 순위/기준 점수, 정답 0위, 두 사용자·랭킹·재접속·중복·임시 스키마 정리 |
| Chrome 화면 | **16개 통과**, JavaScript 오류 0. 화면은 검사 전용 API 자료이며 실제 모델 검사와 구분. `profile_cleanup.removed=true` |
| 실제 채팅 브라우저 | **9개 통과**, JavaScript 오류 0. 실제 API·PostgreSQL·SSE와 서로 다른 세 세션, 탭별 초안, 모바일 경계 확인. `profile_cleanup.removed=true`. 종료 후 임시 스키마 정리 |
| DB 복원 셸 | 최종 이미지의 `sh -n scripts/db.sh` 통과. 실제 Mac의 복원과 논리 백업/복원은 이번에 재실행하지 않음 |
| 문서 링크 | 관련 문서 10개의 로컬 링크 오류 0개 |
| 최종 실행·정리 | 최종 이미지의 앱·DB healthy, `/` 200·health ok·모델/49,485개 순위 준비 정상. 사용자·게임·랭킹 비어 있음, 검사 스키마 0·프로필 폴더 0, 최종 검사 파일 8개 약 0.37MiB |

이번에도 Starlette 내부의 anyio 별칭 사용 중단 예정 경고 1개가 발생했습니다. 테스트 실패가 아니며 경고를 숨기거나 의존성 버전을 임의로 바꾸지 않았습니다. 실제 IDE 진단 목록은 제공받지 못해 타입 검사·빌드 확인과 구분합니다.

중간 검사에서는 CDP 연결 종료와 Windows의 Chrome 종료 이벤트 지연으로 프로필 정리가 실패했습니다. 종료 코드와 OS의 PID 존재 확인을 추가한 후 화면 검사·자동 정리가 모두 통과했습니다. 실제 채팅 첫 닉네임 화면의 대기 초과에는 검사 시작 전 모델·전체 단어 순위 준비 확인을 추가했습니다. 여러 탭의 대기·캡처 전에는 검사할 탭을 활성화하고 같은 이름의 중복 캡처를 제거했습니다. 최종 실제 채팅 9개와 자동 정리가 모두 통과했습니다. 이전 단계의 통과 횟수를 이번 결과로 재사용하지 않았습니다.

DB 컨테이너의 `/tmp`에 남아 있던 간맨틀 임시 백업 1개(11,627바이트)도 확인 후 삭제했습니다. 검사 실패 도중 남은 프로필과 실패 캡처는 실행 프로세스가 없는지 확인한 뒤 정리하고, 최종 통과 JSON·캡처만 남깁니다.

## 영향과 남은 일

- 현재 기록과 기존 백업을 삭제했으므로 기존 닉네임·게임·채팅은 복원되지 않습니다. 새로 접속하면 닉네임 설정부터 시작합니다.
- 설정 키·잠금 파일·DB 스키마·현재 모델·점수/순위 계산식 변경은 없습니다. `.env`의 비밀값은 그대로 분리합니다.
- 실제 Mac/arm64·모바일 기기·Safari는 이번에 확인하지 않았습니다. IDE 진단 화면 자체를 읽지는 못했으며 호스트의 실제 TypeScript 검사·빌드 결과로 구분해 보고합니다.
- GitHub 업로드와 공개 배포는 하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
