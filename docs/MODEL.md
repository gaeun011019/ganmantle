# 간맨틀 모델·비교 사전·유사도 순위

현재 모델은 **한국어 fastText `cc.ko.300`의 원본 `.bin`**입니다. 300차원 word/subword 벡터의 실제 코사인 × 100이며, 점수 분포를 임의로 늘리지 않습니다. 꼬맨틀과 모델 파일·전처리·비교 어휘가 모두 같다고 확인한 것은 아니므로 점수와 순위까지 같다고 주장하지 않습니다. 실행 결과는 [검증 기록](VALIDATION.md), 변경 이유는 [013 기록](../CHANGELOG/2026-09/19-013-fasttext-game.md)에 남깁니다.

## 이전에 fastText를 쓰지 않은 이유

변경 전 실제 모델은 `Xenova/paraphrase-multilingual-MiniLM-L12-v2`의 ONNX int8였습니다. `similarity.py`가 tokenizer → ONNX 평균 풀링 → L2 정규화를 수행했고, 준비된 사전 벡터를 입력 점수에도 사용했습니다. [011 기록](../CHANGELOG/2026-09/19-011-similarity-model.md)에는 기존 ONNX 실행과 잠금 의존성 유지, E5 대비 한국어 비교 20개·후보 4,005쌍의 개선이 선택 이유로 적혀 있습니다. **fastText를 실제 측정해서 배제했다는 기록은 없습니다.** 라이선스나 Windows 때문에 불가능했다고 추측하지 않습니다.

MiniLM 명세는 [model-manifest-minilm.json](model-manifest-minilm.json), E5 명세는 [model-manifest-e5.json](model-manifest-e5.json), 과거 비교는 [model-comparison-amd64.json](model-comparison-amd64.json)에 보존합니다. 과거 측정값을 이번 fastText 측정값으로 읽지 않습니다.

## 출처·라이선스·고정 파일

- [fastText 공식 Common Crawl 모델 안내](https://fasttext.cc/docs/en/crawl-vectors.html): Common Crawl/Wikipedia, CBOW, 300차원, 문자 5-gram. 모델 라이선스 **CC-BY-SA 3.0**.
- [Meta의 한국어 모델 고정 커밋](https://huggingface.co/facebook/fasttext-ko-vectors/commit/3dcf803428851b59842f09c42ad3d0930913b83d): 원본 `model.bin` 다운로드 위치.
- 출처 표기: Meta/Facebook fastText, Bojanowski 등의 subword 단어 표현과 Grave 등의 다국어 사전학습 모델. 모델을 재배포·변형할 때 모델 라이선스의 저작자 표시·동일 조건을 확인합니다. 라이브러리/계산 알고리즘 코드는 별도 **MIT**입니다.
- [공식 v0.9.2 소스](https://github.com/facebookresearch/fastText/tree/v0.9.2/src): 파일 형식, UTF-8 hash, subword 평균의 기준. `fasttext_bin.py`에 MIT 고지와 지원 형식을 적었습니다.

| 파일 | 크기 | SHA-256 |
|---|---:|---|
| `model.bin` | 7,243,669,409 bytes (약 6.75 GiB) | `a021ebbd5521ca4b3b33425fc25dacd60e4a795041d6f785997800d32a58acd7` |

[현재 모델 명세](../model-manifest.json)는 모델 커밋·알고리즘·크기·해시를 고정합니다. 준비 도구와 서버 시작 모두 검증합니다. 실행용 `.bin`·비교 벡터·다운로드 `.partial`은 Docker Linux 볼륨 `ganmantle-v1_model_data`에 두고 컨테이너의 `/models`에 연결합니다. 실행 모델은 이 Linux 볼륨에만 두며 Git·Docker 이미지에 포함하지 않습니다. 중복 호스트 복사본과 미사용 MiniLM 실물은 2026-09-26 정리에서 삭제했습니다. 작은 이전 manifest·측정 JSON은 선정 근거 자료로 보존합니다.

이번 원본 파일은 위 **7,243,669,409바이트 전체를 읽어 SHA-256 일치를 확인**했습니다. Linux 볼륨의 순위 자료 준비, 실제 모델 벤치마크·게임 검사, 논리 백업과 기존 기록 보존 전환을 2026년 9월 20일 완료했습니다. 최종 로컬 Docker 앱 이미지 빌드, fixture UI 22개와 실제 API Chrome 6개도 통과했고 앱·DB 컨테이너 모두 healthy입니다. 실제 API의 어제 정답이 DB와 같고 오늘 정답 필드와 다른 사람의 추측 단어가 노출되지 않는 점도 확인했습니다.

## 모델 파일 검증 캐시

[`backend/app/model_files.py`](../backend/app/model_files.py)는 큰 모델을 바꾸지 않았는데도 앱을 시작할 때마다 전체 파일을 다시 읽는 비용을 줄입니다. 선택 파일 `.verified-model.json`에 검증한 파일의 기대 SHA-256·기대 크기와 현재 크기·장치 번호(`st_dev`)·파일 번호(`st_ino`)·수정 시각(`st_mtime_ns`)·상태 변경 시각(`st_ctime_ns`)을 기록합니다. 모두 정확히 같을 때만 이전의 전체 검증 결과를 재사용합니다.

- [`prepare_model.py`](../scripts/prepare_model.py)만 `remember_verified()`로 캐시를 발행합니다. 전체 크기·SHA-256 검사에 성공해야 하며, 다운로드한 파일은 `.partial`을 최종 파일로 바꾸는 rename까지 끝나야 합니다. 이미 있는 파일도 준비 명령을 실행하면 전체 해시를 확인한 뒤 기록합니다.
- 앱의 `verify_file()`은 읽기 전용입니다. 캐시 누락·손상·기대 해시 변경·파일 식별 정보 변경 때는 전체 해시 검사로 돌아가고, 파일 크기가 틀리면 즉시 실패합니다. 전체 검사 도중 파일 정보가 달라져도 실패합니다. 앱은 성공해도 캐시를 새로 쓰거나 수정하지 않습니다.
- **`prepare_model.py --check`는 항상 캐시 없이 전체 파일을 검사하며 읽기만 합니다.** 캐시를 만들거나 갱신하려면 쓰기 가능한 준비 경로에서 `--check` 없는 준비 명령을 사용합니다. 캐시 저장이 실패해도 검증된 모델은 쓸 수 있으며 다음 시작에서 전체 검사를 합니다.
- 상대 모델 경로를 키로 사용하므로 같은 파일을 `/model-work`와 `/models`로 연결해도 재사용할 수 있습니다. 다른 기기로 복사해 파일 식별 정보가 달라지면 다시 검사합니다. 캐시는 필수 모델 자료가 아니며 Git에 넣지 않습니다.

이 캐시는 로컬 파일 변경을 감지해 반복 읽기를 줄이는 장치입니다. 로컬 관리자가 모델과 캐시를 함께 조작하는 것을 막는 암호학적 방어 수단은 아닙니다. 단어 벡터 2,048개를 보관하는 아래 입력 벡터 캐시와도 역할이 다릅니다.

이번 실행 파일의 기대 해시·크기와 파일 식별 정보를 캐시 메타데이터만 읽어 대조해 일치를 확인했습니다. 최초 전체 SHA 검사 성공과 이후 메타데이터 일치 확인을 구분합니다.

[`test_model_files.py`](../backend/tests/test_model_files.py)의 **19개**와 [`test_model_download.py`](../backend/tests/test_model_download.py)의 **23개**를 함께 실행해 **42 passed, 6.63초**를 확인했습니다. 파일 교체·수정, 캐시 손상/누락, 기대 해시 변경, 읽기 전용 실행, 전체 검사 강제와 검증 후 발행을 검사한 별도 실행 결과입니다. 기존 전체 226개·후속 83개 결과와 합산하지 않습니다.

## 메모리와 실행 방식

이 Windows PC의 물리 RAM은 약 7.86 GiB이고 Docker Linux VM에는 약 3.75 GiB가 배정돼 있습니다. 공식 native 로더로 6.75 GiB 파일의 입력/출력 행렬과 사전 전체를 메모리에 올리는 방식은 이 환경에 맞지 않습니다. 이를 이유로 원본을 `.vec` 목록으로 대체하지 않습니다.

`backend/app/fasttext_bin.py`는 **원본 입력 행렬만 읽기 전용 mmap**으로 연결합니다. 단어→ID 사전은 RAM에 두고, 필요한 word/subword 행을 읽어 공식 방식으로 평균합니다. 추론에 사용하지 않는 출력 행렬은 RAM에 적재하지 않습니다. 입력 행렬은 4,000,000×300 float32(4.8 GB), 모델 단어는 2,000,000개입니다. 파일 크기·가상 주소 공간(VMS)은 실제 상주 메모리(RSS)와 다릅니다. 접근한 파일 페이지는 OS 캐시를 사용하므로 모델이 작아지거나 RAM 사용이 0이 되는 방식은 아닙니다.

원본 사전에는 UTF-8로 해석되지 않는 토큰도 있어 사전 키를 원본 바이트로 보존합니다. 해당 토큰을 버리거나 디코딩해서 단어 ID와 행렬의 대응을 바꾸지 않습니다. 입력 행렬에는 지원되는 환경에서 `mmap.MADV_RANDOM` 힌트를 주어 드문드문 읽는 단어 행 주변의 불필요한 순차 읽기를 줄입니다. 힌트가 지원되지 않아도 계산 방식은 같습니다. 이 보완 뒤 로더 검사 **46개가 6.55초에 통과**했습니다.

별도 AI 서버·GPU·PyTorch·native fastText 런타임 의존성은 추가하지 않습니다. 기존 NumPy와 단일 FastAPI worker를 사용합니다. 지원 형식은 검증한 **v12, 비양자화, 비축약, CBOW/skip-gram 단어 벡터**이며 다른 형식은 명시적으로 거절합니다. 공식 fastText 패키지는 작은 모델로 계산 결과를 대조하는 검사에서만 임시 설치합니다.

디스크에는 원본·순위 산출물·다운로드 임시 파일과 빌드 여유 공간이 필요합니다. 이 Windows 환경의 호스트 bind mount에서 큰 모델 파일 읽기 지연을 실측해 실행용 파일을 Docker Linux 볼륨으로 옮겼습니다. 실제 로딩·메모리·계산 시간은 아래 표와 [검증 기록](VALIDATION.md)에 있습니다. 시작 시 다운로드하지 않으며, 위 검증 캐시를 재사용할 수 없으면 7.24 GB 전체의 해시를 검사합니다. 다수 worker/동시 접속 부하를 측정한 수치는 아닙니다.

Windows와 Mac 모두 Linux 컨테이너를 기준으로 합니다. 모델은 x86 전용 실행 파일이 아니며 little-endian float32 데이터입니다. 기존 Python/NumPy의 amd64·arm64 의존성과 다중 아키텍처 Docker 기반을 유지합니다. **실제 Mac·Apple Silicon/arm64 실행은 미검증**이며 Linux/amd64 결과와 구분합니다.

## 실제 입력과 점수

1. 앞뒤 공백 제거·NFC 정규화 후 완성형 한글 1~40자를 검사합니다. 숫자·영문·내부 공백·분리 자모는 안내 후 입력창에서 지우며 시도에 넣지 않습니다.
2. 입력과 정답 각각을 원본 `.bin`으로 계산합니다. 모델 사전에 있는 단어는 word ID와 subword ID, 없는 단어는 subword ID를 사용합니다. 반복·hash 충돌도 공식 평균과 같은 횟수로 합산합니다.
3. L2 정규화한 float32 벡터의 코사인 × 100을 공통 `cosine_scores()`의 float64 누산으로 계산합니다. 전체 순위와 단일 입력이 같은 계산을 사용하고 화면에서만 소수 둘째 자리로 표시합니다.
4. 정답은 점수가 아니라 정규화한 문자열의 일치로 판정합니다. 점수 100처럼 표시되는 오답을 정답 처리하지 않습니다.

**사전 밖 단어도 실제 계산합니다.** 이것은 뜻이 있는 한국어인지 자동 보증한다는 뜻은 아닙니다. 이전의 비교 사전 목록 안에만 입력을 제한하는 규칙은 이번 요청으로 변경했습니다. 원본이 5-gram만 사용하므로 모델에 없는 일부 1~2음절은 subword도 없어 0벡터가 됩니다. 이런 입력과 비정상 벡터는 오류로 안내하고 시도·점수를 저장하지 않습니다. 0점이나 가짜 점수로 대체하지 않습니다.

실제 검사에서 긴 한글 합성어는 비교 사전과 모델 어휘 양쪽에 없어도 원본 문자 조각으로 계산됐습니다. 반면 미등록 오탈자 `산첵`은 유효한 문자 조각이 없어 `vector_unavailable`로 처리했습니다. 짧은 OOV 지원 확대는 3~6-gram 등 다른 범위를 학습한 원본 bin을 별도로 확보해 라이선스·한국어 품질·자원을 검증하고 새 모델 전환을 거치는 대안이 있습니다. 현재 파일의 설정만 바꿔 이미 학습되지 않은 문자 조각 벡터를 만들 수는 없으며, 이 대안은 미검증입니다.

입력 벡터 캐시는 프로세스당 최대 2,048개입니다. **사전 안팎의 새 입력 모두 `.bin` 계산 경로**를 거치며 비교용 `vectors.npy` 조회로 입력을 대체하지 않습니다. 캐시는 이미 실제 계산한 결과를 재사용할 뿐입니다.

## 같은 기준으로 계산하는 단어 순위

[비교 사전](../backend/app/dictionary/README.md)의 원본 49,485개를 같은 모델로 계산해 **48,978개를 준비**했습니다. 유효한 문자 조각이 없는 **507개**는 `word-ranks/manifest.json`의 `excluded_words`에 남겼고, 두 목록이 원본을 빠짐없이 나누는지 검사했습니다. 정답 후보 **90개 모두 지원**합니다. `vectors.npy`와 `words.json` 합계는 **59,382,895바이트**입니다.

`MADV_RANDOM` 보완 뒤 기존 1,000개 체크포인트에서 재개한 **나머지 48,485개 처리에 139.9초**가 걸렸습니다. 이 값은 다운로드·전체 해시 검사·앞선 1,000개 처리와 중단된 실행을 포함한 전체 준비 시간이 아닙니다.

정답 제외 비교 어휘의 점수를 정렬해 기준 1·10·1,000번째 점수를 구합니다. 사전 안팎 입력의 순위는 **해당 입력보다 원 점수가 높은 비교 단어 수 + 1**입니다. 같은 점수는 공동 순위, 정답은 별도 0위입니다. 연속 막대는 단일색으로 채우고 순위 차이는 채움 길이와 숫자로 표시하며, 1,000위를 넘으면 범위 밖으로 표시합니다. 새 미등록 입력이 들어와도 비교 집합이나 다른 단어 순위가 바뀌지 않습니다. 반올림한 표시 점수로 순위를 정하지 않습니다.

사용자 랭킹에는 최고 유사도와 **그 최고 기록의 단어 순위**만 보냅니다. 동점 최고점이면 정답을 우선하고, 다른 사람의 단어는 공개하지 않습니다. 사용자 간 순위는 기존 시도 횟수→정확한 풀이 시간 순서이고, 두 값 모두 같아 실제 공동 순위인 행에서만 시간을 표시합니다.

## 실제 한국어 모델 측정

[실측 JSON](model-benchmark-fasttext-amd64.json)은 한국 시간 2026년 9월 20일, Windows의 WSL2 Linux/amd64·Python 3.12.11·NumPy 2.2.6에서 실행한 결과입니다. 원본 `.bin`을 Linux 모델 볼륨에서 읽었고 검증 캐시의 메타데이터 일치를 확인했습니다. 입력 벡터 LRU만 비웠으며 **OS 파일 캐시는 비우지 않았습니다.** 다운로드·최초 전체 SHA 검사 시간이나 물리적으로 처음 읽는 디스크 성능으로 해석하지 않습니다.

| 측정 | 결과 |
|---|---:|
| import·warmup을 포함한 모델 로드 | 11.792초 |
| 로드 직후 / 벤치마크 후 RSS | 350.59 / 360.23 MiB |
| 최대 RSS 보고값 (`resource.ru_maxrss`) | 359.96 MiB |
| 로드 직후 / 벤치마크 후 VMS | 5,123.36 / 5,156.36 MiB |
| 입력 쌍 계산 중앙값 / p95 (LRU 비움) | 0.351 / 0.553ms |
| 정답별 비교 순위 최초 계산 | 56.189ms |
| 20개 의미 비교에서 관련 단어 점수가 더 높음 | 19개 |
| 정답 후보 90개의 서로 다른 4,005쌍 점수 범위 / 중앙값 | −11.1769~76.9568 / 18.1445 |
| 위 후보 쌍 중 80점대 비율 | 0% |

RSS·최대 RSS는 서로 다른 OS 측정 API의 보고값이고, VMS는 매핑한 주소 공간으로 실제 RAM 사용량이 아닙니다. 최종 메모리에는 비교 사전 검산과 품질 비교도 포함되며 앱 서버나 Docker 전체의 메모리 측정값은 아닙니다.

품질 예외는 `사랑–좋아하다` **14.2818**이 `사랑–망치` **17.2472**보다 낮은 경우입니다. 19/20 결과나 표본의 80점대 0%는 전체 한국어 품질·점수 분포를 보장하지 않습니다. 원 점수를 임의로 늘리거나 변형하지 않았습니다.

독립 계산으로 정답을 제외한 비교 점수 48,977개를 대조했고 최대 차이는 약 `3.55e-14`였습니다. 등록 단어와 긴 OOV의 원본 벡터·코사인, 정답 0위와 1위·1,000위 경계를 확인했습니다. 실제 모델 `smoke_ranking.py`도 OOV·원 코사인·고정 비교 기준·2인 랭킹·정답·중복·재접속을 통과했고 검사 임시 스키마를 정리했습니다. Mac/arm64·실제 모바일·Safari·공개 운영 부하는 아직 검사하지 않았습니다.

## 준비와 재현

[README](../README.md)에서 `setup_env.py`로 최초 설정을 만든 뒤, 프로젝트 루트에서 아래 명령을 실행합니다. 모델 준비 명령은 Windows와 Mac에서 같으며 호스트 Python이 필요하지 않습니다. Compose의 `name: ganmantle-v1`과 `model_data` 볼륨으로 실제 이름 `ganmantle-v1_model_data`를 고정합니다.

```sh
docker compose build app
docker compose run --rm --no-deps --user 0:0 --volume ganmantle-v1_model_data:/model-work:rw app python scripts/prepare_model.py --directory /model-work/fasttext-ko
docker compose run --rm --no-deps --user 0:0 --volume ganmantle-v1_model_data:/model-work:rw app python scripts/prepare_word_ranks.py --directory /model-work/fasttext-ko
docker compose run --rm --no-deps app python scripts/prepare_model.py --directory /models/fasttext-ko --check
docker compose run --rm --no-deps app python scripts/prepare_word_ranks.py --directory /models/fasttext-ko --check
docker compose run --rm --no-deps app python scripts/benchmark_model.py --directory /models/fasttext-ko
```

새 DB는 준비 후 `docker compose up -d`로 시작합니다. 기존 기록이 있으면 아래 모델 전환 절차를 먼저 따릅니다. 준비 중에는 모델 볼륨을 `/model-work:rw`에, 실행 앱에서는 `/models:ro`에 연결합니다. 같은 `/models` 경로에 쓰기 마운트를 겹치면 읽기 전용이 유지되는 것을 실제 검사에서 확인해 경로를 분리했습니다. `.env`의 `MODEL_DIR`는 마운트 선택에 사용하지 않습니다. 컨테이너 내부의 모델 경로는 `/models/fasttext-ko`입니다.

다운로드는 `.partial`과 HTTP Range로 재개합니다. 서버가 Range를 무시하면 전체 파일로 다시 받고, 잘못된 범위·크기·체크섬은 거절합니다. 최종 파일은 검증이 끝난 뒤에만 교체합니다. 순위 준비는 1,000개마다 체크포인트를 기록하고 재실행 시 완료 구간을 확인합니다. 최종 산출물은 `words.json`, `vectors.npy`, `manifest.json`입니다. 준비 중의 제외 표시용 0행은 최종 비교 행렬에 들어가지 않습니다.

다른 모델 명세는 `--manifest`에 **컨테이너에서 읽을 수 있는 JSON 경로**, 준비 명령의 `--directory`에는 `/model-work/모델폴더`를 지정합니다. 현재 지원 경로는 fastText bin과 format 2 순위 자료입니다. `docs/`의 이전 ONNX 명세는 역사 자료이며 현재 코드로 실행하는 복구 설정이 아닙니다. `.env`나 모델 데이터를 이미지에 추가할 필요는 없습니다.

공식 라이브러리 대조는 임시 검사 환경에서 `fasttext-wheel==0.9.2`를 설치한 뒤 `python scripts/check_fasttext.py`를 실행합니다. 작은 실제 모델 2개만 생성하며 7 GB 한국어 모델을 native 로더로 여는 검사가 아닙니다. 결과는 `test-results/fasttext-reference.json`입니다. 원본 한국어 모델의 실제 계산은 별도 benchmark/smoke 검사로 확인합니다.


## 모델 파일 이전

Mac에서는 위 명령으로 같은 모델을 다시 준비하는 방법을 우선 사용합니다. 네트워크 다운로드를 줄이려면 검증된 모델 원본과 순위 자료 4개를 별도 경로로 옮길 수 있습니다. 파일 크기·SHA-256·모델 지문은 새 환경에서 다시 검사해야 합니다. 현재 호스트 `models/` 복사본은 없으며 Docker Linux 모델 볼륨이 실행 원본입니다.

DB 이전은 모델 파일과 별개로 `pg_dump`/`pg_restore`만 사용합니다. `docker compose stop`은 볼륨을 보존하며 `docker compose down -v`는 DB와 모델을 모두 삭제합니다. 실제 Mac·Apple Silicon 실행 검증은 아직 완료하지 않았습니다.

## 기존 기록과 모델 전환

실행 중 앱을 멈추고 `scripts/db.ps1`/`db.sh`로 논리 백업합니다. `scripts/recalculate_scores.py --from-fingerprint 기존지문`으로 확인한 뒤 `--apply`를 실행합니다. 당일 입력 점수와 문제의 모델 지문·갱신 시각을 한 트랜잭션에서 전환하며 정답·입력·최초 시도 번호·최근 순서·시작/완료 시각·사용자·채팅·지난 날짜는 보존합니다. 기존 입력을 새 모델로 계산할 수 없으면 **전체 전환을 취소**합니다. 이전 점수와 새 기준을 섞어 정상 게임처럼 제공하지 않습니다.

이전 MiniLM 로더·실물·format 1 순위 호환은 현재 사용하지 않아 제거했습니다. 다른 모델로 바꾸려면 지원 파일 형식과 품질을 먼저 검증하고 아래의 점수 일괄 전환 절차를 사용합니다. 2026-09-26 전체 기록 초기화는 별도의 사용자 요청이며 일반 업데이트의 기록 보존 원칙과 구분합니다.

프로젝트 루트에서 실행합니다. `OLD_FINGERPRINT`는 대상 DB의 오늘 문제에 저장된 기존 지문으로 바꿉니다. 새 모델 파일·비교 자료를 먼저 준비하고, 실제 입력을 보존할 때만 이 전환 절차를 사용합니다.

```sh
docker compose stop app
# Windows: powershell -ExecutionPolicy Bypass -File scripts/db.ps1 backup
# Mac: sh scripts/db.sh backup
# 논리 백업이 성공한 뒤 진행합니다.
docker compose run --rm --no-deps app python -c "import sys; sys.path.insert(0, 'backend'); from app import db; db.migrate()"
docker compose run --rm --no-deps app python scripts/recalculate_scores.py --from-fingerprint OLD_FINGERPRINT
# dry run의 모델 지문·대상 개수를 확인한 뒤 저장합니다.
docker compose run --rm --no-deps app python scripts/recalculate_scores.py --from-fingerprint OLD_FINGERPRINT --apply
docker compose up -d --no-deps app
```

기본 명령은 저장하지 않는 dry run입니다. 새 지문이면 재계산하지 않으며, 지문 불일치·계산 실패·잠금 충돌·자정 전환 때는 변경 없이 중단합니다.
**과거 전환 기록:** 논리 백업을 완료한 뒤 한국 시간 **2026년 9월 20일**의 문제를 전환했습니다. 당일 게임·입력이 각각 0개여서 모델 지문·갱신 메타데이터만 원자적으로 변경됐습니다. 9월 19일의 사용자 1명·게임 1개·입력 5개는 단어·원 점수·시각을 포함한 해시 비교로 보존을 확인했습니다. 문제는 어제와 오늘 2개, DB 변경 이력은 3개이며, 변경 대상 필드를 제외한 PostgreSQL `public` 스키마 9개 테이블의 비교가 통과했고 검사 임시 스키마는 0개입니다. 과거 입력 5개의 점수를 재계산한 전환이 아닙니다. 당시 기록·백업은 이후 사용자가 요청한 전체 초기화 전의 상태입니다. 현재 UI에는 기술적인 모델 변경 안내를 표시하지 않습니다.
