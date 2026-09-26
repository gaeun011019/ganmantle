# 2026-09-21 — 4단계 배포 준비와 기록 보존 검사

- 기록 ID: 2026-09-21-003
- 분야: 서버 / 환경 / 검사 / 문서
- 유형: 수정 / 추가
- 구현 상태: 로컬 구현·검증 완료. 실제 Mac/arm64·공개 환경 검증은 별도
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

명세 8장의 다음 미완료 단계인 **4단계 배포 준비**를 진행했습니다. 1~3단계 게임·전체 랭킹·채팅, fastText 점수, 9월 21일 간소화한 UI를 유지합니다. 공개 서버를 만들거나 GitHub에 업로드하지 않았습니다.

| 변경 전 | 변경 후 |
|---|---|
| 모델 미준비에도 상태 API가 HTTP 200을 반환해 Docker가 healthy로 판단 | 모델 미준비·오늘 모델 지문 불일치·DB 확인 실패는 HTTP 503 |
| DB 장애의 내부 오류가 상태 확인에 그대로 전파 | 짧은 오류 응답, 로그에는 DB 예외 타입만 기록 |
| HTTPS 출처 제한 코드가 있어도 Compose에서 `APP_ORIGIN`을 전달하지 못함 | 비밀값 없는 예시와 Compose에 전달 항목 추가 |
| 자동 이미지 이름·무제한 기본 로그 | `APP_IMAGE`로 버전 태그 선택, 컨테이너별 10MB×3개 로그 회전 |
| 개별 규칙 검사와 백업 명령만 제공 | 실제 모델 API로 재시작·논리 백업·새 DB 복원을 한 번에 검증하는 도구 추가 |
| GitHub 검사 파일 및 업데이트·코드 복구 안내 없음 | 배포 없는 CI 파일, 업데이트·되돌리기·HTTPS·배포 옵션/비용 문서 추가 |

## 어디를 수정했나요?

| 파일 | 코드 위치 | 역할과 변경 |
|---|---|---|
| [main.py](../../backend/app/main.py) | `health` | DB·모델 준비 실패 HTTP 503, 내부 오류 감춤. 상태 조회는 데이터 생성 안 함 |
| [test_operations.py](../../backend/tests/test_operations.py) | 상태 검사 4개·HTTPS 설정 1개 | 정상/모델 실패/DB 연결·쿼리 실패와 복구, Secure 쿠키·출처 제한 검증 |
| [compose.yaml](../../compose.yaml) | `app.image`, `environment`, `logging`, `stop_grace_period` | 이미지 태그, HTTPS origin 전달, 로그 제한, 종료 대기 |
| [.env.example](../../.env.example) | `APP_IMAGE`, `APP_ORIGIN` | 로컬 기본값·운영 설정 위치 설명. 실제 `.env`는 수정하지 않음 |
| [check_release.mjs](../../scripts/check_release.mjs) | 격리 확인·API 검사·DB 비교·정리 | 현재 이미지·읽기 전용 모델을 재사용하고 별도 DB에서 재시작/복원 검증 |
| [check.yml](../../.github/workflows/check.yml) | GitHub Actions `test` | 잠금 파일 빌드, PostgreSQL 규칙·로더·사전 검사. 업로드·배포 명령 없음 |
| [DEPLOYMENT.md](../../docs/DEPLOYMENT.md) | 운영 절차 전체 | 파일 역할, 백업·업데이트·이미지 복귀·DB 호환성·HTTPS·자원/비용과 한계 |
| [README.md](../../README.md), [GANMANTLE_SPEC.md](../../GANMANTLE_SPEC.md) | 현재 단계·최신 UI 기준·검사 명령 | 지난 검사와 이번 검사를 구분하고 제거한 날짜 배너를 다시 추가하지 않도록 명시 |
| [VALIDATION.md](../../docs/VALIDATION.md) | 4단계 검증 결과 | 실제 실행과 미검증 환경 구분 |
| [월별 목록](README.md), [전체 목록](../README.md) | 최신 기록 | 이번 변경과 다음 번호 연결 |

별도 앱 서비스·AI 서비스·Redis·새 DB 계층·새 migration은 추가하지 않았습니다. `.github/workflows`는 GitHub의 지정 위치이며 나머지 파일은 기존 `scripts`, `docs`, `backend/tests` 안에 둡니다.

## 어떤 코드인가요?

상태 API 변경 전에는 준비 실패도 일반 dict를 반환해 HTTP 200이었습니다.

```python
return {"status": "ok" if model["ready"] else "model_unavailable",
        "database": True, "model": model}
```

변경 후 일부 발췌:

```python
if not model["ready"]:
    return JSONResponse(status_code=503, content={
        "status": "model_unavailable", "database": True,
        "model": {**model, "error": "유사도 모델을 사용할 준비가 되지 않았어요."},
    })
```

Docker의 기존 HTTP 상태 점검이 실제 게임 준비 실패를 감지합니다. DB 오류도 503으로 반환하며 연결 문자열·원본 SQL 예외는 외부에 내보내지 않습니다.

재시작 검사는 생성한 `ganmantle-check-...` 프로젝트의 DB만 씁니다. 실행·삭제 전에 실제 Compose 설정의 프로젝트 이름, DB 볼륨, 읽기 전용 external 모델, localhost 임시 포트를 확인합니다. 같은 쿠키로 게임·채팅을 읽고 `pg_dump` custom 파일을 새 DB에 복원하여 모든 테이블과 sequence를 대조합니다. 종료 때 검사 DB·컨테이너·임시 비밀 설정만 삭제합니다. 원래 앱 DB와 모델은 유지합니다.

## 어떻게 확인했나요?

- `docker compose config --quiet`: 통과. 실제 비밀값을 출력하지 않았습니다.
- 실제 DB 논리 백업: Windows `scripts/db.ps1 backup` 성공. 백업은 Git/Docker 제외 경로에 보존했습니다.
- 이전 앱 이미지는 로컬 `ganmantle-v1-app:before-stage4-20260921` 태그로 보존했습니다.
- `docker compose build app`: 새 이미지 빌드 성공. 잠금 파일 설치·화면 빌드 단계는 변경 없는 캐시를 재사용했습니다.
- `node --check scripts/check_release.mjs`: 통과.
- `docker compose exec -T app python scripts/prepare_dictionary.py --check`: 원본 비교 사전 49,485개·514,758바이트 검증 통과. 미등록 입력을 거절하도록 규칙을 바꾼 것이 아닙니다.
- 전체 백엔드 `pytest -q -p no:cacheprovider backend/tests`: **251개 통과, 121.32초**. 새 운영 검사 5개 포함. Starlette의 기존 anyio 별칭 관련 폐기 예정 경고 1개가 있었으며 실패는 없습니다. 규칙 검사에는 임시 스키마와 검사 전용 모델을 사용합니다.
- `docker compose up -d --no-build --wait --wait-timeout 240`: 앱·DB 재생성 후 모두 healthy. 기존 볼륨 유지.
- `node scripts/check_release.mjs`: **실제 모델/API·재시작·논리 복원 6개 묶음 통과**. 같은 쿠키의 닉네임·게임·시도·점수·시작 시각·채팅 복구, 실제 경과 시간 지속, 새 DB의 모든 테이블·sequence 일치, 복원 후 중복 요청을 확인했습니다. 검사 컨테이너·DB 볼륨·임시 설정 정리와 공유 모델 보존도 확인했습니다.
- `node test-results/check-live-ui.mjs`: **실제 서버 GET·Chrome 화면 6개 통과**. 1600×1000, 390×844, 320×844에서 실제 날짜·어제 정답·기준 점수·로고·닉네임 입력·배치를 확인했습니다. JavaScript 오류와 API 쓰기 요청은 0건이며 검사 프로필을 정리했습니다. 기존 읽기 전용 검사 도구를 재사용했으며 변경하지 않았습니다.
- Linux/arm64 `backend-deps` 빌드: 기반 이미지 확인 후 첫 `/bin/sh`에서 `exec format error`, 실패. 의존성 설치 전에 중단됐으며 이 Docker 환경에서 arm64 실행을 확인하지 못했습니다.

재시작·복원 결과는 Git에서 제외하는 `test-results/release-checks.json`, 실제 화면 결과는 `test-results/live-ui-checks.json`과 PNG에 있습니다. 실제 사용자 DB의 백업 생성과 **검사 DB의 복원 검사**는 별개입니다. 실사용 백업을 덮어쓰거나 실사용 기록으로 복원 검사를 하지 않았습니다. 이전 9월 20일 검사 수치와 합산하지 않습니다.

## 영향과 남은 일

- DB 구조·현재 모델·사용자 기록·UI 변경 없음. 기존 migration 001~003 보존.
- 현재 `.env`를 덮어쓰지 않았습니다. 새 항목은 Compose 기본값으로 동작하며 HTTPS 운영 때 실제 origin·Secure 쿠키를 별도로 지정합니다.
- GitHub Actions 원격 실행, 공개 배포·실제 인증서/프록시·운영 부하·실제 Mac/arm64·Safari·실제 모바일은 미검증입니다.
- 공개 전에 외부 백업 예약·실패 알림·보관 기간·채팅 운영 정책을 확정해야 합니다. 임의의 자동 데이터 삭제나 서비스 구매는 하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
