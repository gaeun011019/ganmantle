# 2026-09-21 — 단어 대비·최근 구분선·연속 막대와 입력 테두리

- 기록 ID: 2026-09-21-005
- 분야: 화면 / 검사 / 문서
- 유형: 변경 / 수정 / 삭제
- 구현 상태: 로컬 구현·빌드·브라우저 검사 완료
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

추측한 단어가 더 분명히 보이도록 단어와 표 제목의 글자색·굵기를 조정했습니다. 최근 단어 아래에만 구분선을 남기고 순위 막대의 칸 분할을 없앴으며, 입력창과 추측하기 버튼을 하나의 테두리로 묶었습니다. 직전에 조정한 여백과 글자 크기는 유지합니다.

| 변경 전 | 변경 후 |
|---|---|
| 일반 단어 글자 굵기 400·회청색 | 일반 단어 굵기 600·짙은 글자색, 최신·정답 단어는 짙은 파랑 |
| 추측표 제목 아래와 각 입력 행 아래 구분선 | 최근 단어 한 행 아래에만 2px 구분선 |
| 흰 간격으로 나눈 10칸 순위 막대 | 칸 분할 없는 연속 순위 막대 |
| 입력창의 개별 테두리와 옆에 붙은 추측 버튼 | 두 요소를 감싸는 하나의 테두리와 포커스 표시 |

흰 배경·하늘색 포인트·로고·하단 사용자 랭킹·작은 채팅은 유지합니다. 하단 랭킹 표의 구분선은 이번 추측표 변경에 포함하지 않습니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 역할과 변경 |
|---|---|---|
| [styles.css](../../frontend/src/styles.css) | `.guess-table thead th`, `.guess-table td`, `.guess-table tbody th`, `.latest-guess` | 추측표 제목·일반 행의 선을 제거하고 최근 행 아래 구분선만 유지 |
| [styles.css](../../frontend/src/styles.css) | `.guess-word`, `.score`, `.attempt`, `.word-rank`, `.recent-row`, `.correct-row` | 단어·점수·제목·보조 숫자의 글자색과 단어 굵기 조정 |
| [styles.css](../../frontend/src/styles.css) | `.rank-track::after` | 반복 그라데이션으로 만들던 칸 구분 제거 |
| [styles.css](../../frontend/src/styles.css), [App.tsx](../../frontend/src/App.tsx) | `.guess-form`, 추측 입력 폼 | 공통 외곽선과 포커스 표시, 내부 입력·버튼의 테두리 정리 |
| [App.tsx](../../frontend/src/App.tsx), [WordRank.tsx](../../frontend/src/ranking/WordRank.tsx) | 추측표 캡션·순위 막대 주석 | 연속 막대 표시와 맞도록 설명 수정 |
| [README](../../README.md), [개발 명세](../../GANMANTLE_SPEC.md), [모델 안내](../../docs/MODEL.md) | `WordRank` 역할·현재 표시 규칙 | 기존 블록 설명을 연속 막대로 갱신. 과거 검증·변경 기록은 유지 |
| [월별 목록](README.md), [전체 목록](../README.md) | 최신 기록·다음 번호 | 이번 변경 기록 연결 |

## 어떤 코드인가요?

변경 전 일부 발췌:

```css
.guess-word { font-weight: 400; line-height: 1.7; }
.guess-table .latest-guess > tr > * { border-bottom: 2px solid #d4e6f0; }
.rank-track::after {
  content: '';
  position: absolute;
  inset: 0;
  background: repeating-linear-gradient(to right, transparent 0, transparent calc(10% - 2px), #fff calc(10% - 2px), #fff 10%);
}
```

변경 후 일부 발췌:

```css
.guess-word { color: #172b3a; font-weight: 600; line-height: 1.7; }
.guess-table .latest-guess > tr > * { border-bottom: 2px solid #b8cedc; }
.guess-form { border: 1px solid #8097a8; border-radius: 10px; background: #fff; }
.guess-form:focus-within { border-color: #175e80; outline: 2px solid #76c0e5; outline-offset: 2px; }
.guess-form input:focus-visible { outline: none; }
.guess-form button:focus-visible { outline-offset: -4px; }
```

일반 행과 제목의 테두리는 제거하고 `.rank-track::after`도 삭제했습니다. 입력창의 포커스는 폼 외곽선으로 표시하며, 버튼은 내부 포커스 표시도 유지합니다. 순위 채움 산식과 색 구간은 그대로 사용합니다.

## 어떻게 확인했나요?

| 확인 방법 | 결과 |
|---|---|
| 최종 CSS·App·WordRank 소스 확인 | 일반 행·제목 선 제거, 최근 행 구분선, 글자 대비, 공통 입력 테두리·포커스, 연속 막대 설명 반영 확인 |
| 현재 문서의 블록·칸 설명 검색 | README·개발 명세 두 곳·모델 안내를 연속 막대로 갱신. 과거 검증·변경 기록의 당시 표현 유지 |
| 최종 Docker 앱 이미지 빌드 | TypeScript·Vite 빌드 통과 |
| 로컬 실행 반영 | app·DB Healthy, localhost:8000에 최종 빌드 반영 |
| `node scripts/check_ui.mjs` | 22개 통과, `passed: true`, 종료 코드 0. Chrome JavaScript 오류 0, 임시 프로필 정리 완료 |
| 데스크톱·모바일 자동검사 | 1600×1500·390×844·320×844. 검사 전용 API 자료로 중복·정렬·정답·자정·랭킹·채팅 확인, 실제 DB 쓰기 없음 |
| 데스크톱 `ui-layout.png`·320px 모바일 PNG 직접 확인 | 최근 행 아래만 구분선, 연속 막대, 버튼까지 포함한 공통 테두리, 진해진 단어와 제목 확인. 모바일 제목 한 줄 유지 |
| 변경 문서의 로컬 Markdown 링크 | 6개 문서에서 94개 링크 대상 존재 확인 |

흰 배경의 계산상 대비는 일반 단어 14.55:1, 최신·정답 단어 7.12:1, 표 제목 7.39:1입니다. 이 수치는 전체 접근성 검사나 인증 결과가 아닙니다.

## 영향과 남은 일

- 모델·DB·게임 규칙·정렬·랭킹·실제 `.env` 변경 없음.
- 글자 크기·본문 여백·순위별 채움 산식 변경 없음.
- 로컬 앱에 빌드 반영 완료. GitHub 업로드·공개 배포는 수행하지 않았습니다.
- 모바일 크기는 Windows Chrome 에뮬레이션으로 자동검사했습니다. 실제 모바일 기기·Mac·Safari는 이번에 검사하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
