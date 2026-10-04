# 2026-10-04 — UI·코드 정리·Mac 지원을 GitHub main에 반영

- 기록 ID: 2026-10-04-004
- 분야: Git / 문서
- 유형: 변경
- 관련 커밋: 이 문서를 포함하는 커밋. `git log -1 -- CHANGELOG/2026-10/04-004-github-update.md`로 조회

## 무엇을 반영하나요?

사용자의 GitHub 업로드 요청에 따라 완료한 세 작업의 소스·검사·문서를 하나의 커밋으로 묶습니다. 원격 `origin/main`을 fetch한 결과 로컬 기준 커밋과 같아 기존 `main`에 반영합니다.

- [04-001 닉네임 입력창](04-001-nickname-input-border.md): 입력창과 버튼을 한 테두리로 표시.
- [04-002 폴더·코드 정리](04-002-cleanup-readability.md): 사용처 확인, 임시 파일 정리, 공통 HTTP 요청, 코드 줄바꿈, 오래된 UI 검사 기준 수정.
- [04-003 Mac 관리](04-003-mac-management.md): POSIX sh 관리 도구, Safari 요청 취소 호환 처리, Windows 기록 이전과 ngrok 전환 안내.

각 작업의 파일·함수·핵심 코드·검증 결과는 해당 기록에 있습니다. 이번 업로드 준비에서는 앱 동작을 추가로 바꾸지 않고 GitHub에서 맥으로 내려받는 설명을 보완했습니다.

## 어디를 수정했나요?

| 파일 | 위치 | 변경 내용 |
|---|---|---|
| [docs/MAC.md](../../docs/MAC.md) | 1단계 소스 준비 | `git clone`, GitHub Download ZIP, 기존 clone의 `git pull --ff-only` 안내. 이전 전달용 ZIP과 최신 GitHub 소스를 구분 |
| [README](../../README.md) | 최신 변경 | 이번 세 작업의 GitHub 반영 범위 연결 |
| [docs/DEPLOYMENT.md](../../docs/DEPLOYMENT.md) | 머리말·GitHub 자동 검사 | 최신 기록과 원격 Actions 링크 연결 |
| [월별 목록](README.md), [전체 목록](../README.md) | 최신 기록 | 이 반영 기록 추가 |

맥에서 소스를 새로 받는 명령은 다음과 같습니다.

```sh
git clone https://github.com/gaeun011019/ganmantle.git ganmantle-v1
cd ganmantle-v1
sh scripts/manage.sh setup
```

실제 `.env`, `ngrok.local.yml`, 인증 토큰, DB·백업·모델, `node_modules`, `dist`, 검사 산출물, 전달용 ZIP은 커밋에 포함하지 않습니다. 이전 001~003 기록의 당시 미업로드 설명은 작업 이력으로 유지합니다.

## 확인 결과

- 원격 조회: `git fetch origin` 성공, `HEAD...origin/main` 차이 0/0.
- 업로드 범위 검토: 민감 파일·생성 파일 제외 규칙과 신규 파일 목록 확인, 별도 읽기 검토에서 차단 요소 없음.
- 문서: GitHub에서 받는 절차와 Mac 실행 절차 연결. 로컬 링크·`git diff --check`로 경로와 공백 검사.
- 앞선 코드 정리 작업: 백엔드 288개·UI 33개 검사 통과. [04-002](04-002-cleanup-readability.md)의 실행 결과이며 이번에 다시 실행한 검사는 아닙니다.
- 앞선 Mac 지원 작업: 관리 명령 모의 검사 42개·요청 처리 모의 검사 13개·TypeScript/Vite 빌드 통과. [04-003](04-003-mac-management.md)의 실행 결과입니다.
- [GitHub Actions](https://github.com/gaeun011019/ganmantle/actions)는 push 시 기존 [check.yml](../../.github/workflows/check.yml)에 따라 실행됩니다. 원격 검사 결과는 해당 커밋의 실행 기록과 연결해 확인합니다.

## 영향과 남은 일

- DB·모델·실제 환경변수·ngrok 인증 변경 없음. 현재 Windows 서버를 재시작하지 않습니다.
- 소스 업로드는 맥에 자동 설치하거나 운영 서비스를 배포하지 않습니다.
- 실제 Mac/Apple Silicon·Safari·Mac ngrok 연결 확인과 운영 기록 이전은 [Mac 안내](../../docs/MAC.md)를 따릅니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
