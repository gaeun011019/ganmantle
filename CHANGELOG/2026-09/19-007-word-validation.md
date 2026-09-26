# 2026-09-19 — 입력 단어 검사와 유사도 단위 표시

- 기록 ID: 2026-09-19-007
- 분야: 게임 / 화면 / 사전 / 문서
- 유형: 추가 / 수정
- 구현 상태: 완료 (브라우저 직접 조작은 미검증)
- 관련 커밋: 미기록

## 무엇이 달라졌나요?

사용자가 무작위 입력에도 높은 유사도가 표시되는 문제를 제기하고, 허용하지 않는 단어는 안내 후 입력창에서 지워 달라고 요청했습니다. 초기 명세의 미등록 입력 허용보다 이번 요청을 우선했습니다. `ganmantle-v1` 안에서 수정했으며 모델·점수 계산식·당일 정답·기존 기록은 교체하지 않았습니다.

| 변경 전 | 변경 후 |
|---|---|
| 길이와 제어 문자만 검사한 뒤 임의 문자열도 임베딩 | 한국어 입력 사전에 있는 표제어만 모델로 전달 |
| 사전 밖 조합도 점수와 시도 기록 생성 | `unrecognized_word` 400 안내, 추론·기록·횟수 추가 없음 |
| 오류 시 입력 내용 유지, 연결 오류 안내와 같은 표시 | 단어 거절일 때 입력을 비우고 안내·입력 포커스. 연결/모델/사전 준비 오류는 입력 유지 |
| 표 제목 `유사도` | `유사도 (%)`, 코사인 × 100과 정답 확률이 아니라는 안내 |
| 입력 허용 사전 없음 | 정답 후보 90개와 별도로 고정한 한국어 표제어 49,485개 |

현재 E5 모델은 관련 없는 단어도 높은 코사인을 가질 수 있습니다. [공식 FAQ](https://huggingface.co/intfloat/multilingual-e5-small#faq)는 0.7~1.0 부근에 몰리는 학습 특성을 설명합니다. 기존 계산은 L2 정규화 벡터의 내적 × 100으로 맞았으며, 이번 변경으로 점수를 늘리거나 빼서 구간을 바꾸지 않았습니다. 입력 제한은 점수 분포 자체를 개선하는 모델 교체가 아닙니다.

## 어디를 수정했나요?

| 파일 | 코드 위치 | 역할과 변경 |
|---|---|---|
| [backend/app/words.py](../../backend/app/words.py) | `get_words()`, `is_allowed_word()` | 한글 형태·등록 여부 검사, 사전 SHA-256/단어 수/형식 검사, 메모리 캐시 |
| [backend/app/game.py](../../backend/app/game.py) | `guess()` | 중복 처리·모델 호출 전에 사전 검사. 사전 준비 실패는 503 |
| [backend/app/dictionary/](../../backend/app/dictionary/README.md) | `words.txt`, `source.yaml`, `manifest.json`, 고지·GPL 전문 | 허용 목록과 고정 원본·변환 규칙·라이선스를 함께 보관 |
| [scripts/prepare_dictionary.py](../../scripts/prepare_dictionary.py) | `build()`, `--check` | 외부 접속 없이 원본에서 정적 목록 재생성, 정답 후보 포함 여부 검사 |
| [frontend/src/App.tsx](../../frontend/src/App.tsx) | `mutate()`, `wordNotice`, `focusAfterReject`, 도움말·표 제목 | 단어 오류 전용 안내, 자동 비움·포커스 복귀, `%` 설명 |
| [backend/tests/test_words.py](../../backend/tests/test_words.py) | 신규 검사 26사례 | 사전·정규화·모델 미호출·기록 불변·사전 손상·기존 미등록 기록·코사인 공식 |
| [backend/tests/test_rules.py](../../backend/tests/test_rules.py), [test_ranking.py](../../backend/tests/test_ranking.py) | 기존 경계 검사 입력 | 테스트 모형 전용 단어를 등록된 일상 단어로 바꾸고 미등록 입력 기대 결과 변경 |
| [scripts/smoke_ranking.py](../../scripts/smoke_ranking.py) | `run()` | 실제 모델 캐시 호출 수 불변, 별도로 계산한 코사인 값과 API 점수 비교 |
| `scripts/smoke_test.py` | `before` | 이전 OOV 허용 입력을 등록된 오답 두 개로 대체하여 새 정책에 맞춤 |
| [GANMANTLE_SPEC.md](../../GANMANTLE_SPEC.md), [README.md](../../README.md), [docs/MODEL.md](../../docs/MODEL.md), [docs/VALIDATION.md](../../docs/VALIDATION.md) | 사용자 변경 합의·입력 규칙·검증 범위 | 초기 명세와 현재 정책, 모델 능력과 게임 허용 입력, 이번 검사와 이전 검사 구분 |
| [전체 목록](../README.md), [월별 목록](README.md), [이 기록](19-007-word-validation.md) | 변경 이력 | 수정 위치와 결과 연결 |

`similarity.py`, 모델 manifest, 모델 파일, 의존성 잠금 파일, `.env`, DB migration은 변경하지 않았습니다.

## 어떤 코드인가요?

기존에는 아래 형식 검사 다음에 바로 게임/중복/모델 처리를 했습니다.

```python
if not 1 <= len(word) <= 40 or not valid_text(word):
    raise GameError("invalid_word", "단어는 제어 문자 없이 1~40자로 입력해 주세요.")
```

지금은 게임 시작 여부를 확인한 뒤, 중복 재표시와 모델 호출 전에 다음 검사를 추가합니다(일부 발췌).

```python
allowed = is_allowed_word(word)
if not allowed:
    raise GameError("unrecognized_word", "입력할 수 없는 단어예요. 사전에 등록된 한국어 단어를 입력해 주세요.")
```

화면의 `mutate()`는 단어 요청의 명시적 거절에만 자동 비움을 적용합니다(일부 발췌).

```tsx
if (path === '/guesses' && cause instanceof ApiError &&
    ['invalid_word', 'unrecognized_word'].includes(cause.code)) {
  setWord('');
  setWordNotice(cause.message);
  focusAfterReject.current = true;
}
```

일반 상태 폴링은 `wordNotice`를 지우지 않으므로 거절 안내가 곧바로 사라지지 않습니다. 포커스는 `busy`가 해제된 후 복구합니다. 닉네임 오류나 서버 연결 실패에는 이 처리를 적용하지 않습니다.

## 어떻게 확인했나요?

| 이번 검사 | 결과 |
|---|---|
| Docker `tsc --noEmit` + Vite 빌드 | 통과 |
| 실제 PostgreSQL 임시 스키마에서 `pytest -q -p no:cacheprovider backend/tests` | **43 passed**, 104.04초. 기존 17개 + 신규 26사례 |
| `prepare_dictionary.py --check` | 고정 원본에서 재생성 결과 일치, **49,485개 / 514,758바이트**, 정답 후보 90개 포함 |
| 새 이미지의 `scripts/smoke_ranking.py` | 실제 모델: 미등록 입력의 벡터 호출/기록 없음, 코사인×100 독립 대조(오차 0.0001 이내), 두 익명 사용자·랭킹·재접속·중복 검사 통과 |
| `docker compose up -d --no-deps app`, HTTP 확인 | 앱 교체 완료. health·DB·모델 정상, 화면 200, 새 화면 자산의 입력 거절 처리 확인 |
| 문서 검사 | 문서 8개의 로컬 링크 54개와 UTF-8 확인 |
| 브라우저 직접 입력·자동 비움·포커스·모바일 화면 | 미검증. 제어 도구에 연결된 브라우저가 없음. 코드 검토와 TypeScript 빌드는 통과 |

규칙 검사는 자모·무작위 한글·영문·숫자·문장·emoji 거절, 모델 호출 0회, 게임/랭킹/DB 원본 불변, 정상 단어와 NFD 입력, 사전 누락·체크섬·JSON·개수·형식 오류, 기존 잘못된 입력의 보존과 재제출 차단을 포함합니다. 코사인 공식은 정규화된 직교·동일·반대 벡터로 각각 0·100·−100을 확인합니다. 실제 모델 검사는 검증 문서에서 구분합니다. 테스트 경고 1개는 Starlette의 anyio 별칭 사용 중단 예정 경고입니다.

## 영향과 남은 일

- 표제어 기준이므로 `반가워`는 거절하고 `반갑다`를 허용합니다. `아` 같은 실제 한 글자 단어는 허용합니다. 사전에 누락된 신조어·고유명사도 거절될 수 있습니다.
- 사전 데이터는 hunspell-dict-ko **0.7.94**, 고정 커밋 `07c339220d92ce06ccbae62a345c7314a7e724ce`에서 추출했으며 원본·GPL-3.0-or-later 고지·전문·추출 방법을 동봉했습니다. 실행 중 인터넷이나 추가 서비스는 필요 없습니다.
- 기존 DB 입력과 점수는 삭제·재계산하지 않습니다. 새 요청부터 변경 규칙을 적용하며 이전 미등록 입력을 다시 제출해도 원래 행을 이동하지 않습니다.
- 실행은 `docker compose up -d --build` 후 새로고침입니다. 모델과 DB를 다시 준비할 필요는 없습니다.
- 현재 모델의 점수 밀집과 한국어 단어 의미 구분 한계는 남습니다. 모델 교체는 품질 비교와 날짜별 지문 호환을 별도로 검토해야 합니다.
- 실제 Mac·arm64 실행과 브라우저 직접 조작은 미검증입니다. GitHub 업로드·공개 배포는 하지 않았습니다.

> 후속 정리(2026-09-19): `scripts/smoke_test.py`는 [012 정리 기록](19-012-cleanup.md)에 따라 삭제했습니다. 이 문서의 실행 사실은 당시 기록으로 보존하며, 현재 실제 모델·DB 통합 검사 도구는 `scripts/smoke_ranking.py`입니다.

[월별 목록](README.md) · [전체 변경 기록](../README.md)
