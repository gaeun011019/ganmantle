# 2026-09-19 — 2단계 전체 사용자 랭킹

- 기록 ID: 2026-09-19-006
- 분야: 게임 / DB / 화면 / 문서
- 유형: 추가 / 수정
- 구현 상태: 완료 (브라우저 시각 검사와 실제 Mac 검사는 미실행)
- 관련 커밋: 미기록 (현재 로컬 작업)

## 무엇이 달라졌나요?

명세 3.5절과 2단계의 다음 미완료 기능인 전체 랭킹을 구현했습니다. 기존 `ganmantle-v1/`에서 기본 게임을 유지하며 확장했습니다. **2단계는 새 `v2` 폴더나 별도 DB를 뜻하지 않습니다.**

| 변경 전 | 변경 후 |
|---|---|
| 본인의 게임 기록만 표시 | 게임 아래에서 오늘 완료자의 전체 순위와 도전 중 목록 표시 |
| 순위 계산 없음 | 시도 횟수 → 서버에 저장한 원래 풀이 시간 순서 |
| 공동 순위 없음 | 횟수와 시간이 모두 같으면 `1, 1, 3` 방식의 공동 순위 |
| 테스트 검색 경로에 `public` 포함 | 테스트마다 만든 임시 스키마만 검색하여 기존 테이블 접근 방지 |

## 어디를 수정했나요?

| 파일 | 코드 위치 | 추가·변경한 내용 |
|---|---|---|
| [backend/app/game.py](../../backend/app/game.py) | `ranking()`, `state()` | 날짜별 전체 랭킹 조회와 상태 응답의 `ranking` 필드 |
| [frontend/src/api.ts](../../frontend/src/api.ts) | `RankingPlayer`, `DailyRanking`, `State.ranking` | 완료·도전 중 응답 타입 |
| [frontend/src/ranking/Ranking.tsx](../../frontend/src/ranking/Ranking.tsx) | `Ranking()`, `duration()` | 순위·공동 순위·내 행·도전 중·실제 빈 상태 표시 |
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | `Ranking` 연결 | 게임 아래에 랭킹 배치, 기존 상태 갱신 활용 |
| [frontend/src/styles.css](../../frontend/src/styles.css) | `.ranking-card`, `.ranking-table`, `.my-ranking-row`, 모바일 규칙 | 기존 녹색 화면에 맞춘 랭킹과 좁은 화면 줄바꿈 |
| [backend/tests/test_ranking.py](../../backend/tests/test_ranking.py) | `test_*` 6개 | 순위·원래 시간·공동 순위·공개 필드·재접속·닉네임 변경·조회 불변·자정·중복 검증 |
| [backend/tests/test_rules.py](../../backend/tests/test_rules.py) | `runtime()` | 테스트 DB 검색 경로를 임시 스키마 하나로 제한 |
| [scripts/smoke_ranking.py](../../scripts/smoke_ranking.py) | `run()` | 실제 모델과 두 익명 세션을 사용한 재현 가능한 검사 |
| [README.md](../../README.md) | 현재 상태·파일 역할·규칙·검사·다음 단계 | 1·2단계 완료와 3단계 계획, 실행·수정 위치 안내 |
| [docs/VALIDATION.md](../../docs/VALIDATION.md) | 2단계 검증 기록 | 이번 실행 결과와 기존 단계의 검사 구분 |
| [CHANGELOG/README.md](../README.md), [월별 목록](README.md), [이 기록](19-006-ranking.md) | 기록 목록 | 파일·코드·확인 결과를 찾아볼 수 있도록 연결 |

## 어떤 코드인가요?

`game.state()` 응답에는 원래 본인의 `game`과 `model`만 있었고, 아래 필드가 추가됐습니다(일부 발췌).

```python
"ranking": ranking(conn, day, user["id"] if user else None),
```

신규 `game.ranking()`의 핵심입니다(일부 발췌).

```sql
CASE WHEN g.status = 'completed' THEN
    RANK() OVER (
        PARTITION BY g.status
        ORDER BY g.attempts, g.completed_at - g.started_at
    )
ELSE NULL END AS rank
```

순위는 밀리초나 화면의 초 단위로 자르기 **전** PostgreSQL 시간 차로 계산합니다. 닉네임은 공동 순위 안과 도전 중 목록의 표시 순서만 고정하며, 순위를 가르는 조건에는 넣지 않습니다. 완료와 도전 중을 한 번에 조회해 두 목록 사이에 중복되는 결과를 피합니다.

`runtime()`의 실제 수정 전후입니다.

```python
# 변경 전: public에 기존 테이블이 있으면 테스트가 그 테이블을 찾을 수 있었습니다.
options=f"-c search_path={schema},public"
# 변경 후: 해당 검사에서 생성한 스키마 하나만 사용합니다.
options=f"-c search_path={schema}"
```

랭킹에 필요한 횟수·시작·완료 시각이 이미 저장되어 있으므로 테이블이나 별도 서비스는 추가하지 않았습니다. 화면은 기존 상태 요청으로 약 10초마다 갱신하고 입력·시작·닉네임 변경·창 복귀·재접속·날짜 변경도 같은 흐름을 사용합니다. 미시작 사용자는 목록에 넣지 않고, 도전 중인 사람에게는 순위를 부여하지 않습니다. 상대의 정답·추측 단어·세션을 응답에 포함하지 않습니다.

## 어떻게 확인했나요?

| 이번에 실제 실행한 검사 | 결과 |
|---|---|
| `docker compose build app` | TypeScript 검사와 Vite 7.3.6 빌드 통과 |
| 새 이미지에서 `pytest -q backend/tests` | **17 passed**, 35.95초. 기본 게임 11개 + 랭킹 6개 |
| `docker compose run --rm --no-deps app python scripts/smoke_ranking.py` | 실제 모델·실제 PostgreSQL·두 익명 사용자·횟수 순위·완료/진행 분리·본인 표시·재접속·중복 불변 통과 |
| `docker compose up -d --no-deps app`, HTTP 확인 | 앱만 교체 후 앱·DB healthy. 간맨틀 화면 200, DB/모델 정상, 실제 랭킹 응답 확인 |
| 기존 데이터 비교 | 사용자·당일 문제·migration 및 기존 입력 행 해시 일치. 임시 테스트 스키마 잔여 0개 |

경계 조건 테스트는 테스트용 점수 모형과 고정 시계를 사용합니다. 특히 10.000100초와 10.000900초가 같은 표시 밀리초여도 다른 순위인지, 정확한 동률은 공동 1위 다음 3위인지 검증했습니다. 실제 모델 검사는 별도 명령으로 실행했으며 기존 앱 DB의 데이터를 만들거나 바꾸지 않고 임시 스키마를 정리합니다. 모델 벤치마크·백업/복원·arm64 의존성 검사는 이전 결과이며 이번에 반복 실행하지 않았습니다.

pytest 경고는 Starlette의 anyio 별칭 사용 중단 예정과 읽기 전용 앱 디렉터리에 캐시를 만들 수 없다는 두 가지입니다. 검사 실패는 없습니다. 브라우저 제어 도구의 연결 목록이 비어 있어 클릭·시각·모바일 검사는 실행하지 못했습니다.

작업 중 진행 중인 게임에 새 입력이 추가되어 전체 DB 해시는 달라졌습니다. 기존 입력 범위를 따로 비교했고 추가 기록은 보존했습니다. 전체 기록이 작업 전후 완전히 불변이었다는 의미는 아닙니다. 비교 범위와 실제 실행 결과는 [검증 기록](../../docs/VALIDATION.md)에 남겼습니다.

## 영향과 남은 일

- DB 변경: 없음. 새 migration 없이 기존 기록으로 순위를 계산합니다. 기존 migration을 수정하지 않았습니다.
- 설정·의존성: 추가 없음. `.env`, 잠금 파일, 모델은 그대로이며 `docker compose up -d --build`로 앱을 갱신합니다.
- 다음 기능: 명세 3단계 채팅(전체·개인·단체방, 초대·수락, 권한 확인, 메시지 저장·재접속). 현재 닉네임은 표시용입니다.
- 미확인: 실제 Mac 및 arm64 모델 실행, 브라우저·모바일 화면. 기존 Windows/Linux amd64 개발 경로로 검증했습니다.
- GitHub 업로드와 공개 배포는 실행하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
