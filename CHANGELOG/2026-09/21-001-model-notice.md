# 2026-09-21 — 사용자 화면의 모델 변경 안내 제거

- 기록 ID: 2026-09-21-001
- 분야: 화면 / 검사 / 문서
- 유형: 수정 / 삭제
- 구현 상태: 소스 정리·빌드 완료. Docker 실행 화면 재빌드·브라우저 재검은 이번에 실행하지 않음.
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

사용자 요청에 따라 모델 변경에 관한 내부 안내를 화면에서 표시하지 않습니다. 작업 시작 때 App.tsx에는 해당 조건부 p 요소가 이미 삭제되어 있었으므로 그 상태를 유지했습니다. 함께 없어져 있던 일반 notice 표시만 복구해 중복 입력·날짜 변경 안내를 다시 표시하고, 사용되지 않는 notice 변수로 인한 TypeScript 오류도 방지했습니다.

## 어디를 수정했나요?

| 파일 | 수정 위치 | 내용 |
|---|---|---|
| [App.tsx](../../frontend/src/App.tsx) | 로딩·오프라인 안내 다음 JSX | 모델 안내가 없는 상태를 확인하고 일반 notice 표시 한 줄만 복구. 빈 안내 요소를 만들지 않음 |
| [check_ui.mjs](../../scripts/check_ui.mjs) | 모델 점수 갱신 안내 검사 | 갱신 시각·null·필드 없음 모두 모델 안내가 없으며 입력값·목록·횟수는 유지되는지 확인하도록 기존 기대값 수정 |
| [월별 목록](README.md), [전체 목록](../README.md) | 최신 항목 | 이번 기록과 다음 번호 연결 |

## 어떤 코드인가요?

모델 안내를 제거할 때는 문장만 비우지 않고, 문장을 감싸는 `state?.model.scores_updated_at &&` 조건부 JSX 전체를 제거합니다. 현재 그 요소는 없습니다. 일반 게임 안내는 다음 한 줄로 표시합니다.

```tsx
{notice && <p className="message notice" role="status">{notice}</p>}
```

## 어떻게 확인했나요?

- frontend 폴더에서 `npm.cmd run build`: TypeScript·Vite 빌드 통과.
- `node --check scripts/check_ui.mjs`: 문법 검사 통과.
- App.tsx에서 모델 안내 문구·model-update-notice가 없고 일반 notice 표시가 있는지 확인.
- 실제 브라우저 22개 검사는 이번에 실행하지 않았습니다. 과거 통과 결과와 구분합니다.

## 영향과 실행 방법

DB·모델·서버 점수 계산은 수정하지 않았습니다. Docker에서 실행 중인 화면에 반영하려면 ganmantle-v1 폴더에서 다음 명령을 실행한 뒤 브라우저를 새로고침합니다.

```powershell
docker compose up -d --build
```

[월별 목록](README.md) · [전체 변경 기록](../README.md)
