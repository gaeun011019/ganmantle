# 2026-10-04 — Mac 실행·관리 도구와 Safari 요청 호환 처리

- 기록 ID: 2026-10-04-003
- 분야: 환경 / 화면 / 문서
- 유형: 추가 / 수정
- 구현 상태: 도구·안내 구현 완료, 실제 Mac 확인 남음
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

맥에서도 간맨틀을 실행·종료·백업하고 ngrok로 공유할 수 있도록 관리 명령과 단계별 안내를 추가했습니다. 현재 Windows 서버는 유지하고, 최신 소스를 맥으로 옮길 ZIP을 준비합니다. Safari 일부 버전에서 지원되지 않는 요청 취소 API도 교체했습니다.

| 변경 전 | 변경 후 |
|---|---|
| 첫 실행 때 Docker 설정·빌드·모델 준비 명령을 각각 입력 | `sh scripts/manage.sh setup`으로 순서대로 실행 |
| 시작·종료·로그·백업 명령이 문서에 분산 | 한 스크립트에서 명령별로 실행, 도움말 제공 |
| Windows → Mac 소스·DB·공유 주소 이전 순서가 분산 | [Mac 안내](../../docs/MAC.md)에 준비·플레이·최종 백업·복원·ngrok 전환 순서 정리 |
| 공통 요청이 `AbortSignal.any()`와 `timeout()`에 의존 | `AbortController`·타이머·취소 이벤트 사용, 완료 후 정리 |

## 어디를 수정했나요?

| 파일 | 위치 | 변경 내용 |
|---|---|---|
| [scripts/manage.sh](../../scripts/manage.sh) | `usage`, 인자 검사, `run_docker`, `start_app`, 명령 분기 | POSIX sh 기반 관리 도구. Docker 상태 확인, 기존 `.env` 보존, 명시적 인자 검사, 실패 시 후속 작업 중단 |
| [frontend/src/api.ts](../../frontend/src/api.ts) | `request()`의 취소·제한 시간과 `finally` | 정적 AbortSignal API 의존성 제거. 게임 45초·채팅 15초, 상위 화면의 취소, HTTP·JSON 오류 처리 유지 |
| [docs/MAC.md](../../docs/MAC.md) | 전체 | Mac 설치·소스 준비·모델 준비·플레이·관리·Windows DB 이전·ngrok 전환 안내 |
| [README](../../README.md), [공유 안내](../../docs/DEPLOYMENT.md) | Mac 안내 연결·파일 역할 | 맥에서 플레이만 하는 경우와 맥으로 서버를 옮기는 경우의 시작 위치 연결 |
| [월별 목록](README.md), [전체 목록](../README.md) | 최신 기록 | 이번 변경 연결 |

## 어떤 코드인가요?

관리 명령은 다음과 같습니다. `setup`은 기존 초기화·모델 준비 도구를 그대로 호출하며, `backup`과 `restore`는 기존 [db.sh](../../scripts/db.sh)에 위임합니다.

```sh
sh scripts/manage.sh setup
sh scripts/manage.sh start
sh scripts/manage.sh status
sh scripts/manage.sh logs app
sh scripts/manage.sh backup
sh scripts/manage.sh restore backups/파일.dump ganmantle_restore_mac
sh scripts/manage.sh update
sh scripts/manage.sh stop
```

시작·업데이트는 `docker compose up -d --wait --wait-timeout 600`으로 정상 상태를 기다립니다. 종료는 `docker compose stop`이며 볼륨을 지우지 않습니다. `update` 전에 백업·이전 이미지 보존이 필요하다는 안내를 연결했고, 소스 자동 다운로드·운영 DB 자동 전환은 하지 않습니다.

요청 코드 일부 발췌입니다. 호출한 화면의 취소 신호도 같은 컨트롤러에 전달하며, `finally`에서 타이머·리스너를 제거합니다.

```ts
const controller = new AbortController();
const timeout = setTimeout(
  () => controller.abort(new DOMException('Request timed out', 'TimeoutError')),
  timeoutMs,
);
```

`AbortSignal.any()`는 [Safari 17.4에서 추가된 기능](https://webkit.org/blog/15063/webkit-features-in-safari-17-4/)이므로 이 정적 메서드에 의존하지 않게 바꿨습니다. 전체 앱의 모든 구형 Safari 지원을 보증하는 변경은 아니며 최신 브라우저 사용과 실기 확인을 안내합니다.

## 어떻게 확인했나요?

| 확인 방법 | 결과 |
|---|---|
| `manage.sh`·`db.sh`의 셸 문법 및 LF 확인 | 통과. 호스트 Windows 경로에 의존하지 않고 공백 경로를 따옴표로 처리 |
| 관리 도구의 모의 Docker 실행 | **42개 통과**. 공백 경로·명령 전달·기존 설정 보존·실패 시 중단·잘못된 인자 23종 차단 포함. 실제 Docker 작업 없이 격리해 확인하고 검사 임시 파일 삭제 |
| 요청 코드의 모의 검증 | **13개 통과**. 정적 AbortSignal API 부재, GET/POST, 게임·채팅 제한 시간, 상위·사전 취소, 성공·오류 후 정리, JSON 수신 중 제한 시간 포함 |
| `npm.cmd run build` | TypeScript·Vite 빌드 통과 |
| Docker 고정 이미지의 원격 manifest 확인 | Python·Node·PostgreSQL 모두 `linux/amd64`·`linux/arm64` 포함 |
| 네이티브 Python 의존성의 ARM64 배포 파일 확인 | Python 3.12 호환 휠 SHA-256이 현재 잠금 파일에 있음 |
| Mac 안내·관리 도구 교차 검토 | 모델 볼륨·경로, 새 DB 복원 후 설정 전환, 브라우저 쿠키 설명 일치 |
| 현재 Windows 컨테이너 상태 | app·db 모두 healthy. 이번 작업에서 재시작하지 않음 |
| 수정 문서의 로컬 링크·공백 검사 | 로컬 링크 57개 정상, `git diff --check` 통과 |

ARM64 의존성 확인은 공식 PyPI의 [NumPy](https://pypi.org/pypi/numpy/2.2.6/json), [psutil](https://pypi.org/pypi/psutil/7.0.0/json), [psycopg-binary](https://pypi.org/pypi/psycopg-binary/3.2.9/json), [pydantic-core](https://pypi.org/pypi/pydantic-core/2.46.5/json) 배포 메타데이터를 사용했습니다. 실제 Mac에서의 설치·실행 검사와는 구분합니다. 이전 정리 작업의 백엔드 288개·UI 33개 검사는 [앞선 기록](04-002-cleanup-readability.md)의 결과이며 이번에 다시 실행했다고 표현하지 않습니다.

## 전달 파일과 데이터

프로젝트 바깥의 상위 폴더에 `ganmantle-mac-source-날짜.zip`을 만듭니다. Git이 추적하는 현재 작업 파일과 이번에 추가한 소스·문서를 모으므로, 아직 커밋하지 않은 수정도 포함합니다. 숨김 설정 예시와 마이그레이션도 포함하고, 실제 설정·인증 파일·DB·모델·설치 산출물은 제외합니다. 소스 ZIP 자체는 Git 저장소에 추가하지 않습니다.

소스 ZIP에는 사용자 기록이 없습니다. 기존 기록은 전환 직전에 Windows 앱을 멈춘 뒤 논리 백업하고, 맥의 새 DB로 복원하는 절차를 따릅니다. ngrok 계정 연결은 맥에서 별도로 하며, 같은 공유 주소를 동시에 양쪽에서 실행하지 않도록 안내합니다.

## 영향과 남은 일

- DB·모델·의존성 잠금·실제 환경변수·ngrok 인증 변경 없음. 현재 Windows 서비스 유지.
- 실제 Mac/Apple Silicon 모델 실행, Safari 입력·채팅, Mac ngrok 연결은 맥에서 확인해야 합니다.
- 실제 운영 기록의 백업·전송·복원은 아직 실행하지 않았습니다. 두 컴퓨터의 DB를 자동 동기화하지 않습니다.
- Safari 요청 호환 수정은 소스와 빌드에 반영했고 현재 Windows 컨테이너는 교체하지 않았습니다.
- Git 커밋·GitHub 업로드·Mac 원격 설치는 실행하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
