# 간맨틀

한국 시간 자정에 정답이 바뀌는 한국어 단어 유사도 게임입니다. Python/FastAPI·React/TypeScript·PostgreSQL을 Docker로 실행합니다. 기본 게임·사용자 랭킹·전체/개인/방 채팅을 구현했습니다.

**로컬 주소: http://localhost:8000** · 친구에게 잠깐 보여줄 때는 [ngrok 공유 안내](docs/DEPLOYMENT.md)를 사용합니다. 별도 서버를 구매하지 않아도 되며 공유하는 동안 내 컴퓨터와 Docker를 켜 두어야 합니다.

**2026-09-27:** 불필요 코드·중복 모델 정리와 전체 기록 초기화, 로컬 검사를 완료했습니다. GitHub 업로드는 진행 중이며 실제 결과는 [9월 26~27일 변경 기록](CHANGELOG/2026-09/26-001-cleanup-share-github.md)에 남깁니다. 실제 Mac/Apple Silicon·Safari·공개 HTTPS 연결은 아직 확인하지 않았습니다. 이전 검사 결과는 [검증 기록](docs/VALIDATION.md)에서 날짜별로 구분합니다.

## 실행과 종료

명령은 **`compose.yaml`이 있는 폴더**에서 실행합니다. 현재 Windows 폴더는 `C:\Users\rkdms\OneDrive\Desktop\ganmantle\ganmantle-v1`이며 GitHub에서 내려받은 폴더 이름은 달라도 됩니다.

모델과 설정을 이미 준비했다면:

```sh
docker compose up -d
docker compose ps
```

소스를 바꿨으면 `docker compose up -d --build`, 종료는 `docker compose stop`입니다. 오류는 `docker compose logs --tail=60 app`으로 확인합니다. **`docker compose down -v`는 DB와 모델까지 지우므로 평소 종료에 사용하지 않습니다.**

## Windows / Mac에서 처음 준비

Docker Desktop을 **Linux 컨테이너**로 실행합니다. 호스트 Python은 필요하지 않습니다. GitHub의 `main`을 내려받은 뒤 프로젝트 폴더에서 `.env`를 만듭니다.

Windows PowerShell:

```powershell
docker run --rm --mount "type=bind,source=$($PWD.Path),target=/work" -w /work python:3.12.11-slim-bookworm python scripts/setup_env.py
```

Mac 터미널:

```sh
docker run --rm --mount "type=bind,source=$PWD,target=/work" -w /work python:3.12.11-slim-bookworm python scripts/setup_env.py
```

그다음 명령은 Windows/Mac 공통입니다. 원본 모델 다운로드는 약 7.24GB입니다.

```sh
docker compose build app
docker compose run --rm --no-deps --user 0:0 --volume ganmantle-v1_model_data:/model-work:rw app python scripts/prepare_model.py --directory /model-work/fasttext-ko
docker compose run --rm --no-deps --user 0:0 --volume ganmantle-v1_model_data:/model-work:rw app python scripts/prepare_word_ranks.py --directory /model-work/fasttext-ko
docker compose up -d
```

`setup_env.py`는 비밀번호를 포함한 `.env`를 처음 한 번만 만들고 기존 파일을 보존합니다. 모델 다운로드와 순위 준비는 중단 지점부터 재개합니다. 준비 실패는 오류로 안내하며 가짜 점수를 만들지 않습니다.

Compose 이름 `ganmantle-v1`과 모델 볼륨 `ganmantle-v1_model_data`는 고정입니다. 모델은 준비할 때만 `/model-work`에 쓰기 가능하게 연결하고, 앱은 `/models/fasttext-ko`에서 읽기 전용으로 사용합니다. DB는 `postgres_data` 볼륨에 저장합니다. 앱은 localhost에만 열리고 DB 포트는 외부에 열리지 않습니다.

컨테이너 기준은 Python 3.12.11·Node 22.16.0·PostgreSQL 17.5입니다. Windows Linux/amd64 실행은 검증했지만 **실제 Mac과 arm64 모델 실행은 미검증**입니다. Mac에서는 Windows의 설치 산출물을 복사하지 말고 위 절차로 다시 준비합니다.

## 게임 규칙

- 닉네임 설정 후 시작합니다. 입력·횟수·시작/완료 시각은 서버에 저장하며 재접속해도 이어집니다. 쿠키를 지우거나 다른 기기를 쓰면 새 사용자입니다.
- 입력은 앞뒤 공백 제거·NFC 정규화 후 완성형 한글 1~40자로 검사합니다. 사전에 없는 단어도 fastText 문자 조각으로 실제 벡터를 만들 수 있으면 계산합니다. 벡터가 없는 입력은 안내하고 시도에 넣지 않습니다.
- 점수는 **원본 벡터의 코사인 × 100**입니다. 확률이 아니며 임의 보정하지 않습니다. 정답은 단어 일치로 판정합니다.
- 최근 입력은 맨 위에, 나머지는 유사도 내림차순·동점이면 최초 시도 번호순으로 표시합니다. 중복 입력은 기존 행만 최근 영역으로 이동하며 점수·시도 번호·횟수는 유지합니다.
- 단어 순위와 1·10·1,000번째 기준 점수는 같은 모델·고정 비교 집합을 사용합니다. 실제 벡터가 있는 48,978개에서 정답을 제외해 비교하며 정답 후보 90개는 전부 지원합니다. 정답은 0위, 정확한 동점은 공동 순위입니다. 막대는 단일색이며 순위에 따라 길이만 달라집니다.
- 사용자 랭킹은 완료자의 적은 시도 횟수 → 짧은 실제 시간 순입니다. 두 값이 모두 같은 공동 순위일 때만 시간을 표시합니다. 최고 유사도와 단어 순위는 공개하지만 다른 사람의 추측 단어는 숨깁니다.
- 날짜·어제 정답은 서버 데이터입니다. 바로 전날 문제가 없으면 어제 정답을 숨깁니다. 자정에 새 날짜로 전환하고 전날 미완료 도전을 닫습니다.

채팅은 닉네임 설정 후 사용합니다. 개인 대화는 두 사람만, 방 대화는 초대 수락자만 읽고 보냅니다. 메시지는 DB에, 방 선택·초안은 같은 탭의 `sessionStorage`에 저장합니다. SSE 알림을 위해 현재 **FastAPI worker는 1개**입니다.

## 파일 역할과 수정 위치

| 파일·폴더 | 여기서 바꾸는 내용 |
|---|---|
| `frontend/src/App.tsx` | 닉네임·게임·입력 기록과 전체 화면 연결 |
| `frontend/src/styles.css` | 글자·색상·너비·여백·모바일 배치 |
| `frontend/src/ranking/` | 사용자 랭킹·공동 순위 시간, 단어 순위 막대 |
| `frontend/src/chat/` | 작은 채팅 팝업·방·초대·메시지·초안 |
| `frontend/src/api.ts` | 게임 API 요청·응답 타입 |
| `frontend/public/brand-mark.svg` | 로고·파비콘 |
| `backend/app/main.py`, `users.py` | 서버 시작·화면 제공·닉네임·세션 |
| `backend/app/game.py`, `chat.py` | 게임·랭킹 규칙, 채팅 저장·접근 권한 |
| `backend/app/similarity.py`, `fasttext_bin.py`, `word_ranks.py` | 실제 모델 계산·bin 읽기·단어 순위 |
| `backend/app/model_files.py` | 모델 SHA-256 검사·검증 캐시 |
| `backend/app/words.py`, `dictionary/`, `answers.txt` | 입력 형식·비교 사전·정답 후보 |
| `backend/app/db.py`, `backend/migrations/` | DB 연결·순서대로 적용하는 SQL 변경 이력 |
| `backend/tests/`, `scripts/` | 자동 검사·모델 준비·백업·복원 |
| `Dockerfile`, `compose.yaml`, `.env.example` | 앱+DB 실행·비밀값 없는 설정 예시 |
| `.github/workflows/check.yml` | GitHub 자동 검사. 자동 배포 없음 |
| `model-manifest.json`, `docs/MODEL.md` | 현재 모델 버전·체크섬·라이선스·전환 방법 |
| `docs/DEPLOYMENT.md`, `CHANGELOG/` | 친구 공유·업데이트 안내, 파일별 변경 이유·결과 |

별도 AI 서버·채팅 서버·Redis·ORM 계층은 없습니다. React 빌드 결과를 FastAPI가 함께 제공합니다. 변경할 때는 [AGENTS.md](AGENTS.md)와 [변경 기록 양식](CHANGELOG/TEMPLATE.md)을 따릅니다.

화면을 빠르게 수정하려면 `frontend/`에서 Windows는 `npm.cmd ci` → `npm.cmd run dev`, Mac은 `npm ci` → `npm run dev`를 실행합니다. API용 Docker 앱도 켜 두어야 합니다. `npm.cmd run build`(Mac은 `npm run build`)로 타입 검사·화면 빌드를 확인합니다. Node 22.16.0 기준이며 IDE 타입 검사에 필요한 `node_modules`는 기기마다 설치하고 Git에는 넣지 않습니다.

## 모델과 Git에 넣지 않는 데이터

현재 모델은 **한국어 fastText `cc.ko.300` 원본 bin·300차원**입니다. 원본은 7,243,669,409바이트이며 CC BY-SA 3.0입니다. 코드 라이선스·비교 사전·OOV 제한·실측 조건은 [모델 안내](docs/MODEL.md)에 있습니다. 입력 행렬을 메모리 매핑해 실제 단어/문자 조각 벡터를 읽습니다. fastText라는 이유만으로 꼬맨틀과 점수가 같지는 않습니다.

Docker 모델 볼륨의 필수 파일은 다음 4개입니다. 원본은 `prepare_model.py`, 나머지는 `prepare_word_ranks.py`가 준비합니다.

```text
fasttext-ko/model.bin
fasttext-ko/word-ranks/vectors.npy
fasttext-ko/word-ranks/words.json
fasttext-ko/word-ranks/manifest.json
```

Git에는 소스·문서·잠금 파일·DB 변경 이력·`.env.example`·현재 모델 manifest를 넣습니다. 작은 과거 모델 manifest/측정 JSON은 선정 근거를 남기는 자료이며 실행 모델이 아닙니다. 실제 `.env`, `ngrok.local.yml`, DB·백업·모델 실물·`node_modules`·`dist`·캐시·`test-results`는 Git과 Docker 빌드에서 제외합니다.

## DB 백업·복원과 Mac 이전

Mac에서 새로 시작하려면 빈 DB로 실행하면 됩니다. 기존 게임·채팅을 옮길 때만 **논리 백업과 새 DB 복원**을 사용합니다. PostgreSQL 데이터 폴더나 실행 중인 볼륨은 복사하지 않습니다.

Windows:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/db.ps1 backup
powershell -ExecutionPolicy Bypass -File scripts/db.ps1 restore -File backups/백업파일.dump -Database ganmantle_restore_check
```

Mac:

```sh
sh scripts/db.sh backup
sh scripts/db.sh restore backups/백업파일.dump ganmantle_restore_check
```

복원 도구는 기존 DB를 덮어쓰지 않습니다. 새 DB의 기록 확인 후 `.env`의 `POSTGRES_DB`를 바꾸고 `docker compose up -d`로 앱·DB 환경을 함께 반영합니다. 브라우저 쿠키는 자동 이전되지 않습니다. 적용한 `001`·`002`·`003` SQL은 현재 앱에 필요하므로 유지하고, 다음 구조 변경은 `004_설명.sql`로 추가합니다.

## 확인 방법과 남은 검증

앱·DB·모델을 준비한 뒤 프로젝트 루트에서 실행합니다.

```sh
docker compose exec -T app sh -c 'TEST_DATABASE_URL="$DATABASE_URL" pytest -q -p no:cacheprovider backend/tests'
docker compose exec -T app python scripts/smoke_ranking.py
docker compose exec -T app python scripts/prepare_dictionary.py --check
```

`pytest`는 임시 PostgreSQL 스키마의 규칙 검사, `smoke_ranking.py`는 실제 모델의 게임·순위 검사입니다. 사용자 기록은 수정하지 않습니다. 호스트 Node 24 이상과 Chrome이 있으면 `node scripts/check_ui.mjs`로 검사 자료 기반 화면을, `node scripts/check_chat_ui.mjs`로 [별도 서버의 실제 채팅](docs/VALIDATION.md)을 확인할 수 있습니다.

`node scripts/check_release.mjs`는 별도 DB·localhost 포트에서 실제 모델·재시작·논리 백업/복원을 검사하고 만든 자원을 정리합니다. 실제 자정까지 20분 이상 남았을 때 실행합니다. GitHub Actions는 큰 모델을 받지 않고 잠금 파일 빌드·규칙 검사만 수행합니다.

현재 작업의 실제 실행 결과와 초기화 범위는 [최신 변경 기록](CHANGELOG/2026-09/26-001-cleanup-share-github.md)을 따릅니다. 실제 Mac/arm64·Safari·실제 모바일 기기, 외부 공유 링크의 로그인·채팅 연결은 별도로 확인해야 합니다. 서버 구매와 상시 공개 배포는 이번 범위가 아닙니다.
