# 2026-09-26 — 불필요 코드·모델 정리, 전체 초기화와 친구 공유 준비·GitHub 등록

- 기록 ID: 2026-09-26-001
- 작업일: 2026-09-26 시작, 2026-09-27 구현·로컬 검사 완료. 시작일 파일 이름 유지
- 분야: 서버 / 화면 / DB / 모델 / 환경 / 문서
- 유형: 삭제 / 단순화 / 수정 / 추가
- 구현 상태: 완료 — 구현·로컬 검사·GitHub 등록. ngrok는 사용자 선택에 따라 공유 준비까지만 완료
- 관련 커밋: [db09e53](https://github.com/gaeun011019/ganmantle/commit/db09e5372ff891d6a57cc6e4999bcb754ba2908c) — 현재 구현 최초 등록. 이 문서의 완료 결과 정리는 후속 문서 커밋에 포함

## 무엇이 달라졌나요?

현재 fastText 게임·랭킹·채팅에 필요한 구성을 유지하며 과거 모델 지원과 중복 파일을 정리했습니다. 사용자가 “현재 기록도 전부 초기화”를 선택해 닉네임·게임·채팅 데이터를 모두 초기화했습니다. ngrok 계정이 아직 없어 실제 터널 연결은 하지 않고 공유 안내와 비밀값 없는 설정 예시를 준비했습니다.

빈 [GitHub 저장소](https://github.com/gaeun011019/ganmantle)에 현재 프로젝트를 처음 등록했으므로 `main` 하나를 사용합니다. 최초 push와 원격 자동 검사 성공을 확인했습니다. 이 작업의 GitHub 업로드는 사용자 요청 범위이며 서버 구매·상시 공개 배포는 포함하지 않습니다.

| 변경 전 | 변경 후 |
|---|---|
| fastText와 사용하지 않는 ONNX 지원·format 1 호환 코드가 공존 | 현재 fastText bin·format 2 순위 자료 경로로 정리 |
| Linux 실행 모델 외에 호스트 MiniLM·fastText 복사본 보관 | 실행용 Docker 모델 볼륨만 유지 |
| 기존 닉네임·게임·입력·채팅과 백업 보관 | 사용자 요청에 따라 전부 초기화, DB 구조·기본 전체 채팅방 유지 |
| README에 현재 실행·과거 검사·MiniLM 복구 안내 혼재 | 실행 명령·수정 위치를 앞에 두고 이전 측정은 역사 자료로 구분 |
| ngrok 공유 설정 예시 없음 | `ngrok.example.yml`과 단계별 공유·종료 안내 제공 |
| 로컬 Git 저장소 없음, 원격 빈 저장소 | 프로젝트 루트를 `main`에 최초 등록, 원격 자동 검사 성공 |

## 어디를 수정했나요?

| 파일 | 코드 위치 | 추가·변경한 내용 |
|---|---|---|
| [backend/app/similarity.py](../../backend/app/similarity.py) | `SimilarityEngine.__init__`, `vector` | ONNX·MiniLM·E5·Tokenizer 추론 삭제, 실제 fastText word/subword 계산 유지. 모델 지문 계산식 불변 |
| [backend/app/word_ranks.py](../../backend/app/word_ranks.py) | `WordRankIndex` | 현재 300차원·format 2만 지원, 사용하지 않는 이전 format 1 호환 제거 |
| [scripts/prepare_model.py](../../scripts/prepare_model.py), [prepare_word_ranks.py](../../scripts/prepare_word_ranks.py) | manifest 확인·`prepare` | fastText 알고리즘만 허용, 모델 차원 직접 사용, format 1 재개 분기 제거 |
| [scripts/benchmark_model.py](../../scripts/benchmark_model.py) | `EXAMPLES`·`main` | 20쌍 품질 예시 통합, ONNX 측정 분기 제거. 실제 fastText 사전 안팎·원본 벡터·순위 검산 유지 |
| 삭제: `scripts/compare_models.py` | `EXAMPLES`·`measure` | 사용하지 않는 E5/MiniLM 비교 도구 제거. 필요한 예시만 현재 benchmark로 통합 |
| [backend/requirements.in](../../backend/requirements.in), [requirements.lock](../../backend/requirements.lock) | 런타임·검사 의존성 | ONNX/tokenizers와 불필요 전이 패키지 17개 삭제, 42→25개. 남은 버전·해시 유지 |
| [test_model_download.py](../../backend/tests/test_model_download.py), [test_model_files.py](../../backend/tests/test_model_files.py), [test_word_ranks.py](../../backend/tests/test_word_ranks.py), [test_word_rank_preparation.py](../../backend/tests/test_word_rank_preparation.py) | 모델 명세·차원·형식 검사 | 현재 fastText·300차원·format 2 검사 자료로 맞추고 이전 형식 거절 확인. 준비/캐시 검사 fixture의 필수 알고리즘 보완 |
| [.gitignore](../../.gitignore), [.dockerignore](../../.dockerignore) | `ngrok.local.yml` | 실제 공유 비밀번호 정책 파일이 Git·이미지에 들어가지 않게 제외 |
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | 상태 조회 effect·자정 effect·`game-summary` | 자동 조회 10→30초, 500ms 반복 렌더 대신 자정 1회 타이머, 닉네임 표시의 중복 조건 제거 |
| [scripts/check_ui.mjs](../../scripts/check_ui.mjs), [scripts/check_chat_ui.mjs](../../scripts/check_chat_ui.mjs) | `chromePath`·Chrome 시작 대기 | `CHROME_PATH` 우선, OS별 기본 Chrome 경로 선택. 시작 포트 대기 15→30초 |
| [README.md](../../README.md) | 실행·파일 역할·모델·DB 이전·확인 방법 | 현재 fastText 실행 기준으로 안내를 줄이고 공유 안내 연결 |
| [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md) | 친구 공유·GitHub 자동 검사·모델 자원 | ngrok 계정 설정부터 비밀번호 정책·origin·종료까지 안내. 상시 서버 구매는 현재 범위에서 분리 |
| [ngrok.example.yml](../../ngrok.example.yml) | `on_http_request` → `basic-auth` | 실제 비밀번호가 없는 공유 정책 예시. 개인 복사본은 `ngrok.local.yml` |
| [docs/MODEL.md](../../docs/MODEL.md) | 모델 위치·이전·지원 형식 | 삭제한 호스트 복구본·MiniLM 실행 안내 정리, 현재 Docker fastText 모델과 과거 자료 구분 |
| [backend/app/dictionary/README.md](../../backend/app/dictionary/README.md) | 실제 순위 비교 집합 | format 2 현재 기준과 이전 자료 재준비 안내 |
| [GANMANTLE_SPEC.md](../../GANMANTLE_SPEC.md) | 맨 위 현재 작업 기준 | 이번 초기화·공유 준비·GitHub 요청과 과거 보존 원칙 구분 |
| [docs/VALIDATION.md](../../docs/VALIDATION.md) | 맨 위 최신 작업 연결 | 이전 검사 수치를 이번 결과로 오해하지 않게 날짜 구분 |
| [전체 목록](../README.md), [월별 목록](README.md) | 최신 항목 | 이번 변경 기록 연결 |

역사 자료인 작은 E5/MiniLM manifest·측정 JSON은 실행 경로와 분리해 보존합니다. `test_model_files.py`의 ONNX 이름 임시 파일은 파일 검증 로직용 자료이며 ONNX 런타임을 사용하지 않아 유지합니다.

## 실제 정리 범위

- 호스트 `models/`: 미사용 MiniLM과 중복 fastText 원본 등 6개 파일, 7,455,683,706바이트 삭제. 실행용 `ganmantle-v1_model_data`의 bin·순위 자료 3개는 보존.
- 호스트 `backups/`: 과거 `.dump` 2개, 49,515바이트 삭제.
- 호스트 `test-results/`: 이전 생성물 25개, 716,458바이트 삭제. 이번 검사 결과는 새로 생성하며 Git에 넣지 않음.
- 호스트 `frontend/dist/`는 재생성 가능한 빌드 산출물이므로 삭제. Docker 앱 이미지 내부의 실행용 화면 빌드는 유지. IDE 타입 검사에 필요한 `node_modules`는 유지하되 Git에서 제외.
- 이전 앱 이미지의 `before-stage4-20260921`·`latest` 태그와 공통 이전 이미지 삭제. 새 앱 이미지는 약 352MB로 이전 약 580MB보다 작아짐. 다른 이미지나 전체 빌드 캐시를 광범위하게 삭제하지 않음.
- DB는 `ganmantle` 앱 DB와 PostgreSQL 기본 관리 DB만 확인. 별도 검사 DB·남은 검사 스키마는 없어 삭제하지 않음.
- 앱을 멈춘 뒤 앱 데이터 8개 테이블에 `TRUNCATE ... RESTART IDENTITY`를 적용하고 기본 전체 채팅방 1개만 재생성. 사용자·문제·게임·입력·메시지·멤버·초대는 모두 0개, 채팅방은 1개, `schema_migrations` 3개는 유지.
- 소스·잠금 파일·SQL 이력·사전 원본과 라이선스·작은 과거 모델 manifest/측정 JSON·완료한 CHANGELOG는 보존.
- `scripts/compare_models.py`는 E5/MiniLM 비교용으로 삭제하며 한국어 비교 예시 20쌍은 현재 `scripts/benchmark_model.py`로 옮겨 계속 사용. 과거 [19-011 기록](19-011-similarity-model.md)의 이 파일 링크 1개는 삭제 후 열리지 않음. 완료 기록을 다시 쓰거나 불필요한 대체 파일을 만들지 않으며, 최초 Git 등록 전 파일이라 삭제 전 전체 소스의 Git 이력도 없음. 당시 측정 JSON·이유·핵심 코드는 과거 기록에 남아 있음.

## 모델 경로 단순화

변경 전에는 manifest에 따라 fastText와 ONNX/Tokenizer 모델을 분기하고 기존 format 1 순위도 읽었습니다. 변경 후 현재 게임에 쓰는 fastText 알고리즘과 format 2만 허용합니다. 사전 안팎 입력은 모두 원본 bin에서 계산하며 준비된 비교 벡터 조회로 대체하지 않습니다.

`similarity.py`의 알고리즘 확인과 벡터 읽기 일부(두 위치에서 발췌):

```python
if manifest["algorithm"] != "fasttext-bin-subword-mean-l2-cosine100-v1":
    raise ModelUnavailableError("fastText .bin 모델 명세가 필요합니다.")
# ... 파일 검사와 로더 준비 후 vector()에서
result = self.fasttext.get_word_vector(text)
```

L2 정규화와 공통 `cosine_scores()`의 코사인 × 100, 입력 점수·단어 순위·기준 점수의 비교 기준은 그대로입니다. 현재 모델의 revision·알고리즘·파일로 만드는 지문도 바꾸지 않아 유지한 fastText 순위 산출물을 다시 만들 필요가 없습니다.

## 화면 조회 단순화

변경 전에는 게임 상태를 10초마다 조회하고 표시하지 않는 경과 시간을 위해 500ms마다 앱 전체를 다시 렌더링했습니다. 변경 후 평상시 조회는 30초마다 실행하며 입력·탭 복귀·온라인 복귀·다른 탭 알림은 즉시 반영합니다. ngrok의 요청 사용량을 줄이기 위한 변경이며 게임 시간·정답 판정은 계속 서버가 계산합니다.

`App.tsx`의 새 자정 타이머 일부:

```tsx
const remaining = anchor.current.resetAfter - (performance.now() - anchor.current.at);
const timer = window.setTimeout(() => checkDate(n => n + 1), Math.max(0, remaining) + 1);
return () => window.clearTimeout(timer);
```

서버의 `next_reset_at - server_now`와 기기 시계 변경에 영향을 받지 않는 `performance.now()`를 사용합니다. 새로운 상태가 오면 이전 타이머를 정리하고 다시 예약합니다. 자정 때 요청이 진행 중이거나 연결이 실패하면 완료 응답·다음 상태 조회·탭 복귀로 다시 확인합니다. 글자 크기·굵기·색·막대·여백은 바꾸지 않았습니다.

## 어떤 설정인가요?

실제 비밀번호는 포함하지 않는 예시입니다. 공유용 파일은 복사 후 사용자가 로컬에서 직접 수정합니다.

```yaml
on_http_request:
  - actions:
      - type: basic-auth
        config:
          realm: ganmantle-friends
          credentials:
            - "CHANGE_ME:REPLACE_WITH_A_PRIVATE_PASSWORD"
          enforce: true
```

`ngrok http 8000 --traffic-policy-file ngrok.local.yml`은 비밀번호 정책을 적용해 localhost 앱을 연결합니다. 실제 `.env`의 `APP_ORIGIN`과 `COOKIE_SECURE`를 공유 주소에 맞춰야 합니다. ngrok 인증 토큰과 비밀번호는 Git·CHANGELOG에 넣지 않습니다. [공식 정책 문서](https://ngrok.com/docs/gateway/traffic-policy/actions/basic-auth), [무료 제한](https://ngrok.com/docs/pricing-limits/free-plan-limits)을 2026-09-26 확인했습니다.

## 어떻게 확인했나요?

| 확인 방법 | 결과 |
|---|---|
| 삭제 대상 절대 경로와 workspace 범위 확인 | 확인 후 명시된 호스트 모델·백업·과거 검사 산출물만 삭제 |
| DB 최종 행 개수·저장 공간 확인 | 사용자·문제·게임·입력·메시지·멤버·초대 모두 0, 기본 전체방 1, SQL 이력 3. DB는 관리용과 앱용만, public 스키마만, 앱 DB·모델 볼륨 2개만 유지 |
| 현재 안내 문서 9개 로컬 파일 링크 | 135개 모두 존재 확인. 완료한 과거 CHANGELOG의 삭제 파일 링크와 구분 |
| ngrok 공식 문서·비밀값 없는 예시 | 공식 basic-auth 정책·무료 제한 확인. 계정 연결과 실제 터널 실행은 하지 않음 |
| 브라우저 검사 도구 구문 | `node --check scripts/check_ui.mjs`, `node --check scripts/check_chat_ui.mjs` 각각 exit 0. Chrome 실제 실행 결과와 별개 |
| Docker 앱 이미지 | 새 이미지 빌드 통과. TypeScript·Vite 화면 빌드와 25개 고정 해시 패키지 설치 완료 |
| 로컬 앱·의존성·사전 | 앱·DB running/healthy, `pip check` 통과, 비교 사전 49,485개 검사 통과 |
| 화면 검사 | `check_ui.mjs` **22/22 통과**, JavaScript 오류 0. 1600×1500·390×844·320×844에서 확인. 검사 전용 API 자료이며 실제 사용자 기록이나 모델 점수 검사가 아님 |
| 실제 모델 재시작·논리 복원 | `check_release.mjs` **6/6 묶음 통과**. 실제 fastText 점수·단어 순위·중복·시간·채팅·재시작·pg_dump/pg_restore·재접속 확인 |
| 통합 검사 자원 정리 | 이번 검사 컨테이너·DB·임시 설정 정리 확인. 실사용 DB와 공유 모델은 검사와 분리 |
| 전체 pytest | **최종 252개 통과, 135.75초**, Starlette TestClient의 AnyIO 별칭 폐기 예정 경고 1개. 첫 실행의 준비/검증 fixture 알고리즘 누락 2개를 수정해 전체 재검사 통과 |
| GitHub 업로드 | `main` 최초 push 성공, `origin/main` 추적 설정. 코드 커밋 `db09e5372ff891d6a57cc6e4999bcb754ba2908c` |
| 원격 자동 검사 | 최초 코드 커밋의 [Actions 실행](https://github.com/gaeun011019/ganmantle/actions/runs/36252031245)이 `completed/success`. 이후 문서 정리 커밋의 별도 실행 결과와 구분 |
| 업로드 대상·비밀값 검사 | 110개 소스·문서 파일 확인. 제외 산출물 위반 0, 토큰 패턴 일치 0, 실제 `.env` 비밀값이 들어간 업로드 파일 0. 모델·DB·백업·실제 설정은 업로드하지 않음 |

## 영향과 남은 일

- DB 구조 변경 없음. 사용자가 요청한 전체 기록 초기화이며 평소 업데이트 절차가 아님. 새 접속에서 닉네임부터 시작하고 날짜별 문제는 서버 상태 조회 때 생성될 수 있음.
- 공유는 **준비까지만** 요청받은 상태. ngrok 설치·계정·로컬 토큰·개인 정책 비밀번호를 준비한 뒤 외부 접속·채팅을 확인해야 함.
- 실제 Mac/Apple Silicon·Safari·실제 모바일 기기와 상시 공개 운영 부하는 이번에도 미검증. 검사 스크립트의 Mac/Linux Chrome 기본 경로는 추가했지만 해당 OS에서 실행하지 않았음. 30초 시작 대기는 이전 Chrome 기동 지연의 여유를 늘리는 조치이며 모든 기동 오류가 해결됐다는 보장은 아님.
- 구현·로컬 검사·GitHub 최초 등록과 해당 코드의 원격 검사를 완료. 앱 런타임은 실제 모델·화면 검사를 통과한 코드 그대로이며 최종 pytest 보완은 검사 자료의 알고리즘 필드뿐임.
- Windows의 샌드박스/실행 계정 소유권 차이로 생긴 Git 실행 오류는 현재 Windows 계정의 `safe.directory`에 이 프로젝트의 정확한 경로 1개만 등록해 해결. 전체 경로를 허용하는 와일드카드는 사용하지 않음.
- 기록의 원격 검사 성공은 위 코드 커밋의 결과. 뒤이어 올라가는 완료 결과 문서 커밋의 검사는 별도 실행이며 실제 최신 상태는 저장소 Actions에서 확인.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
