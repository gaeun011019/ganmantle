# 간맨틀 친구 공유와 실행 관리

현재 사용 방식은 **내 PC의 간맨틀을 ngrok 링크로 친구에게 잠깐 공유**하는 것입니다. 앱 하나와 PostgreSQL 하나를 유지합니다. 서버 구매·상시 공개 배포는 진행하지 않습니다. 최신 GitHub 반영 범위는 [10월 4일 변경 기록](../CHANGELOG/2026-10/04-004-github-update.md)을 확인합니다.

**Windows에서 맥으로 서버를 옮기거나 맥에서 관리하려면 [Mac 실행·관리 안내](MAC.md)를 먼저 보세요.** 현재 소스 준비, 최초 실행, 최종 DB 백업·새 DB 복원, 같은 ngrok 주소로 전환하는 순서가 있습니다. 맥에서 플레이만 하는 경우에는 기존 HTTPS 링크를 사용하면 됩니다.

## 친구에게 ngrok 링크로 공유

**2026-10-04 Windows 확인:** ngrok 계정 연결·공유 인증·HTTPS 설정을 마쳤고, 실제 외부 주소에서 인증 후 게임 화면이 열리는 것을 사용자가 확인했습니다. 아래는 처음 준비하거나 다른 기기로 옮길 때의 절차입니다. PC가 절전 상태가 되거나 Docker·앱·ngrok를 종료하면 친구의 접속도 끊깁니다. DB 기록은 볼륨에 남습니다.

1. [ngrok 공식 다운로드](https://ngrok.com/downloads)에서 Windows 또는 Mac용 프로그램을 설치하고 계정을 만듭니다. 공식 시작 안내대로 `ngrok config add-authtoken`에 **본인의 토큰을 로컬 터미널에서만** 설정합니다. 토큰은 프로젝트의 `.env`나 Git에 넣지 않으며 채팅으로 전달하지 않습니다. [설치·계정 연결 안내](https://ngrok.com/docs/getting-started/).
2. 프로젝트 루트의 [ngrok.example.yml](../ngrok.example.yml)을 **`ngrok.local.yml`**로 복사합니다. `credentials`의 아이디·비밀번호 자리표시자를 직접 바꿉니다. 비밀번호는 8~128자이며 영문·숫자를 섞은 충분히 긴 값을 사용합니다. 실제 파일은 Git·Docker 빌드에서 제외됩니다. `enforce: true`는 유지합니다. [공식 Basic Auth 설정](https://ngrok.com/docs/gateway/traffic-policy/actions/basic-auth).
3. ngrok 대시보드에서 계정에 할당된 개발 도메인을 확인하고, **기존 `.env`**의 다음 두 설정을 변경합니다. 아래 주소는 예시이므로 실제 할당 주소로 바꿉니다. 새 `local.env` 파일은 만들지 않습니다.

   ```dotenv
   APP_ORIGIN=https://your-assigned-name.ngrok-free.app
   COOKIE_SECURE=true
   ```

4. 앱을 실행하고, ngrok를 별도 터미널에서 시작합니다. 명령은 `compose.yaml`이 있는 폴더에서 실행합니다.

   ```sh
   docker compose up -d
   ngrok http 8000 --traffic-policy-file ngrok.local.yml
   ```

   `8000`은 기본 `APP_PORT`입니다. 포트를 바꿨다면 같은 값으로 맞춥니다. ngrok의 `Forwarding` HTTPS 주소와 `APP_ORIGIN`이 같아야 합니다. 다르면 `.env`를 실제 주소로 맞추고 `docker compose up -d --no-deps app`으로 반영합니다. `--host-header=rewrite`는 사용하지 않습니다.

   앱을 시작하거나 재시작한 뒤에는 `docker compose ps`에서 `app`이 **healthy**가 될 때까지 기다립니다. 모델 준비에 몇 분 걸릴 수 있으며, 준비 중 접속하면 ngrok 오류가 나타날 수 있습니다. 정상 상태가 된 뒤 같은 주소를 새로고침합니다.

5. 공유 전에 새 브라우저 창에서 비밀번호 없이 접근이 거절되는지, 올바른 아이디·비밀번호로 닉네임 설정·단어 입력·채팅·새로고침이 되는지 확인합니다. 친구에게는 **HTTPS 링크와 공유용 아이디·비밀번호**만 전달합니다. ngrok 인증 토큰·DB 비밀번호는 전달하지 않습니다.
6. 공유 종료는 ngrok 터미널에서 `Ctrl+C`입니다. 다시 localhost로만 개발하려면 `.env`를 `APP_ORIGIN=`·`COOKIE_SECURE=false`로 되돌리고 `docker compose up -d --no-deps app`을 실행합니다. 게임을 완전히 멈추려면 `docker compose stop`을 사용합니다.

로컬 주소와 공유 도메인은 브라우저 쿠키가 별개라 같은 브라우저에서도 다른 사용자로 보일 수 있습니다. ngrok의 비밀번호는 링크 입장용이며 게임 닉네임과는 다릅니다. 방화벽의 DB 포트를 열거나 공유기의 포트 전달을 추가할 필요는 없습니다.

**2026-09-26 공식 안내 확인:** 무료 요금제는 월 HTTP 요청 20,000회·외부 전송 1GB 제한과 첫 방문 안내 화면이 있습니다. 랭킹·상태 자동 조회도 요청을 사용하므로 사용량은 ngrok 대시보드에서 확인합니다. 비용이나 한도가 바뀔 수 있어 사용 시 [공식 제한](https://ngrok.com/docs/pricing-limits/free-plan-limits)을 다시 확인합니다. 외부 인증 후 화면 접속은 위의 10월 4일 사용자 확인과 구분하며, 친구 기기에서의 실제 SSE 채팅은 별도로 확인합니다.

## 파일과 데이터 위치

| 파일·저장 공간 | 역할 |
|---|---|
| `Dockerfile`, `compose.yaml` | 화면과 서버 빌드, 앱·DB 실행, 상태 확인·로그 크기 제한 |
| `.env.example` | 설정 항목. 실제 비밀값은 각 기기의 `.env`에 보관 |
| `backend/migrations/` | DB 변경 이력. 적용한 SQL은 수정하지 않고 새 파일 추가 |
| `scripts/db.ps1`, `scripts/db.sh` | 논리 백업과 새 DB 복원 |
| `scripts/check_release.mjs` | 별도 DB의 실제 모델·재시작·논리 복원 검사 |
| `.github/workflows/check.yml` | GitHub 빌드·규칙 검사. 자동 배포·이미지 업로드 없음 |
| Docker `model_data`, `postgres_data` 볼륨 | 읽기 전용 모델, 사용자·게임·채팅 DB. 이미지와 Git에서 분리 |
| `backups/`, `test-results/` | 실제 백업과 검사 결과. Git과 이미지에서 제외 |

Windows/Mac 최초 실행·모델 준비·DB 이전 명령은 [README](../README.md)를 따릅니다. DB 데이터 폴더나 실행 중인 볼륨을 복사하지 않고 `pg_dump`와 `pg_restore`를 사용합니다.

## 평소 확인

```sh
docker compose ps
docker compose logs --tail=60 app
docker compose logs --tail=60 db
```

`/api/health`는 DB와 오늘 문제의 모델 지문이 정상일 때 HTTP 200, 모델 미준비 또는 DB 확인 실패 때 HTTP 503을 반환합니다. Docker도 준비 실패를 감지합니다. 상태 조회만으로 사용자나 문제를 만들지 않습니다. 상태 확인이 실패했다고 Docker의 `restart` 정책이 자동으로 앱을 재시작하는 것은 아니므로 원인을 확인합니다.

컨테이너별 로그는 10MB씩 최대 3개로 회전합니다. 사용자 메시지의 보관 기간과는 별개입니다. 로그에 쿠키·요청 본문·DB 비밀번호를 추가하지 않습니다. `docker compose config`는 실제 비밀값을 포함할 수 있어 문법 확인에는 `docker compose config --quiet`를 사용합니다.

## 기록을 보존하는 코드 업데이트

모델을 바꿀 때는 이 절차만으로 처리하지 않고 [모델 전환 절차](MODEL.md#기존-기록과-모델-전환)를 함께 따릅니다. 아래는 모델·기존 SQL을 유지하는 코드 업데이트입니다. 명령은 프로젝트 루트에서 실행합니다.

1. `docker compose images -q app`으로 현재 이미지 ID를 확인합니다. 다음 명령의 `현재이미지ID`를 바꾸고, 업데이트마다 중복되지 않는 태그를 붙입니다.

   ```sh
   docker tag 현재이미지ID ganmantle-v1-app:before-update-YYYYMMDD-HHMM
   ```

2. Windows는 `powershell -ExecutionPolicy Bypass -File scripts/db.ps1 backup`, Mac은 `sh scripts/db.sh backup`으로 논리 백업합니다. 백업 완료와 파일 크기를 확인합니다. 실제 운영에서는 업데이트 중 쓰기가 발생할 수 있으므로 필요하면 `docker compose stop app`으로 앱을 멈춘 뒤 최종 백업합니다. DB는 계속 실행합니다.

3. 같은 작업 폴더에 새 소스를 준비하되 `.env`와 모델·DB 볼륨을 보존합니다. `docker compose build app`으로 새 이미지를 만듭니다. `.env`의 `APP_IMAGE` 기본값은 `ganmantle-v1-app:local`입니다. 이전 이미지 보존 태그를 빌드 대상 이름으로 사용하지 않습니다.

4. 백엔드 자동 검사를 실행합니다. 실제 DB의 임시 스키마만 만들고 정리하며 사용자 기록은 검사에 사용하지 않습니다.

   ```sh
   docker compose run --rm --no-deps app sh -c 'TEST_DATABASE_URL="$DATABASE_URL" pytest -q -p no:cacheprovider backend/tests'
   ```

5. `docker compose up -d --no-deps --no-build app`으로 앱을 바꾸고 `docker compose ps`에서 healthy를 확인합니다. DB 환경변수를 바꾼 작업이라면 앱만 바꾸지 말고 `docker compose up -d --no-build`로 DB의 환경도 함께 반영해야 합니다. 앱 교체 중에는 잠깐 연결이 끊깁니다.

6. `node scripts/check_release.mjs`를 실행합니다(Node 24 이상). 현재 앱 이미지와 읽기 전용 모델을 재사용하며 별도 DB·localhost 임시 포트에서 검사합니다. 닉네임·게임·중복·채팅, 재시작 후 같은 쿠키, 논리 백업→새 DB 복원과 모든 테이블·sequence의 일치를 확인합니다. 결과는 `test-results/release-checks.json`입니다. 기존 DB에는 검사 기록을 만들지 않습니다.

7. 사용하던 브라우저에서 새로고침해 날짜·추측 목록·랭킹·채팅이 돌아오는지 확인합니다. 오래된 이미지와 업데이트 전 백업은 운영자가 복구 기간을 정하기 전까지 보존합니다.

이 절차는 [Docker의 단일 서버 Compose 업데이트 방식](https://docs.docker.com/compose/how-tos/production/)을 사용합니다. 기존 서비스의 모델이 준비되어 있어야 실제 모델 검사를 실행할 수 있습니다.

## 코드 되돌리기와 DB 복구

**기존 DB 구조와 이전 코드가 호환되는 경우:** 실제 `.env`의 `APP_IMAGE`를 앞에서 보존한 이미지 태그로 바꾸고 다음 명령을 실행합니다.

```sh
docker compose up -d --no-deps --no-build app
docker compose ps
```

`--no-build`가 있어야 이전 이미지 이름에 새 코드를 다시 빌드하지 않습니다. 되돌린 뒤 다음 업데이트를 시작할 때는 `APP_IMAGE`를 다시 새 빌드용 태그로 바꿉니다.

**새 SQL로 이전 코드가 동작하지 않는 경우:** 이미지 변경만으로 DB를 되돌릴 수 없습니다. 앱 쓰기를 중지하고 현재 DB도 별도 백업합니다. 이전 백업을 `ganmantle_restore_날짜` 같은 **새 DB**로 복원하고 기록·변경 이력을 확인한 뒤 `.env`의 `POSTGRES_DB`와 `APP_IMAGE`를 함께 바꿉니다. 기존 DB에 덮어쓰지 않습니다. 과거 백업으로 돌아가면 백업 이후 기록이 빠질 수 있으므로 전환 전에 비교·복구해야 합니다.

복원 명령은 README의 Windows/Mac 절차를 사용합니다. DB를 전환한 뒤에는 `docker compose up -d --no-build`로 앱과 DB 환경을 갱신합니다. 소스 업데이트용으로 `docker compose down -v`, 적용된 SQL 삭제, 볼륨 복사를 사용하지 않습니다. 현재 DB 구조는 001~003을 유지합니다.

## GitHub 자동 검사

`compose.yaml`과 `.github/`가 있는 `ganmantle-v1` 폴더를 저장소 루트로 사용합니다. 빈 원격 저장소에 현재 구현을 처음 등록했으므로 `main` 하나로 관리합니다. 최초 코드 커밋의 원격 자동 검사 성공을 확인했습니다. `.github/workflows/check.yml`은 push·PR·수동 실행의 자동 검사이며 배포는 하지 않습니다. 최신 반영 범위는 [10월 4일 변경 기록](../CHANGELOG/2026-10/04-004-github-update.md), 각 커밋의 원격 검사 결과는 [GitHub Actions](https://github.com/gaeun011019/ganmantle/actions)를 확인합니다.

별도 Ubuntu runner에서 임시 설정을 만들고 잠금 파일 설치·TypeScript/Vite 빌드·PostgreSQL 규칙 검사·입력 사전을 검사합니다. 이 경로는 모델을 다운로드하지 않고 기존 테스트의 합성 벡터·규칙 모형을 사용합니다. 실제 모델·재시작·복원은 위의 로컬 검사와 구분합니다. checkout은 공식 v7.0.1의 전체 커밋 SHA에 고정했고 저장소 읽기 권한만 부여했습니다. [공식 릴리스 커밋](https://github.com/actions/checkout/commit/3d3c42e5aac5ba805825da76410c181273ba90b1), [GitHub 고정 버전 안내](https://docs.github.com/en/actions/reference/security/secure-use#using-third-party-actions).

## HTTPS로 운영할 때

현재 앱은 `127.0.0.1:8000`에만 열리고 PostgreSQL은 외부 포트를 열지 않습니다. 호스트의 Caddy/Nginx 또는 호스팅 HTTPS 프록시가 외부 요청을 로컬 앱에 전달하게 합니다. 별도 AI·채팅 서버는 추가하지 않습니다.

운영 `.env`의 비밀값 이외 설정 예시:

```dotenv
APP_ORIGIN=https://game.example.com
COOKIE_SECURE=true
APP_PORT=8000
```

예시 도메인을 실제 주소로 바꾸며 경로는 붙이지 않습니다. 로컬 HTTP는 `APP_ORIGIN=`·`COOKIE_SECURE=false`를 유지합니다. 프록시는 Host를 보존하고 임의 클라이언트의 전달 헤더를 그대로 신뢰하지 않도록 설정합니다.

호스트 Caddy의 최소 설정 예시:

```caddyfile
game.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

DNS와 80·443 포트를 연결한 뒤 Caddy의 인증서 발급·갱신과 HTTP→HTTPS 처리를 확인합니다. Caddy는 `text/event-stream`을 즉시 전달합니다. 다른 프록시는 SSE 응답 버퍼링을 끄고 연결 시간 제한을 확인해야 합니다. 이 구성은 이번 작업에서 설치하거나 공개 연결하지 않았습니다. [Caddy HTTPS](https://caddyserver.com/docs/automatic-https), [스트리밍 전달](https://caddyserver.com/docs/caddyfile/directives/reverse_proxy).

현재 채팅 알림은 프로세스 안에서 관리하므로 FastAPI worker는 **1개**로 유지합니다. 여러 worker·여러 서버로 늘리려면 알림 전달과 모델 메모리 공유를 먼저 검토합니다.

## 모델 자원과 배포 비용

현재 모델 원본 7,243,669,409바이트, 비교 자료 59,382,895바이트입니다. 앞선 Linux/amd64 실측은 로드 11.792초, RSS 350.59→360.23MiB, 입력 쌍 계산 중앙값 0.351ms였습니다. OS 파일 캐시를 비우지 않은 **독립 벤치마크**이며 HTTP 지연·앱+DB 최대 메모리·동접 성능이 아닙니다. 메모리 매핑으로 사용하는 파일 페이지도 OS 캐시를 차지합니다. [측정 조건](MODEL.md).

소규모 검증 시작점은 2vCPU·RAM 4GB·SSD 40GB 이상으로 가정합니다. 실제 요구 사양을 보증하는 수치가 아니며 모델 준비본·이전 이미지·DB·백업·빌드 캐시의 여유를 고려합니다. 공개 전에 해당 서버에서 처음 실행과 다양한 단어·SSE 동시 연결의 메모리·CPU·응답 지연을 측정해야 합니다.

친구들과 잠깐 공유하는 현재 방식에는 유료 서버가 필요하지 않습니다. 나중에 상시 운영으로 바꾸면 모델·DB·백업 공간과 실제 부하를 측정한 뒤 서버를 선택합니다. 과거 가격 비교는 [9월 21일 변경 기록](../CHANGELOG/2026-09/21-003-deployment-ready.md)에 남아 있으며 구매 시점의 견적을 다시 확인합니다.

## 공개 전 남은 확인

- 선택한 서버에서 실제 모델·DB·동시 입력·SSE 부하 측정. 단일 서버 장애 시 앱과 DB가 함께 중단됨을 고려합니다.
- 실제 도메인의 HTTPS·보안 쿠키·출처 제한·채팅 재연결을 확인합니다. TestClient의 HTTPS URL 검사는 인증서·프록시 검사가 아닙니다.
- 일별 논리 백업·서버 밖 비공개 복사·실패 알림을 예약하고 정기 복원을 연습합니다. 현재는 명령 제공이며 자동 예약은 미설정입니다. 보관 기간은 운영자의 복구 목표에 맞춰 결정합니다.
- 채팅 보관·신고·삭제 정책을 정합니다. 현재 기록은 계속 저장하며 임의의 자동 삭제는 추가하지 않았습니다. 공개 서비스의 요청·연결 제한도 부하 측정에 맞춰 결정해야 합니다.
- 실제 Mac/Apple Silicon·Safari·모바일 기기를 확인합니다. 이번 Windows Docker arm64 빌드는 기반 이미지 확인 후 첫 `/bin/sh`에서 `exec format error`로 중단됐습니다. 의존성 설치 전 실패이므로 라이브러리 호환 실패로 단정하지 않습니다. 이 환경의 에뮬레이션 설정은 바꾸지 않았습니다.

Mac에서는 README대로 같은 소스·잠금 파일로 네이티브 Linux 이미지를 빌드하고 모델 준비 후 `node scripts/check_release.mjs`까지 실행해야 합니다. 기존 arm64 의존성 다운로드·해시 확인과 실제 모델 실행은 구분합니다. Windows 설치 산출물이나 PostgreSQL 데이터 폴더를 복사하지 않습니다.
