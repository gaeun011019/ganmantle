# 맥에서 플레이하고 관리하기

맥에서 **플레이만** 할 때는 지금 쓰는 ngrok HTTPS 링크를 최신 Safari나 Chrome에서 열고 공유용 아이디·비밀번호를 입력하면 됩니다. 이 경우 서버는 Windows에서 계속 실행합니다.

아래는 **서버도 맥에서 실행하고 친구에게 공유하는 방법**입니다. 현재 Windows 서버를 자동으로 종료하거나 데이터를 옮기지는 않습니다. 두 컴퓨터의 DB는 서로 동기화되지 않으므로 실제 공유에 사용할 서버는 하나로 정합니다.

## 1. 현재 소스를 맥으로 옮기기

맥 터미널에서 [GitHub 저장소](https://github.com/gaeun011019/ganmantle)의 최신 소스를 내려받습니다. 아래 명령은 새 `ganmantle-v1` 폴더를 만듭니다. 이미 같은 이름의 폴더가 있으면 다른 위치에서 실행합니다.

```sh
git clone https://github.com/gaeun011019/ganmantle.git ganmantle-v1
cd ganmantle-v1
```

Git을 사용하지 않으면 저장소의 **Code → Download ZIP**으로 내려받아 압축을 풉니다. 이 경우 폴더 이름은 보통 `ganmantle-main`입니다. 앞서 Windows에서 만든 `ganmantle-mac-source-날짜.zip`도 사용할 수 있지만, 만든 이후의 변경은 GitHub에서 확인합니다.

GitHub와 전달용 ZIP에는 코드·문서·설정 예시가 들어 있습니다. 실제 `.env`, `ngrok.local.yml`, ngrok 토큰, DB 기록·백업, 모델, `node_modules`는 포함하지 않습니다. 기존 기록을 옮기는 방법은 아래 4단계에 있습니다. 이미 맥에 예전 프로젝트가 있다면 새 폴더로 받아 확인하거나, 기존 Git 작업 폴더에서 `git pull --ff-only`로 업데이트합니다. 수정 충돌이 안내되면 로컬 수정과 설정을 지우지 말고 먼저 확인합니다.

ZIP으로 내려받았다면 터미널에서 `cd `를 입력한 뒤 Finder의 압축을 푼 프로젝트 폴더를 터미널로 끌어다 놓고 Enter를 누릅니다. 이후 명령은 `compose.yaml`이 있는 이 폴더에서 실행합니다.

## 2. Docker 설치와 최초 준비

1. [Docker Desktop 공식 Mac 설치 페이지](https://docs.docker.com/desktop/setup/install/mac-install/)에서 칩에 맞는 설치 파일을 받습니다. Apple 메뉴 → 이 Mac에 관하여에서 Apple 칩이면 **Apple silicon**, Intel이면 **Intel chip**을 선택합니다.
2. Docker를 응용 프로그램에 설치하고 실행합니다. 터미널에서 다음 명령이 성공하는지 확인합니다.

   ```sh
   docker info
   docker compose version
   ```

3. 다음 명령으로 설정·앱 이미지·모델을 준비하고 서버를 시작합니다.

   ```sh
   sh scripts/manage.sh setup
   ```

Python이나 Node를 맥에 따로 설치하지 않아도 됩니다. Docker 안에서 필요한 도구를 실행하며, 맥의 CPU에 맞게 이미지를 빌드합니다. 처음에는 약 **7.24GB 모델 다운로드**와 순위 자료 준비가 있어 오래 걸릴 수 있습니다. 모델·Docker 이미지·백업을 고려해 디스크 여유를 확보합니다. 중간에 실패하면 원인 해결 후 같은 명령을 다시 실행할 수 있습니다.

기존 `.env`는 덮어쓰지 않습니다. 처음 생성한 `.env`는 로컬용 `APP_ORIGIN=`와 `COOKIE_SECURE=false`를 사용합니다. 맥에 같은 이름의 Docker 볼륨이 이미 있다면 기존 DB·모델을 사용하므로, 새 소스 폴더를 만들었다고 빈 DB가 되는 것은 아닙니다.

설정이나 모델이 잘못되면 명령이 실패한 단계에서 멈춥니다. 서버 시작은 정상 준비 상태까지 최대 10분 기다립니다. 시간이 초과되더라도 컨테이너·볼륨을 삭제하지 않으므로 아래 명령으로 상태와 오류를 확인합니다.

```sh
sh scripts/manage.sh status
sh scripts/manage.sh logs app
```

## 3. 맥에서 게임 열기

`app`과 `db`가 정상 상태이면 [http://localhost:8000](http://localhost:8000)을 엽니다. `.env`의 `APP_PORT`를 바꿨다면 그 포트로 접속합니다.

Safari에서 닉네임 설정 → 단어 입력 → 랭킹 → 채팅 → 새로고침을 확인합니다. 다른 브라우저나 새 기기에서는 쿠키가 별개이므로 새 사용자로 인식됩니다. HTTPS 공유 설정을 적용한 뒤에는 아래 5단계의 공유 주소로 플레이합니다.

## 4. Windows의 기존 기록 옮기기

새 기록으로 시작할 때는 이 단계를 건너뜁니다. 기존 기록을 유지하려면 **전환하는 시점의 최종 백업**을 사용합니다. Windows와 맥에서 따로 진행된 기록을 자동 병합하는 기능은 없습니다.

Windows에서 ngrok 터미널의 `Ctrl+C`로 공유를 끝내고, 프로젝트 폴더의 PowerShell에서 실행합니다. 앱을 멈춰 백업 이후 새 기록이 생기지 않게 하며 DB는 켜 둡니다.

```powershell
docker compose stop app
powershell -ExecutionPolicy Bypass -File scripts/db.ps1 backup
```

출력된 `backups/ganmantle-날짜.dump` 파일을 맥의 프로젝트 안 `backups/` 폴더로 비공개 복사합니다. PostgreSQL 데이터 폴더나 Docker 볼륨 자체를 복사하지 않습니다.

맥에서 먼저 2단계 준비를 마친 후, 실제 파일 이름으로 바꾸어 실행합니다.

```sh
sh scripts/manage.sh restore backups/ganmantle-날짜.dump ganmantle_restore_mac
```

기존 DB는 유지하고 `ganmantle_restore_mac`이라는 **새 DB**에 복원합니다. 이 이름의 DB가 이미 있으면 `ganmantle_restore_mac_2`처럼 다른 이름을 사용합니다. DB 이름은 `ganmantle_restore_`로 시작하는 영문 소문자·숫자·밑줄이며 63자 이내입니다. 복원 결과의 기록 수·마이그레이션 목록을 확인한 다음 맥의 `.env`에서 다음 항목만 바꿉니다.

```dotenv
POSTGRES_DB=ganmantle_restore_mac
```

```sh
sh scripts/manage.sh start
```

DB 백업에는 게임·랭킹·채팅·사용자 기록이 들어 있지만 Windows 브라우저 쿠키는 맥 브라우저로 자동 이전되지 않습니다. 같은 닉네임 입력만으로 예전 사용자의 기록에 로그인하는 구조도 아닙니다. 친구들이 기존 브라우저·같은 공유 도메인으로 접속하는 경우에는 해당 쿠키와 복원한 DB가 함께 필요합니다.

## 5. 맥에서 ngrok 공유하기

1. [ngrok 공식 Mac 설치 안내](https://ngrok.com/download/mac-os)에 따라 설치합니다. 기존과 같은 ngrok 계정으로 로그인하고, 대시보드의 본인 토큰을 맥 터미널에서 설정합니다.

   ```sh
   ngrok config add-authtoken 본인_토큰
   ```

2. `ngrok.local.yml`이 없으면 예시를 복사하고 편집합니다. 기존 파일이 있으면 그대로 보존합니다.

   ```sh
   if [ ! -f ngrok.local.yml ]; then
     cp ngrok.example.yml ngrok.local.yml
   fi
   ```

   `CHANGE_ME`와 `REPLACE_WITH_A_PRIVATE_PASSWORD`를 공유용 아이디·비밀번호로 바꿉니다. Windows에서 쓰던 값을 직접 설정하거나 기존 `ngrok.local.yml`만 비공개로 옮겨도 됩니다. `enforce: true`는 유지합니다.

3. 맥의 `.env`를 편집합니다. 예시 주소는 **ngrok 계정에 할당된 실제 HTTPS 주소**로 바꾸고, 뒤에 `/`나 경로는 붙이지 않습니다.

   ```dotenv
   APP_ORIGIN=https://your-assigned-name.ngrok-free.dev
   COOKIE_SECURE=true
   ```

4. 설정을 반영하고 정상 상태가 된 뒤 ngrok를 실행합니다. 아래 `--url`에도 `.env`와 **같은 실제 주소**를 넣습니다.

   ```sh
   sh scripts/manage.sh start
   ngrok http 8000 --url https://your-assigned-name.ngrok-free.dev --traffic-policy-file ngrok.local.yml
   ```

   `APP_PORT`를 바꿨다면 `8000`도 맞춥니다. Windows에서 같은 주소의 ngrok가 아직 실행 중이면 먼저 그 터미널에서 `Ctrl+C`로 종료합니다. [같은 주소가 이미 사용 중일 때의 ngrok 안내](https://ngrok.com/docs/errors/err_ngrok_334).

5. HTTPS 주소로 로그인·단어 입력·채팅을 확인하고 친구들에게 주소와 공유용 아이디·비밀번호를 알려줍니다. 맥·Docker·ngrok를 켜 두고, 공유하는 동안 맥이 잠자기 상태가 되지 않도록 합니다.

다음에 공유할 때는 Docker를 켠 뒤 `sh scripts/manage.sh start`와 위의 `ngrok http ...`를 실행하면 됩니다. ngrok 종료는 그 터미널의 `Ctrl+C`, 게임 서버 종료는 다른 터미널에서 `sh scripts/manage.sh stop`입니다.

## 평소 관리 명령

| 작업 | 맥 터미널 명령 |
|---|---|
| 사용법 | `sh scripts/manage.sh help` |
| 처음 준비 또는 준비 재개 | `sh scripts/manage.sh setup` |
| 시작·`.env` 반영 | `sh scripts/manage.sh start` |
| 종료, DB·모델 보존 | `sh scripts/manage.sh stop` |
| 상태 | `sh scripts/manage.sh status` |
| 최근 앱 / DB 로그 | `sh scripts/manage.sh logs app` / `sh scripts/manage.sh logs db` |
| 백업 | `sh scripts/manage.sh backup` |
| 새 DB에 복원 | `sh scripts/manage.sh restore backups/파일.dump ganmantle_restore_mac_2` |
| 코드 수정 후 재빌드·적용 | `sh scripts/manage.sh update` |

업데이트 전에 백업하고 [이전 이미지 보존·복구 안내](DEPLOYMENT.md#기록을-보존하는-코드-업데이트)를 따릅니다. `update`는 현재 폴더의 코드를 빌드하며 Git에서 자동으로 내려받지 않습니다. 종료에 `docker compose down -v`를 사용하면 DB와 모델까지 삭제되므로 사용하지 않습니다.

화면 코드를 맥에서 직접 개발하려면 호스트 Node를 추가로 설치하고 `frontend/`에서 `npm ci` → `npm run dev`를 실행합니다. Windows의 `node_modules`는 복사하지 않습니다. 빠른 개발 화면과 API 프록시 설명은 [README](../README.md)를 따릅니다.

## 확인 범위

이번 준비 작업은 Windows에서 했습니다. 관리 명령의 셸 문법·모의 실행과 관련 코드 검사를 수행한 결과는 [변경 기록](../CHANGELOG/2026-10/04-003-mac-management.md)에 남깁니다. 실제 Mac/Apple Silicon의 모델 실행·Safari 입력·ngrok 연결은 맥에서 위 순서대로 확인해야 합니다.
