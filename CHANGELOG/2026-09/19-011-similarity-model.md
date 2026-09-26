# 2026-09-19 — 유사도 모델 교체와 실제 단어 순위·블록 표시

- 기록 ID: 2026-09-19-011
- 분야: 모델 / 게임 / 서버 / DB / 화면 / 검사 / 문서
- 유형: 변경 / 추가 / 수정
- 구현 상태: 구현·검증·기존 점수 전환 완료, localhost:8000에 반영
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

E5의 원래 코사인 점수가 높은 구간에 몰려 관련 없는 단어도 대부분 80점대에 표시됐습니다. 계산식의 백분율 변환 오류는 아니었습니다. 고정 한국어 비교에서 더 넓게 구분하는 **paraphrase-multilingual-MiniLM-L12-v2의 ONNX int8 모델**로 변경합니다. 점수에 임의의 빼기·배율·백분위를 적용하지 않고 실제 두 벡터의 코사인 × 100을 유지합니다.

사용자의 추가 요청에 따라, 고정 입력 사전 **49,485개 단어의 실제 모델 벡터**로 단어 유사도 순위와 기준 점수를 계산합니다. 입력 표에는 숫자 순위와 사각 블록을 표시하고, 사용자 랭킹에도 최고 유사도에 해당하는 단어 순위를 함께 표시합니다.

| 변경 전 | 변경 후 |
|---|---|
| E5 점수가 높은 구간에 몰림 | 실제 비교 후 선정한 MiniLM의 원래 코사인 점수 사용 |
| 전 어휘 기준 점수·순위가 `준비 중` | 정답을 제외한 사전 단어의 실제 순위와 1·10·1,000번째 기준 점수 |
| 점수 중심의 입력 표 | 실제 점수, 단어 순위, 순위에 따른 블록 채움·진하기 |
| 모델을 바로 바꾸면 오늘 문제의 지문 불일치로 새 제출 차단 | 논리 백업 후 오늘 기록 전체의 점수와 모델 지문을 원자적으로 전환하는 도구 |

2026-09-19 Linux amd64에서 수행한 모델 단독 비교 결과를 [원본 비교 JSON](../../docs/model-comparison-amd64.json)에서 인용합니다. 전체 사전 인덱스를 포함한 최종 자원 측정과는 구분합니다.

| 실제 비교 | E5 | MiniLM |
|---|---:|---:|
| 정답 후보 90개, 서로 다른 4,005쌍 중 80점대 비율 | 94.31% | 5.12% |
| 같은 쌍의 중앙값 | 82.97 | 44.42 |
| 관련어가 무관어보다 높은 비교 | 17/20 | 18/20 |
| 관련·무관 점수 차이 중앙값 | 5.89 | 50.30 |
| 산책–걷다 | 84.42 | 85.18 |
| 산책–냉장고 | 83.09 | 25.43 |
| 강아지–개 | 83.17 | 90.17 |
| 강아지–책상 | 78.92 | 29.83 |

20개 수동 비교 중 ‘사과–배/모니터’, ‘비–우산/컴퓨터’는 새 모델도 기대 순서를 충족하지 못했습니다. 다의어와 짧은 단어의 의미 한계는 남습니다. 이 비교는 한국어 전반의 품질을 보증하지 않습니다. 모델 출처·선정 근거는 [모델 문서](../../docs/MODEL.md)에 있습니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 역할·변경 내용 |
|---|---|---|
| [model-manifest.json](../../model-manifest.json) | 모델 ID·revision·algorithm·SHA-256 | 새 모델 버전과 두 파일 고정 |
| [docs/model-manifest-e5.json](../../docs/model-manifest-e5.json) | 이전 명세 | 구모델 재현·비교·복구용 정보 보존 |
| [backend/app/similarity.py](../../backend/app/similarity.py) | `SimilarityEngine.__init__`, `vector`, `score`, `rankings`, `get_engine` | 모델별 접두사, 실제 사전 벡터 재사용, 앱의 순위 자료 필수 검증. 워밍업 캐시와 사전 벡터 혼용 방지 |
| [backend/app/word_ranks.py](../../backend/app/word_ranks.py) | `WordRankIndex`, `rankings` | 모델 지문·사전·파일 검증, 전체 단어의 동일한 내적 계산, 공동 순위와 기준 점수 |
| [scripts/prepare_word_ranks.py](../../scripts/prepare_word_ranks.py) | `main`, `write_json`, `progress.json` | 전체 사전 벡터 생성·체크포인트 재개·검증. partial 누락 시 이전 완료 파일을 새 모델로 재사용하지 않음 |
| [compose.yaml](../../compose.yaml), [Dockerfile](../../Dockerfile) | `MODEL_DIR` | 별도 준비한 MiniLM 모델·순위 자료 디렉터리 연결 |
| [scripts/prepare_model.py](../../scripts/prepare_model.py) | `--manifest` | 현재 모델과 이전 명세를 선택해 다운로드·검증 |
| [scripts/compare_models.py](../../scripts/compare_models.py) | `EXAMPLES`, `measure` | 같은 실제 엔진으로 한국어 20쌍·정답 90개 분포·독립 코사인 계산 비교 |
| [scripts/benchmark_model.py](../../scripts/benchmark_model.py) | `--without-index`, `scoring_path`, `word_ranks` | 모델 단독 추론과 준비된 사전 벡터 경로를 구분. 순위 최초 계산·캐시 조회·메모리·지연 측정 |
| [backend/migrations/003_score_update.sql](../../backend/migrations/003_score_update.sql) | `puzzles.scores_updated_at` | 오늘 점수를 다시 계산한 시각 기록. 단어 순위용 DB 열은 추가하지 않음 |
| [scripts/recalculate_scores.py](../../scripts/recalculate_scores.py) | `recalculate_scores`, `--apply` | 오늘 저장 점수·모델 지문을 한 트랜잭션으로 전환. 기본은 DB를 바꾸지 않는 사전 계산 |
| [backend/app/game.py](../../backend/app/game.py) | `model_status`, `word_rankings`, `state`, `ranking` | 실제 기준·입력 순위·최고 유사도 순위 응답. 초기 조회에서는 문제만 고정하고 도전 기록은 만들지 않음 |
| [frontend/src/api.ts](../../frontend/src/api.ts) | `similarity_reference`, `similarity_rank`, `best_similarity_rank` | 서버가 계산한 순위·기준 점수와 준비 상태의 응답 타입 |
| [frontend/src/ranking/WordRank.tsx](../../frontend/src/ranking/WordRank.tsx) | `WordRank`, `fill`, `tone` | 정답·1~1,000위·순위 밖·준비 전 표시. 순위 기준 블록 채움과 색상 |
| [frontend/src/App.tsx](../../frontend/src/App.tsx), [Ranking.tsx](../../frontend/src/ranking/Ranking.tsx), [styles.css](../../frontend/src/styles.css) | `referenceScore`, `WordRank`, `.rank-track`, `.rank-fill`, `.model-update-notice` | 실제 기준·입력 표·사용자 랭킹 표시, 모델 전환 안내, 사각 블록의 구간과 최소 폭 |
| [backend/tests/test_model_update.py](../../backend/tests/test_model_update.py) | 전환·보존·실패·자정 검사 | 임시 PostgreSQL 스키마에서 점수 전환 규칙 검증. 순위 응답 fixture 호환 유지 |
| [backend/tests/test_word_ranks.py](../../backend/tests/test_word_ranks.py) | 순위 경계·동점·파일 검사 | 원점수 비교, 정답 제외, 1,000위 경계의 동점, 누락·변조·모델/사전 불일치 거부 |
| [backend/tests/test_word_ranks_api.py](../../backend/tests/test_word_ranks_api.py) | 기준·입력·랭킹·재접속·자정 검사 | 순위 전달, 자료 실패 시 차단과 기록 보존, 정답·상위 단어 목록 비노출 |
| [backend/tests/test_word_rank_preparation.py](../../backend/tests/test_word_rank_preparation.py) | partial 누락·정상 재개 검사 | 임시 파일로 이전 벡터의 잘못된 재인증 거부와 정상 진행·완료 구간 재개 검증 |
| [backend/tests/test_rules.py](../../backend/tests/test_rules.py), [test_ranking.py](../../backend/tests/test_ranking.py) | `RuleTestEngine.rankings`, 공개 필드 검사 | 기존 규칙 검사에 순위 fixture와 새 공개 필드 반영 |
| [scripts/smoke_ranking.py](../../scripts/smoke_ranking.py) | 실제 순위·기준 비교 | 실제 모델·임시 DB에서 코사인, 기준 점수, 입력 순위, 정답 0위, 중복·재접속 확인 |
| [scripts/check_ui.mjs](../../scripts/check_ui.mjs) | 화면 fixture 검사 | 전환 안내와 순위·블록·기준 점수 표시 검증. 실제 모델 검사는 위 스모크와 구분 |
| [docs/MODEL.md](../../docs/MODEL.md), [README.md](../../README.md), [명세](../../GANMANTLE_SPEC.md), [검증 기록](../../docs/VALIDATION.md) | 현재 모델·사전 순위·실행·업데이트 | 이전 E5 기록과 현재 구현·검증 범위 구분 |
| [비교 JSON](../../docs/model-comparison-amd64.json), [추론 벤치마크](../../docs/model-benchmark-minilm-amd64.json), [사전 벡터 벤치마크](../../docs/model-benchmark-ranked-amd64.json) | 재현 가능한 실측 자료 | 측정 환경과 모델 추론/준비 벡터 조회 경로를 구분해 기록 |
| [전체 목록](../README.md), [월별 목록](README.md) | 011 링크·다음 번호 012 | 이번 변경 기록 연결 |

## 어떤 코드인가요?

두 모델의 학습 방식이 달라 입력 전처리도 모델 지문에 포함된 알고리즘 이름으로 고정합니다. 새 모델에 E5 전용 접두사를 넣지 않습니다. 아래는 `similarity.py`의 일부 발췌입니다.

```python
prefixes = {
    "e5-query-mean-pool-l2-cosine100-v1": "query: ",
    "minilm-mean-pool-l2-cosine100-v1": "",
}
cosine = self._np.dot(self.vector(word), self.vector(answer))
return float(self._np.clip(cosine, -1.0, 1.0) * 100.0)
```

`WordRankIndex.rankings`는 같은 float32 벡터 한 행과 정답 벡터를 같은 `np.dot`으로 계산합니다. 표시용 소수 둘째 자리로 반올림하기 전 점수가 **정확히 같으면 공동 순위**이며, 다음 순위를 건너뛰는 `1, 1, 3` 방식입니다. 정답은 유사어 목록에서 제외하고 별도 `0`으로 표시합니다. 순위가 1~1,000인 단어만 전달하며, 1,000위 경계의 동점 단어는 모두 포함될 수 있습니다. 그 밖은 `null`입니다.

기준 점수는 정답을 뺀 내림차순 목록의 **1번째·10번째·1,000번째 점수**입니다. 동점으로 특정 순위 번호가 비어도 해당 위치의 점수를 사용합니다. 정답과 상위 단어 목록은 응답에 포함하지 않고, 기준 숫자와 사용자가 입력한 단어의 순위만 공개합니다.

```python
# word_ranks.py 일부 발췌
scores[answer_position] = -np.inf
order = np.argsort(-scores, kind="stable")
# 동점의 실제 순위는 중간 반복문에서 처리합니다. 반환부 일부입니다.
return {"ranks": ranks, "reference": {
    "vocabulary_size": len(self.words),
    "top1": float(scores[order[0]]), "top10": float(scores[order[9]]),
    "top1000": float(scores[order[999]]),
}}
```

첫 상태 조회부터 기준 점수를 보여주기 위해 오늘 문제를 한 번 고정합니다. 사용자의 도전은 시작 버튼을 눌러야 생성됩니다. 단어 순위는 DB에 별도 저장하지 않고 오늘 정답·일치하는 모델·사전 자료에서 다시 조회하므로 기존 입력, 중복 재표시, 재접속에 같은 규칙이 적용됩니다. 사용자 성적 순위는 기존 시도 횟수·완료 시간 기준을 유지합니다.

블록은 실제 단어 순위로 채웁니다. 정답은 전부 채우고, 1위에 가까울수록 많이 채워지고 진해집니다. `WordRank.tsx`의 일부 발췌입니다.

```tsx
const fill = correct ? 100 : inRange ? ((1001 - rank) / 1000) * 100 : 0;
```

CSS가 채움 위에 사각 구간을 나누며 1,000위에도 최소 3px를 남깁니다. 이 채움 비율은 유사도 퍼센트나 정답 확률이 아닙니다. 순위 밖에는 빈 블록과 `1,000위 밖`, 자료가 준비되지 않았을 때는 `—`를 표시합니다. 자료가 없거나 모델·사전·체크섬이 맞지 않으면 예시 순위를 대신 넣지 않고 새 시작·입력을 막습니다.

오늘 이미 저장된 점수와 새 점수가 섞이지 않게 전환 도구는 오늘의 모든 입력을 같은 정답·새 모델로 재계산합니다. `--from-fingerprint`가 DB 지문과 맞아야 하며 계산 실패·잘못된 점수·자정 경계·DB 잠금 충돌에는 중단합니다. `--apply`일 때만 유사도와 문제의 모델 지문·전환 시각을 함께 갱신합니다. 이미 같은 새 지문이면 같은 명령을 다시 실행해도 재계산하지 않습니다.

입력 단어·횟수·정답·시각·순서·정답 판정·사용자·채팅·지난 날짜는 유지합니다. 미등록 단어 거절·자동 비움과 860px 본문·공동 순위의 시간 표시는 유지합니다.

## 어떻게 확인했나요?

| 확인 범위 | 현재 결과 |
|---|---|
| 모델 원본 다운로드·SHA-256 | 모델 비교 실행 당시 확인한 완료 항목. 고정된 모델 두 파일 합계 135,391,039바이트 |
| E5/MiniLM 모델 단독 비교 | 이번 작업에서 20개 관련/무관 비교와 정답 후보 90개의 4,005쌍 분포를 실제 측정. 결과는 위 표와 원본 JSON |
| 전체 사전 벡터 생성·검증 | 49,485개·384차원, 데이터 76,622,818바이트와 별도 메타데이터. 계산 구간 1,823.2초(검사·빌드 병행). SHA-256·사전·모델·정규화 검사 통과 |
| 순위 단위/API 검사·기존 게임/채팅 회귀·준비 재개 검사 | **111 passed, 609.62초 + 추가 3 passed, 11.19초 = 114개**. 자정·중복·시간·정답·재접속·자료 손상·원자적 전환/롤백 포함 |
| 실제 모델·PostgreSQL 순위 스모크 | 최종 이미지에서 통과. 코사인 독립 식·기준값·단어 순위·정답 0위·입력 거절·두 사용자·중복·재접속·임시 스키마 정리 |
| 전체 점수와 순위 독립 확인 | DB 정답 대신 공개 예제 ‘산책’으로 전체 사전 점수와 순위 일치, 기준 1/10/1000번째 일치, 정답 후보 90개 포함. 예제 7개는 저장 벡터와 새 추론이 완전히 일치 |
| 데스크톱·모바일 폭의 화면·블록·기준 점수·전환 안내 | TypeScript/Vite·Docker 빌드와 **Chrome 화면 16개 통과**, JavaScript 오류 0. 1600×1500·390×844 캡처 확인 |
| 사전 벡터를 포함한 자원·시작·점수/순위 지연 | 독립 Python 프로세스 RSS 576.11→576.36MiB, 전체 로딩 31.824초. 준비 벡터 점수 중앙값 0.033ms·p95 0.089ms, 전체 순위 첫 계산 650.012ms·캐시 0.00375ms |
| 기존 DB 논리 백업·점수 전환·앱 재시작 | custom pg_dump 완료 → 003 적용 → dry run → 오늘 4개 점수 전환 → 앱 재시작 healthy. 사용자1/문제1/게임1/입력4/채팅방1의 점수 외 전체 내용 해시·개수 유지, 기존 001/002 보존, 임시 스키마 0 |
| 이번 문서 연결 검사 | 최종 문서 7개의 UTF-8 읽기와 로컬 링크 121개 확인, 누락 0개 |

화면 검사는 최종 빌드의 API·SSE를 검사 자료로 대체한 표시 검사이며 실제 모델·DB 스모크와 별도입니다. 검사 전용 정적 서버는 종료했습니다. 준비 벡터의 점수 조회 시간은 ONNX 추론 시간이나 HTTP 응답 시간이 아니며, RSS도 앱·DB 전체의 최대 메모리가 아닙니다. 상세 조건은 [검증 기록](../../docs/VALIDATION.md)에 있습니다. 실제 정답·사용자 입력·닉네임·쿠키·DB 백업 내용은 문서에 복사하지 않습니다.

## 영향과 남은 일

- 새 런타임 패키지나 별도 서비스를 추가하지 않습니다. 모델과 사전 벡터는 `models/`에 두고 Git/Docker 이미지에서 제외합니다. 모델 준비 후 전체 사전 벡터도 한 번 생성·검증해야 합니다.
- `003_score_update.sql`은 전환 시각만 추가합니다. 기존 적용 SQL을 바꾸지 않고, 오늘 점수 전환 전 논리 백업을 진행합니다. 이전 모델 파일·명세도 보존합니다. 복구할 때는 모델과 DB의 지문을 함께 확인해야 합니다.
- 기존 [003 모델 기록](19-003-model.md), [007 입력 검사 기록](19-007-word-validation.md), [008 UI 기록](19-008-blue-ui.md)과 E5 벤치마크는 당시 조건의 이력입니다. 그 문서의 `순위 준비 중`이나 당시 모델 설명을 현재 구현 상태로 읽지 않습니다. 이번 기능과 현재 절차는 이 기록·README·명세·MODEL 문서를 기준으로 합니다.
- 새 원본 모델은 Apache-2.0, 이전 E5는 MIT입니다. 출처·고지·대안 검토는 [모델 문서](../../docs/MODEL.md)에 있습니다.
- 실제 Mac·Apple Silicon arm64의 새 모델/사전 벡터 실행, 실제 모바일 기기 검사, 더 넓은 한국어 품질 평가, 4단계 배포 준비는 남아 있습니다. 공개 배포·GitHub 업로드는 하지 않습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
