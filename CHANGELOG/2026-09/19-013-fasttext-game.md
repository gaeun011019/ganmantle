# 2026-09-19 — fastText 원본 계산과 날짜·입력 목록 개선

- 기록 ID: 2026-09-19-013
- 작업 기간: 2026-09-19 시작 → 2026-09-20 모델·DB 전환 완료 (한국 시간). 시작일 기준 파일명과 번호 유지.
- 분야: 모델 / 게임 / 서버 / DB / 화면 / 검사 / 환경 / 문서
- 유형: 추가 / 변경 / 수정
- 구현 상태: 완료 — 실제 모델·DB 전환과 최종 Chrome 검사 통과, 앱·DB 컨테이너 healthy
- 관련 커밋: 미기록. GitHub 업로드·공개 배포는 실행하지 않음.

## 무엇이 달라졌나요?

한국어 fastText 원본 `.bin`으로 사전 안팎의 단어 벡터를 계산하고 실제 게임 검사를 마쳤습니다. 서버의 한국 날짜와 어제 정답을 표시하고, 입력 목록은 최근 한 행 아래에 나머지를 유사도순으로 배치합니다. 논리 백업 후 기존 기록을 보존해 9월 20일 문제의 모델 지문을 전환했습니다.

| 변경 전 | 변경 후 |
|---|---|
| MiniLM의 실제 코사인 점수와 입력 허용 사전을 사용. 사전 밖 입력은 계산 전에 거절 | fastText 경로에서는 완성형 한글 입력을 검사한 뒤 원본 word/subword 벡터로 계산. 미등록이라는 이유만으로 거절하지 않음 |
| 순위 계산은 준비된 비교 사전에 있는 단어 중심 | 미등록 입력도 같은 고정 비교 집합에서 더 높은 원 점수의 개수로 순위를 계산. 비교 집합에 새 입력을 추가하지 않음 |
| 화면에 매일 자정 변경 안내 표시 | 서버 `puzzle_date`를 한국식 날짜로 표시. 바로 전날 저장된 문제가 있으면 그 정답만 추가 표시 |
| 모든 입력 행을 서버의 최근 제출 순서대로 표시 | 최근 입력 한 행을 위에 고정하고, 나머지는 원 유사도 내림차순·동점이면 최초 시도 번호 오름차순 |
| 기준 유사도 항목이 같은 흐름 안에 나열 | 제목을 왼쪽에 두고 1·10·1,000위의 순위와 점수 세 그룹에 같은 폭을 배정. 모바일에서는 제목과 그룹을 나누어 표시 |
| 큰 모델 파일을 Windows 공유 폴더에서 읽음 | 실제 모델과 비교 자료를 Linux 전용 볼륨에 준비하고 앱에 읽기 전용 연결 |

### 이렇게 바꾼 이유

1. **모델 선정 근거를 실제 측정 범위에 맞춥니다.** [011 기록](19-011-similarity-model.md)의 비교 결과는 E5와 MiniLM에 관한 것입니다. 당시 fastText 원본을 실제 측정하지 않았으므로 해당 기록만으로 품질·메모리·arm64 호환성 때문에 배제할 근거는 없었습니다. 이번에는 공식 구현 대조와 실제 한국어 모델 검사를 각각 수행했습니다. 표본 의미 비교는 19/20이지만 예외가 있으며, 꼬맨틀과 동일한 점수·순위나 전체 한국어 품질 우위를 보장하지 않습니다.
2. **최근 입력과 점수 비교를 함께 볼 수 있게 합니다.** 기존 코드는 `last_display_order`로 받은 배열 전체를 그대로 `map`했고, 하위 행을 유사도순으로 정렬하는 코드가 없었습니다. 그래서 전체가 최근 제출 순서로 보였습니다. 첫 행을 분리한 뒤 `slice(1)` 복사본만 정렬하도록 수정했습니다. 중복 입력은 한 번만 보이며 최초 시도 번호와 시도 횟수를 유지합니다.
3. **대용량 파일 읽기와 DB 보존을 분리합니다.** Windows 공유 폴더의 큰 파일 읽기 지연 때문에 실행 모델을 Linux 전용 볼륨으로 옮겼습니다. 원본 입력 행렬의 읽기 전용 매핑에 `MADV_RANDOM` 힌트를 더하고 전체 검사 후 검증 캐시를 재사용합니다. DB는 초기화하지 않았습니다. 논리 백업 후 당일 범위만 전환했으며, 전환일의 입력이 0개여서 오늘 모델 지문·갱신 메타데이터만 바뀌고 전날 기록은 그대로 보존됐습니다.

## 어디를 수정했나요?

같은 목적의 파일을 기능별로 묶었습니다. 함수·컴포넌트·선택자 이름으로 수정 위치를 찾을 수 있습니다.

| 파일 | 코드 위치 | 추가·변경한 내용과 이유 |
|---|---|---|
| [backend/app/fasttext_bin.py](../../backend/app/fasttext_bin.py) | `FastTextBin`, `_hash`, `_subword_ids`, `get_word_vector`, `close`, `MADV_RANDOM` | 원본 비양자화 형식·행렬 크기를 검사하고 입력 행렬을 읽기 전용 매핑. 비UTF-8 토큰도 원본 바이트로 보존해 단어 ID 유지. 공식 해시·문자 조각 평균과 반복 조각 유지. 무작위 읽기 힌트로 불필요한 순차 읽기 감소. 벡터가 없는 입력과 손상 모델 구분 |
| [backend/app/model_files.py](../../backend/app/model_files.py) | `verify_file`, `remember_verified`, `_record`, `_sha256`, `.verified-model.json` | 전체 SHA-256 검사와 선택적 로컬 검증 캐시. 기대 해시·크기와 파일 식별 정보가 같을 때만 런타임 재사용. 캐시 발행은 전체 검증을 마친 준비 도구만 수행하고 앱은 읽기만 함 |
| [backend/app/similarity.py](../../backend/app/similarity.py) | `SimilarityEngine.__init__`, `vector`, `score`, `rankings`, `supports_oov` | manifest에 따라 fastText/기존 ONNX 경로 선택. fastText는 등록·미등록 입력 모두 원본 `.bin`에서 계산 후 정규화. 파일 크기·SHA-256 검증과 300차원 확인 |
| [backend/app/word_ranks.py](../../backend/app/word_ranks.py) | `cosine_scores`, `WordRankIndex`, `rank_for_score` | 개별 점수와 전체 비교 점수에 같은 float64 누산 사용. 차원·포함/제외 어휘 검증, 원 점수 동률 순위, 미등록 입력의 고정 사전 대비 순위 계산 |
| [backend/app/words.py](../../backend/app/words.py) | `HANGUL_WORD`, `is_allowed_word` | 완성형 한글 1~40자 형식 검사와 사전 포함 여부를 분리. `allow_oov`일 때만 사전 밖 단어 허용. 자모·내부 공백·영문·숫자 입력은 모델 호출 전에 거절 |
| [backend/app/game.py](../../backend/app/game.py) | `model_status`, `state`, `guess`, `ranking` | 모델의 OOV 지원 전달, 서버 기준 어제 정답 조회, 사전 안팎의 실제 점수·순위 응답. 최고 점수가 정확히 같을 때 정답 입력을 우선해 정답의 순위 0 유지 |
| [frontend/src/api.ts](../../frontend/src/api.ts) | `State.yesterday_answer`, `model.supports_oov` | 날짜 아래에 보여 줄 어제 정답과 모델별 입력 안내의 응답 타입 추가 |
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | `formattedDate`, `latestGuess`, `previousGuesses`, `guessRow`, `mutate`, `.model-update-notice` | 서버 날짜 표시, 어제 정답 조건부 표시, 최근 한 행과 나머지 정렬 분리. 중복과 날짜 변경이 함께 오면 날짜 변경 안내 우선. 모델별 입력 안내와 입력 0건에도 정확한 모델 변경 안내 |
| [frontend/src/styles.css](../../frontend/src/styles.css) | `.puzzle-meta`, `.puzzle-date`, `.yesterday-answer`, `.similarity-reference`, `.reference-title`, `.reference-item`, `.latest-guess`, `.previous-guesses` | 날짜·어제 정답 배치, 최근 행 아래 구분선, 기준 점수 세 그룹의 균등 폭. 720px 이하에서 좁은 화면용 배치 |
| [model-manifest.json](../../model-manifest.json), [fastText manifest](../../docs/model-manifest-fasttext.json), [MiniLM manifest](../../docs/model-manifest-minilm.json) | `algorithm`, `revision`, `directory`, `dimension`, `files` | 모델의 고정 버전·계산 방식·파일 크기·해시 기록. 이전 MiniLM 설정도 작은 manifest로 보존. 실제 가중치는 기록이나 저장소에 넣지 않음 |
| [scripts/prepare_model.py](../../scripts/prepare_model.py) | `validate`, `download`, `save_verification`, `--manifest`, `--directory`, `--check` | 후보 manifest 지원, Range 검증과 재개, 전체 크기·해시 검사 후 최종 파일 교체와 선택 캐시 발행. 해시는 공통 모듈에서 8 MiB씩 읽음. `--check`는 캐시를 무시하며 읽기만 함 |
| [scripts/prepare_word_ranks.py](../../scripts/prepare_word_ranks.py) | `validate_progress`, `main`, `excluded_words` | 모델 차원에 맞춘 비교 벡터 준비와 중단 후 재개. 실제 벡터를 만들지 못한 어휘를 명시해 제외하고, 정답 후보 누락·손상 모델은 준비 실패로 처리 |
| [scripts/check_fasttext.py](../../scripts/check_fasttext.py) | 공식 라이브러리 대조 검사 | 임시 소형 모델을 만들어 공식 `fasttext-wheel==0.9.2`와 단어 ID·문자 조각·벡터·코사인을 비교. 공식 라이브러리는 검사 용도이며 앱 실행 의존성으로 추가하지 않음 |
| [scripts/benchmark_model.py](../../scripts/benchmark_model.py) | `memory_snapshot`, `verify_index`, `quality_comparison`, `main` | 실제 등록/OOV 벡터와 독립 코사인 검산. 원 사전과 실제 비교 사전의 해시·포함/제외 수 구분. 현재 RSS·최대 RSS·VMS, 로딩과 계산 경로 기록. 의미 비교 20개와 후보 4,005쌍의 원 점수 분포·80점대 비율 측정 |
| [scripts/smoke_ranking.py](../../scripts/smoke_ranking.py) | fastText 분기와 기존 게임·랭킹 검사 | 사전과 모델 어휘 양쪽에 없는 한글 합성어를 실제 계산하는 검사 추가. 기존 모델에서는 미등록 거절 검사 유지. 격리된 임시 DB 스키마에서 실행 |
| [scripts/check_ui.mjs](../../scripts/check_ui.mjs) | 시험용 API fixture, 날짜·목록·배치 검사 | 기존 16개에 날짜·어제 정답·중복 정렬·320px 배치 등의 검사를 추가해 총 22개. 실제 DB에 쓰지 않는 시험용 응답이며 화면 점수는 모델 품질 평가에 사용하지 않음 |
| [Dockerfile](../../Dockerfile), [compose.yaml](../../compose.yaml) | `MODEL_DIR`, `model_data`, 앱 `volumes`, `healthcheck.start_period` | `/models/fasttext-ko`와 Linux 모델 볼륨 연결. 앱은 읽기 전용 접근, 모델 준비 명령에서만 쓰기 허용. 기존 PostgreSQL 볼륨은 유지 |
| [.env.example](../../.env.example) | 모델 저장 주석, 기존 `MODEL_DIR` 항목 | 호스트 bind 경로를 고르는 환경값 제거. 모델 볼륨과 컨테이너 경로는 Compose에서 정하도록 안내. 실제 `.env`나 비밀값은 기록하지 않음 |
| [GANMANTLE_SPEC.md](../../GANMANTLE_SPEC.md) | 문서 맨 위 현재 사용자 변경 요청, 과거 정리 기록 | 현재 fastText·OOV·날짜·정렬·기록 보존 요구를 우선 기준으로 표시하고 이전 전체 초기화와 구분 |
| [backend/app/dictionary/README.md](../../backend/app/dictionary/README.md) | 현재 입력 처리, 실제 순위 비교 집합 | 입력 허용 목록에서 고정 순위 비교 사전으로 역할 설명 갱신. OOV 실제 벡터와 유효 벡터가 없는 항목만 제외하는 기준 안내 |
| [docs/VALIDATION.md](../../docs/VALIDATION.md) | 013 실제 실행 결과, 측정 조건, 기록 보존 확인 | 이번 검사와 과거 결과 분리. 실제 모델·브라우저·빌드·DB 전환 결과와 Mac/arm64 등 미검증 범위 기록 |
| [README.md](../../README.md), [docs/MODEL.md](../../docs/MODEL.md), [실측 JSON](../../docs/model-benchmark-fasttext-amd64.json) | 현재 상태, 모델 준비·전환·재현 안내, 공개 측정 결과 | 모델의 라이선스·원본 bin 계산·저장 위치·기존 DB 전환 절차, 실제 속도·메모리·품질 예외와 기존 기록 보존 결과 기록 |
| [월별 목록](README.md), [전체 목록](../README.md) | 최신 항목, 폴더 목록, 다음 번호 | 이번 013 기록 연결. 다음 변경 번호를 014로 변경 |

검증 코드는 다음 파일에 나누어 두었습니다. 기존 게임·채팅·랭킹 검사를 유지하면서 새 계산 방식과 경계 사례를 확인합니다.

| 검사 위치 | 이번 변경과 관련된 확인 범위 |
|---|---|
| [test_fasttext_bin.py](../../backend/tests/test_fasttext_bin.py), [test_model_download.py](../../backend/tests/test_model_download.py) | 원본 파일 형식, UTF-8 해시·문자 조각, 잘못된 벡터/손상 모델, 다운로드 크기·해시·이어받기 |
| [test_model_files.py](../../backend/tests/test_model_files.py) | 파일·기대 해시 변경 시 전체 재검, 캐시 손상·누락, 검사 중 변경, 읽기 전용 런타임과 `--check`, 검증·최종 파일 교체 후 캐시 발행 |
| [test_word_rank_preparation.py](../../backend/tests/test_word_rank_preparation.py), [test_word_ranks.py](../../backend/tests/test_word_ranks.py), [test_word_ranks_api.py](../../backend/tests/test_word_ranks_api.py) | 차원·체크포인트·어휘 제외 검증, 같은 누산식, 원 점수 동률과 사전 밖 입력 순위, API 노출 범위 |
| [test_rules.py](../../backend/tests/test_rules.py), [test_ranking.py](../../backend/tests/test_ranking.py) | 서버 날짜·어제 정답·자정, 입력 형식/OOV, 중복과 시도 보존, 실제 동점 랭킹과 정답 우선 |

[test_words.py](../../backend/tests/test_words.py)는 이번에 바꾸지 않은 **기존 회귀 검사**로 전체 pytest에 포함했습니다. 기본 사전 모드의 등록/미등록 처리·정규화·거절 시 기록 보존·코사인 공식을 검사하며, 새 fastText OOV 지원 검사를 이 파일에 추가했다고 기록하지 않습니다.

## 어떤 코드인가요?

아래 코드는 핵심 부분만 발췌했습니다.

### 최근 입력은 한 행, 나머지는 원 점수순

변경 전에는 서버가 반환한 `game.guesses` 전체를 `map`했습니다. 서버 쿼리는 `ORDER BY last_display_order DESC, attempt DESC`였고, 이 반환 순서는 지금도 유지합니다. 변경 후 화면에서만 아래처럼 분리합니다.

```tsx
const latestGuess = game?.guesses[0];
const previousGuesses = game?.guesses.slice(1).sort((a, b) => b.similarity - a.similarity || a.attempt - b.attempt) || [];
```

`latestGuess`는 `.latest-guess` tbody에 한 번 표시하고, `previousGuesses`만 `.previous-guesses`에서 반복합니다. 중복 단어를 서버가 맨 앞으로 이동하면 그 단어가 첫 행을 차지하고, 이전 첫 행은 나머지 점수순 위치로 돌아갑니다. 화면의 소수 둘째 자리 문자열로 정렬하지 않습니다.

기준값 배치는 기존 나열 방식에서 다음 Grid로 바꿨습니다.

```css
/* .similarity-reference 선언 중 일부 */
grid-template-columns: auto repeat(3, minmax(0, 1fr));
```

첫 열은 제목이며 남은 세 열은 같은 폭입니다. 모바일에서는 제목이 전체 열을 차지하고 세 그룹의 순위와 점수를 세로로 배치합니다.

### 날짜와 공개 가능한 어제 정답

이전에는 고정 자정 안내만 표시했습니다. 서버는 이제 오늘의 한국 날짜에서 하루를 뺀 문제만 조회합니다.

```python
yesterday = conn.execute("SELECT answer FROM puzzles WHERE puzzle_date = %s", (day - timedelta(days=1),)).fetchone()
```

응답의 `yesterday_answer`는 해당 행이 없으면 `null`입니다. 과거의 아무 문제로 대체하지 않으며, 오늘 정답을 이 필드에 넣지 않습니다. 브라우저는 `puzzle_date`의 연·월·일을 표시할 뿐 기기 시간으로 오늘을 결정하지 않습니다. 기존 자정 자동 재조회는 유지합니다.

중복 응답의 안내도 날짜 변경 메시지를 덮어쓰지 않도록 조건을 좁혔습니다.

```tsx
// 변경 전
if (next.duplicate) setNotice('이미 입력한 단어예요. 기존 결과를 맨 위로 옮겼어요. 시도 횟수는 그대로예요.');
// 변경 후
if (next.duplicate && !next.date_changed) setNotice('이미 입력한 단어예요. 기존 결과를 맨 위로 옮겼어요. 시도 횟수는 그대로예요.');
```

모델 변경 안내도 실제 전환 범위에 맞췄습니다. 기존의 “오늘 기록의 점수를 다시 계산했어요”는 입력이 0건인 날에도 재계산을 했다고 읽힐 수 있어 다음 문구로 수정하고 UI 검사 문자열도 맞췄습니다.

```text
유사도 모델을 변경했어요. 오늘 기록은 새 모델 점수로 표시하며, 입력과 시도 횟수는 유지돼요.
```

### 원본 벡터와 점수·순위의 같은 계산 기준

이전 MiniLM 경로는 ONNX 추론 또는 준비된 사전 벡터를 사용했습니다. 새 fastText 경로는 원본 `.bin`의 단어·문자 조각 행을 평균해 벡터를 얻으며, 등록 단어도 이 계산을 건너뛰지 않습니다.

```python
# SimilarityEngine.vector의 fastText 경로 중 일부
result = self.fasttext.get_word_vector(text)
norm = np.linalg.norm(result)
# 중간의 벡터 유효성 검사 생략
result = result / norm
```

개별 입력과 전체 비교 사전이 서로 다른 float32 행렬 연산을 사용하면 경계에서 미세한 점수 차이가 생길 수 있어 공통 함수를 사용합니다.

```python
def cosine_scores(vectors, answer):
    """API의 한 행 계산과 전체 순위 계산에 같은 float64 누산 순서를 사용합니다."""
    scores = np.einsum("ij,j->i", vectors, answer, dtype=np.float64, optimize=False) * 100.0
    return np.clip(scores, -100.0, 100.0)
```

미등록 입력의 순위도 `원 점수가 더 높은 비교 단어 수 + 1`입니다. 정답은 별도 0위이고, 공동 순위와 상위 1,000위 표시 규칙은 유지합니다. 점수는 확률이 아니며 분포를 보기 좋게 늘리거나 임의 점수를 넣지 않습니다. 코사인이 같다는 이유만으로 정답 처리하지 않고 정규화한 문자열 일치로 판정합니다.

### 큰 모델의 전체 검사와 읽기 전용 캐시

변경 전에는 앱을 시작할 때마다 모델 전체를 읽어 SHA-256을 검사했습니다. 변경 후에는 `model_files.verify_file()`이 `.verified-model.json`의 기대 SHA·크기와 파일의 `st_size`, `st_dev`, `st_ino`, `st_mtime_ns`, `st_ctime_ns`가 모두 같은 경우에만 전체 검증 결과를 재사용합니다. 캐시가 없거나 정보가 바뀌면 전체 검사로 돌아가며, 크기가 틀리거나 검사 중 파일이 변경되면 실패합니다.

준비 도구의 명시적 검사는 계속 캐시를 무시합니다.

```python
# scripts/prepare_model.py
def validate(path: Path, item: dict) -> bool:
    """명시적 준비/--check/부분 파일 검증은 캐시와 무관하게 전체 SHA를 확인합니다."""
    return verify_file(path, item, use_cache=False)
```

`remember_verified()`는 전체 검사에 성공한 준비 도구만 호출합니다. 새 다운로드는 최종 파일로 rename한 뒤 캐시를 발행합니다. 앱과 `--check`는 캐시를 쓰지 않으며, 캐시 저장 실패도 검증 자체의 성공을 취소하지 않습니다. 캐시는 없어도 되는 산출물이고 다른 기기로 옮겨 파일 식별 정보가 바뀌면 다시 검사합니다. 모델·캐시를 함께 바꿀 수 있는 로컬 관리자의 변조를 막는 장치로 설명하지 않습니다.

실행용 원본 파일에서 최초 전체 SHA 검사 성공을 확인한 뒤, 캐시 메타데이터와 현재 파일의 기대 해시·크기·식별 정보가 일치하는지도 별도로 조회했습니다. 사전 스캔은 비UTF-8 토큰을 버리지 않고 원본 바이트로 유지하며, 입력 매핑에는 지원되는 환경에서 `MADV_RANDOM`을 사용합니다. 힌트가 없는 환경에서도 벡터 계산 결과는 같습니다.

## 어떻게 확인했나요?

아래는 **이번 작업에서 얻은 결과**입니다. 전체 검사와 후속 수정 범위 재검을 별도 실행으로 구분하며 서로 합산하지 않습니다. 과거 012 기록의 검사 결과도 이번 실행으로 합산하지 않습니다.

| 확인 방법 | 현재 확인 결과와 한계 |
|---|---|
| 백엔드 전체 pytest | 선행 전체 검사 **226 passed, 355.46초**, anyio 관련 경고 1개 |
| 손상 모델 오류·8 MiB 해시 읽기·준비 도구 후속 재검 | **83 passed, 44.22초**. 위 전체 검사와 별도 실행이며 합산하지 않음 |
| 검증 캐시·다운로드 후속 재검 | `test_model_files.py` **19개** + `test_model_download.py` **23개**를 함께 실행해 **42 passed, 6.63초**. 위 226개·83개 결과와 중복될 수 있어 합산하지 않음 |
| 원본 사전·mmap 힌트 로더 최종 재검 | **46 passed, 6.55초**. 별도 실행이며 앞선 결과와 합산하지 않음 |
| `scripts/check_fasttext.py` 공식 구현 대조 | 작은 실제 모델 **2개**, 벡터 **26개**, 코사인 **23개** 대조 통과. 이 결과는 로더의 계산 일치 확인이며 한국어 전체 모델의 품질·메모리 측정 결과가 아님 |
| 호스트 프론트엔드 빌드 | `npm.cmd run build` 통과. TypeScript 검사와 배포용 번들 생성 확인 |
| 최종 로컬 Docker 앱 이미지 빌드·실행 | 마지막 안내 문구까지 반영한 이미지 빌드·재기동 성공. **앱·DB 모두 healthy**. 공개 배포는 아님 |
| `scripts/check_ui.mjs` | 마지막 안내 문구 수정 후 **최종 22개 통과**, JavaScript 오류 0개(`2026-09-19T15:32:48.404Z`, 한국 시간 9/20). 자정 중복 안내 우선·최근 행·원 점수 정렬·중복 번호·날짜·어제 정답·desktop/390px/320px 배치 확인. 재기동 직후 탐색 시간 초과 1회가 있었고 서버 준비 확인 후 정상 완료 |
| UI 검사의 데이터 범위 | 테스트 전용 fetch/EventSource fixture를 사용. 실제 DB 쓰기 없음. 시험용 화면 점수는 실제 모델의 유사도 결과가 아님 |
| 한국어 원본 모델 다운로드·전체 해시 검사 | `model.bin` **7,243,669,409바이트** 전체 SHA-256 검사 성공: `a021ebbd5521ca4b3b33425fc25dacd60e4a795041d6f785997800d32a58acd7`. 고정 명세와 일치하고 검증 캐시 메타데이터 일치도 별도 확인 |
| Linux 볼륨의 비교 자료 준비 | **48,978개 유효 / 507개 제외**, 정답 90개 전부 지원. 벡터·단어 목록 합계 **59,382,895바이트**. `MADV_RANDOM` 보완 뒤 1,000개 체크포인트에서 재개한 나머지 **48,485개가 139.9초**이며 전체 준비 시간은 아님 |
| 원본 모델 benchmark | 완료. 로드 **11.792초**, 로드 직후/측정 후 RSS **350.59/360.23 MiB**, 입력 쌍 중앙값/p95 **0.351/0.553ms**, 최초 순위 계산 **56.189ms**. LRU만 비웠고 OS 파일 캐시는 비우지 않음 |
| 원본 모델 독립 계산·실제 게임 smoke | 등록/OOV 원본 벡터·원 코사인·전체 비교 기준·2인 랭킹·정답·중복·재접속 통과. 정답 제외 48,977개 점수의 독립 계산 최대 차이 약 `3.55e-14`. 검사 임시 스키마 정리 완료 |
| 한국어 품질 표본 | **19/20**, 예외는 사랑–좋아하다 **14.2818** < 사랑–망치 **17.2472**. 후보 4,005쌍 범위 **−11.1769~76.9568**, 중앙값 **18.1445**, 80점대 **0%**. 전체 한국어 품질·분포를 보장하는 표본은 아님 |
| 기존 DB 전환·보존 | 논리 백업 완료. KST **9/20 당일 게임 0·입력 0**이어서 당일 모델 지문·갱신 메타데이터만 원자적 전환. **9/19 입력 5·게임 1·사용자 1**의 원 점수·단어·시각·해시 보존. 변경 대상 필드를 제외한 PostgreSQL `public` 스키마 9개 테이블 비교 통과. 문제 2개, 채팅 0개, 변경 이력 3개, 검사 임시 스키마 0개 |
| 실제 API 화면 Chrome 확인 | **최종 6개 통과**(`2026-09-19T15:30:38.103Z`, 한국 시간 9/20). 1600×1000·390×844·320×844에서 실제 날짜·어제 DB 정답·세 기준값 일치와 겹침/잘림 없음 확인. JS 오류 0·API 쓰기 0·검사 프로필 정리 완료. desktop·320px 캡처 육안 확인. 위 fixture UI 22개와 별도 검사 |
| 실제 API 공개 범위 | 모델/OOV/순위 준비 완료 확인. 어제 정답은 DB 값과 같고 오늘 정답 필드 없음. 다른 사람의 추측 단어를 보내지 않음 |
| 실제 Mac / Apple Silicon arm64 | **미실행.** Linux 컨테이너 구성과 플랫폼 독립 계산 경로를 준비했지만 실제 기기의 실행·메모리·속도를 확인한 것은 아님 |
| GitHub 업로드 / 공개 배포 | 미실행. 로컬 개발·검증 범위 |

## 영향과 남은 일

- **DB:** 새 스키마 변경은 없습니다. 이전의 [scripts/recalculate_scores.py](../../scripts/recalculate_scores.py)를 재사용해 논리 백업·당일 전환·전후 비교를 완료했습니다. 전환 시 오늘 입력이 0개였으므로 **과거 5개 점수를 재계산한 것이 아닙니다.** 기존 사용자·게임·입력·채팅과 시각을 보존했습니다. [012의 전체 기록 초기화](19-012-cleanup.md)는 이전에 완료된 별도 작업입니다.
- **모델 저장:** 원본 복구본은 `models/fasttext-ko/`, 실행용 Linux 볼륨은 `ganmantle-v1_model_data`, 앱 경로는 `/models/fasttext-ko`입니다. 준비 도구에서는 같은 볼륨을 `/model-work`에 쓰기 가능하게 연결합니다. 모델 파일·생성 벡터·선택적 검증 캐시는 Git에 넣지 않습니다. 원본 전체 검사·비교 사전 준비·당일 모델 전환을 마쳤습니다. 파일 크기와 VMS를 실제 상주 메모리로 해석하지 않습니다.
- **라이선스:** 한국어 fastText 모델은 manifest에 기록한 CC-BY-SA 3.0 조건을 따릅니다. 원본 형식·해시·문자 조각 계산을 참고한 공식 fastText 코드의 MIT 고지는 새 로더에 남겼습니다. 출처와 배포 시 고려 사항은 [모델 안내](../../docs/MODEL.md)를 확인합니다.
- **입력 한계:** 미등록 단어를 계산할 수 있다는 것은 실제 한국어 단어 여부를 판정한다는 뜻이 아닙니다. 형식이 맞고 문자 조각 벡터가 있는 입력은 계산하며, 자모 등 형식 오류와 벡터를 만들 수 없는 입력은 안내 후 비웁니다. 손상 모델·네트워크 장애는 입력 오류와 구분해 재시도할 입력을 유지합니다.
- **보존한 기능:** 닉네임, 시작, 정답 판정, 시도 수, 중복 재표시, 재접속, 자정 전환, 실제 동점 기준 사용자 랭킹과 시간 표시 조건, 채팅, 860px 본문과 기존 로고·흰색/파란색 UI를 유지합니다.
- **남은 확인:** 실제 Mac/arm64·모바일 기기·Safari·공개 운영 부하는 미검증입니다. 일부 1~2음절 OOV는 원본 5-gram에 문자 조각이 없어 계산할 수 없습니다. 3~6-gram 등 다른 원본 bin을 확보해 품질·라이선스·자원을 검증한 뒤 새로 전환하는 대안은 아직 검사하지 않았습니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
