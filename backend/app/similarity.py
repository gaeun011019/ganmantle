"""고정한 로컬 모델의 실제 벡터를 정규화해 코사인 × 100을 계산합니다."""

from __future__ import annotations
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path
import time
import unicodedata

from .model_files import verify_file

ROOT = Path(__file__).resolve().parents[2]
# Docker에서는 backend/app 대신 app/에 배치할 수도 있으므로 manifest 위치로 결정한다.
if not (ROOT / "model-manifest.json").exists():
    ROOT = Path(__file__).resolve().parents[1]


class ModelUnavailableError(RuntimeError):
    """모델 누락/검증 실패/계산 불가. 호출자는 시도를 기록하지 않는다."""


class VectorUnavailableError(ModelUnavailableError):
    """모델에 이 단어를 구성할 word/subword 벡터가 없습니다."""


class SimilarityEngine:
    def __init__(
        self,
        manifest_path: Path | None = None,
        directory: Path | None = None,
        *,
        require_ranks: bool = False,
    ) -> None:
        self.ready = False
        self.error = None
        self.name = "간맨틀 임베딩 모델"
        self.fingerprint = "unavailable"
        self.load_seconds = 0.0
        self._rank_index = None
        self.supports_oov = True
        self.dimension = 300
        started = time.perf_counter()
        try:
            manifest = json.loads(
                (manifest_path or ROOT / "model-manifest.json").read_text(encoding="utf-8-sig")
            )
            if manifest["algorithm"] != "fasttext-bin-subword-mean-l2-cosine100-v1":
                raise ModelUnavailableError("fastText .bin 모델 명세가 필요합니다.")
            self.name = manifest.get("display_name", manifest["model_id"] + " · fastText")
            self.fingerprint = hashlib.sha256(
                json.dumps(
                    {
                        "revision": manifest["revision"],
                        "algorithm": manifest["algorithm"],
                        "files": manifest["files"],
                    },
                    sort_keys=True,
                ).encode()
            ).hexdigest()
            directory = Path(directory or os.getenv("MODEL_DIR", str(ROOT / manifest["directory"])))
            for item in manifest["files"]:
                path = directory / item["path"]
                if not path.is_file():
                    raise ModelUnavailableError(
                        "모델 파일이 없습니다. scripts/prepare_model.py를 실행하세요."
                    )
                if path.stat().st_size != item["size"]:
                    raise ModelUnavailableError("모델 파일 크기 검증 실패. 모델을 다시 준비하세요.")
                # 같은 로컬 파일의 검증 캐시만 재사용하며, 앱은 캐시를 쓰지 않습니다.
                if not verify_file(path, item):
                    raise ModelUnavailableError("모델 SHA-256 검증 실패. 모델을 다시 준비하세요.")
            import numpy as np

            self._np = np
            from .fasttext_bin import FastTextBin

            self.fasttext = FastTextBin(directory / "model.bin")
            self.dimension = self.fasttext.dimension
            if self.dimension != manifest["dimension"]:
                raise ModelUnavailableError("fastText 모델 차원이 명세와 다릅니다.")
            self.ready = True
            # 실제 계산 경로를 시작 때 확인합니다.
            self.vector("준비")
            if require_ranks:
                from .word_ranks import WordRankIndex

                self._rank_index = WordRankIndex(
                    directory / "word-ranks", self.fingerprint, dimension=self.dimension
                )
                if self._rank_index.vectors.shape[1] != self.dimension:
                    raise ModelUnavailableError("모델과 비교 단어 벡터의 차원이 다릅니다.")
                self.vector.cache_clear()
        except Exception as exc:
            self.ready = False
            self.error = str(exc) or "모델을 준비하지 못했습니다."
        self.load_seconds = time.perf_counter() - started

    @lru_cache(maxsize=2048)
    def vector(self, text: str):
        """fastText는 사전 안팎 입력 모두 원본 .bin의 word/subword 행에서 계산합니다."""
        if not self.ready:
            raise ModelUnavailableError(self.error or "모델 준비가 필요합니다.")
        np = self._np
        text = unicodedata.normalize("NFC", text.strip())
        if not text:
            raise ModelUnavailableError("빈 입력은 계산할 수 없습니다.")
        from .fasttext_bin import FastTextVectorError

        try:
            result = self.fasttext.get_word_vector(text)
        except FastTextVectorError as exc:
            raise VectorUnavailableError(
                "이 단어를 계산할 서브워드가 없어요. 다른 한국어 단어를 입력해 주세요."
            ) from exc
        norm = np.linalg.norm(result)
        if not np.isfinite(result).all() or not np.isfinite(norm):
            raise ModelUnavailableError("모델이 유한한 벡터를 만들지 못했어요.")
        if norm <= 0:
            raise VectorUnavailableError("이 단어의 유효한 벡터를 만들 수 없어요.")
        result = result / norm
        result.setflags(write=False)
        return result

    def score(self, word: str, answer: str) -> float:
        # 정답 판정은 game.py의 NFC 문자열 일치로만 한다. 점수로 판정하지 않는다.
        if not self.ready:
            raise ModelUnavailableError(self.error or "모델 준비가 필요합니다.")
        from .word_ranks import cosine_scores

        return float(cosine_scores(self.vector(word).reshape(1, -1), self.vector(answer))[0])

    def rankings(self, answer: str) -> dict:
        if not self.ready or self._rank_index is None:
            raise ModelUnavailableError(self.error or "단어 유사도 순위 자료를 준비해 주세요.")
        from .word_ranks import WordRanksUnavailableError

        try:
            return self._rank_index.rankings(unicodedata.normalize("NFC", answer.strip()))
        except WordRanksUnavailableError as exc:
            raise ModelUnavailableError(
                "단어 유사도 순위를 계산하지 못했어요. 순위 자료를 다시 준비해 주세요."
            ) from exc


@lru_cache(maxsize=1)
def get_engine() -> SimilarityEngine:
    return SimilarityEngine(require_ranks=True)
