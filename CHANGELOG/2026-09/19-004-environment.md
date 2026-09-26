# 2026-09-19 — Docker·설정 분리·DB 백업과 복원

- 기록 ID: 2026-09-19-004
- 분야: 환경
- 유형: 초기 구현 기록
- 근거: 현재 소스와 기존 [검증 기록](../../docs/VALIDATION.md). 이번 CHANGELOG 작업에서 실행 환경을 바꾸지는 않았습니다.

## 무엇이 추가되었나요?

Windows와 Mac에서 같은 코드로 다시 빌드할 수 있게 Linux 컨테이너를 기준으로 구성했습니다. 앱 하나와 PostgreSQL 하나를 사용하고, 소스·설정·모델·DB·백업을 구분합니다.

## 어디에 구현했나요?

| 파일 | 코드 위치 | 추가·변경한 처리 |
|---|---|---|
| [Dockerfile](../../Dockerfile) | `backend-deps`, `frontend`, 최종 단계 | 고정 이미지·의존성, React 빌드, FastAPI에서 화면 제공, 일반 사용자 실행 |
| [compose.yaml](../../compose.yaml) | `services.app`, `services.db`, `volumes.postgres_data` | 로컬 앱과 독립 DB, 읽기 전용 모델 마운트, 상태 검사 |
| [.env.example](../../.env.example) | `POSTGRES_*`, `APP_PORT`, `MODEL_DIR`, `COOKIE_SECURE` | 비밀값 없는 설정 항목. 실제 값은 로컬 `.env`에서 별도 관리 |
| [setup_env.py](../../scripts/setup_env.py) | 기존 파일 확인, `secrets.token_hex()` | 최초 설정 파일 생성, 기존 `.env` 보존, 비밀번호 출력 방지 |
| [.gitignore](../../.gitignore), [.dockerignore](../../.dockerignore) | 설정·모델·DB·설치 산출물 제외 규칙 | `.env`, 모델·백업·캐시 등 제외. migration SQL은 보존 |
| [.gitattributes](../../.gitattributes) | `eol=lf` | Windows/Mac의 줄바꿈 통일 |
| [db.ps1](../../scripts/db.ps1) | `backup` / `restore` 분기, `Check-Docker` | Windows 논리 백업·새 DB 복원·기록 확인 |
| [db.sh](../../scripts/db.sh) | `backup` / `restore` 분기 | Mac/Linux에서 같은 논리 백업·복원 절차 |
| `scripts/smoke_test.py` | `before` / `after` | 실제 모델 입력 후 앱 재시작·복구·정답 확인 |
| [package.json](../../frontend/package.json), [package-lock.json](../../frontend/package-lock.json) | `vite`와 잠금 파일 | 초기 설치 검사에서 Vite 7.1.12를 수정 버전 7.3.6으로 변경 |
| [README.md](../../README.md), [VALIDATION.md](../../docs/VALIDATION.md) | 실행·이전·검증 안내 | 운영 방법, 파일 역할, 통과/미검증 구분 |

## 핵심 코드와 초기 수정 사항

`compose.yaml`에서 모델 폴더는 읽기 전용으로 연결합니다.

```yaml
volumes:
  - ${MODEL_DIR:-./models}:/models:ro
```

앱의 `MODEL_DIR`는 컨테이너 안의 `/models/multilingual-e5-small`입니다. 호스트에서 연결할 폴더와 모델 파일이 실제 들어 있는 하위 폴더를 구분했습니다.

백업은 `pg_dump --format=custom --file=...`로 컨테이너 안에 만든 뒤 `docker compose cp`로 가져옵니다. 바이너리를 PowerShell의 문자 출력 리다이렉션으로 저장하지 않습니다. 복원은 `createdb`로 **새 DB**를 만든 후 `pg_restore`합니다.

초기 검증 중 `db.ps1`의 복원 후 조회에서 중첩 따옴표가 잘못 해석되는 문제가 있었습니다. SQL을 표준 입력으로 보내도록 수정했습니다. 현재 코드의 일부입니다.

```powershell
$query | docker compose exec -T db sh -c 'psql -U "$POSTGRES_USER" -d "$1" -v ON_ERROR_STOP=1' sh $Database
```

여기서 `$query`는 테이블 개수와 migration을 확인하는 SQL이며 비밀번호를 출력하지 않습니다.

## 어떻게 확인했나요?

기존 2026-09-19 검사 결과입니다. 이번에는 기록 내용과 소스 위치만 확인했습니다.

- Linux/amd64의 앱 빌드, 모델 실행, 실제 재시작 복구 통과.
- 수정된 Windows 도구로 논리 백업과 새 DB 복원 통과.
- Vite 변경 뒤 npm 검사 0건.
- Python/Node/PostgreSQL 이미지의 amd64·arm64 제공 확인. Python arm64 의존성 다운로드·해시 검사 통과.
- arm64 실행은 현재 Docker의 `exec format error`로 미검증. 실제 Mac 미검증. Mac용 스크립트는 `sh -n` 구문 검사만 통과.

## 영향과 남은 일

기존 프로젝트나 DB를 덮어쓰지 않고 `ganmantle-v1`에서 분리했습니다. GitHub 업로드와 공개 배포는 하지 않았습니다. 실제 Mac 실행·복원 검사와 공개 운영 준비는 후속 작업입니다.

> 후속 정리(2026-09-19): `scripts/smoke_test.py`는 [012 정리 기록](19-012-cleanup.md)에 따라 삭제했습니다. 이 문서의 실행 사실은 당시 기록으로 보존하며, 현재 실제 모델·DB 통합 검사 도구는 `scripts/smoke_ranking.py`입니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
