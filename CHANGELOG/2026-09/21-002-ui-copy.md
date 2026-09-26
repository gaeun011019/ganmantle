# 2026-09-21 — 날짜 변경 배너와 불필요한 UI 문구 정리

- 기록 ID: 2026-09-21-002
- 분야: 화면 / 검사 / 문서
- 유형: 수정 / 삭제
- 구현 상태: 완료
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

사용자가 표시한 날짜 변경 배너를 삭제하고, 게임 화면 전반의 반복 안내와 구현 설명을 정리했습니다. 로고·흰색/하늘색·본문 너비·하단 랭킹·작은 채팅 팝업은 유지합니다.

| 변경 전 | 변경 후 |
|---|---|
| 날짜 변경을 감지하면 큰 안내 배너가 계속 표시됨 | 새 날짜·어제 정답·시작 버튼으로 바로 갱신. 별도 배너 없음 |
| 중복 단어 재입력 시 별도 안내 배너 | 기존 행이 최근 입력 영역으로 이동. 최초 번호·시도 수 유지 |
| 시작 안내, 상단 슬로건, 입력 아래 서브워드 설명, 접힌 게임 설명, 반복 푸터 | 화면에서 제거. 게임 규칙은 README에 유지 |
| 정답 배너에 시도 횟수를 다시 표시 | 정답 결과만 표시. 시도 횟수는 기존 요약에 유지 |
| 랭킹 정렬·공동 순위·갱신 주기를 문장으로 설명 | 실제 랭킹·최고 유사도·단어 순위와 공동 순위의 시간만 표시 |
| 채팅 정상 연결 표시·키보드 도움말·닉네임 설정 중복 설명 | 제거. 공개 대화 범위, 방 이름, 오류·오프라인·재연결·초대 결과는 유지 |

닉네임 길이 조건, 입력 거절, 연결 실패, 로딩과 빈 상태는 플레이에 필요한 피드백으로 남기고 짧게 표현했습니다. 모델 준비 실패의 내부 오류는 게임 화면에 직접 표시하지 않습니다. 입력 label과 표의 화면 낭독기용 설명도 보존했습니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 역할과 변경 |
|---|---|---|
| [App.tsx](../../frontend/src/App.tsx) | `App`, `accept`, `mutate`, `errorMessage` | 메인 게임 화면. `DATE_NOTICE`·`notice` 상태와 JSX 제거, 중복 설명 정리. 날짜 비교·입력 초기화·서버 재조회는 유지 |
| [Ranking.tsx](../../frontend/src/ranking/Ranking.tsx) | `Ranking` | 랭킹 화면. 설명 문단 및 삭제된 ID를 가리키는 `aria-describedby` 제거 |
| [ChatPanel.tsx](../../frontend/src/chat/ChatPanel.tsx) | `ChatPanel` 및 작업 결과 문구 | 채팅 화면. 정상 연결 문구 숨김, 반복 문구 축약. 메시지 전송·구독·초안 저장은 유지 |
| [styles.css](../../frontend/src/styles.css) | 제거한 요소의 선택자, `.chat-compose` | 쓰이지 않는 설명·배너 CSS 제거. 채팅 도움말 삭제 후 입력창 하단 여백 조정 |
| [check_ui.mjs](../../scripts/check_ui.mjs) | 기존 화면·중복·완료·자정 검사 | 사라진 문구 대신 최근 행·시도 수·날짜 갱신과 필요한 오류 표시를 검증 |
| [check_chat_ui.mjs](../../scripts/check_chat_ui.mjs) | 초기 SSE 연결 대기 | ‘실시간 연결됨’ 문구 대신 실제 SSE 수신과 연결 중 표시 해소를 확인 |
| [README.md](../../README.md), [월별 목록](README.md), [전체 목록](../README.md) | 화면 정리 및 최신 기록 | 수정 내용·파일 역할·확인 결과를 찾을 수 있도록 연결 |

## 어떤 코드인가요?

`App.accept` 일부 변경 전:

```tsx
if (next.date_changed || (dateHint.current && dateHint.current !== next.puzzle_date)) {
  setNotice(DATE_NOTICE);
  setWord('');
  setWordNotice('');
}
```

변경 후:

```tsx
if (next.date_changed || (dateHint.current && dateHint.current !== next.puzzle_date)) {
  setWord('');
  setWordNotice('');
}
```

날짜 전환 동작을 유지하면서 화면 배너만 없앴습니다. `mutate`에서도 `date_changed` 오류는 별도 배너 없이 저장된 새 상태를 조회합니다. 중복 단어는 기존 서버 응답의 최근 순서로 표시하므로 별도 안내 상태가 필요하지 않습니다.

## 어떻게 확인했나요?

| 확인 방법 | 결과 |
|---|---|
| `node --check scripts/check_ui.mjs`, `node --check scripts/check_chat_ui.mjs` | 두 검사 도구 문법 통과 |
| `docker compose up -d --no-deps --build app` | TypeScript 검사·Vite 빌드·앱 재실행 통과. 앱/DB healthy 확인 |
| `node scripts/check_ui.mjs` | Chrome 22개 검사 통과. 검사 전용 API/SSE 자료로 기존 정렬·중복·시도 수·정답·자정 전환과 필요한 오류 안내 확인 |
| `node test-results/check-live-ui.mjs` | 실제 localhost GET 응답 대조 6개 통과. 서버 날짜·어제 정답·실제 기준 점수·로고·닉네임 폼 확인. API 쓰기 0건 |
| 데스크톱·모바일 배치 | 실제 화면 1600×1000, 390×844, 320×844 확인. 입력/채팅을 포함한 검사 자료 화면도 확인. 페이지 가로 넘침 없음, 넓은 표는 표 내부 스크롤 유지 |
| 화면 캡처 검토 | 실제 데스크톱·320px 화면과 게임/랭킹/채팅 검사 화면에서 삭제한 문구의 빈 공간·중복 표시 없음 확인 |
| 브라우저 오류 | 두 브라우저 검사 모두 JavaScript 오류 0건. 검사 프로필 정리 완료 |

이번에 생성한 결과는 Git에서 제외하는 `test-results/ui-checks.json`, `live-ui-checks.json`과 같은 폴더의 PNG에 있습니다. `test-results/check-live-ui.mjs`는 기존 읽기 전용 로컬 검사 도구를 재사용했으며 변경하지 않았습니다. UI 자료의 점수는 경계 표시 검사용이며 실제 모델 재검증 결과로 취급하지 않습니다. 실제 서버 화면 검사는 별도로 실제 응답과 대조했습니다.

## 영향과 남은 일

- DB·모델·점수 계산·랭킹 규칙·설정 변경 없음. 사용자 기록을 초기화하지 않았습니다.
- 로컬 앱 컨테이너만 다시 빌드·실행했습니다. http://localhost:8000 에서 새로고침하면 반영된 화면을 볼 수 있습니다. GitHub 업로드·공개 배포는 하지 않았습니다.
- 미완료 구현 없음. 실제 Mac·iPhone·Android 기기는 미검사이며 모바일은 Windows Chrome의 화면 크기 에뮬레이션입니다.
- 채팅 전송·초대·권한과 실제 모델 계산은 변경하지 않아 전체 통합 검사를 다시 실행하지 않았습니다. 이번 채팅 검증은 팝업·표시·입력 경계와 변경된 검사 도구의 문법 확인입니다. 실제 자정까지 기다리는 검사 대신 서버 응답을 모사해 경계를 검증했습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
