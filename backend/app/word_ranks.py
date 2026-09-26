"""고정 비교 사전의 실제 벡터로 정답별 상위 1,000위와 기준 점수를 계산합니다."""
from bisect import bisect_right
from functools import lru_cache
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .words import WORDS_PATH, get_words


class WordRanksUnavailableError(RuntimeError):
    pass


def digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def cosine_scores(vectors, answer):
    """API의 한 행 계산과 전체 순위 계산에 같은 float64 누산 순서를 사용합니다."""
    scores = np.einsum("ij,j->i", vectors, answer, dtype=np.float64, optimize=False) * 100.0
    return np.clip(scores, -100.0, 100.0)


class WordRankIndex:
    def __init__(self, directory: Path, fingerprint: str, dimension: int = 300):
        try:
            metadata = json.loads((directory / "manifest.json").read_text(encoding="utf-8"))
            if metadata["format"] != 2 or metadata["model_fingerprint"] != fingerprint:
                raise ValueError("모델 버전 불일치")
            if metadata["dictionary_sha256"] != digest(WORDS_PATH):
                raise ValueError("입력 사전 버전 불일치")
            for name in ("words.json", "vectors.npy"):
                file = directory / name
                item = metadata["files"][name]
                if file.stat().st_size != item["size"] or digest(file) != item["sha256"]:
                    raise ValueError("단어 벡터 파일 검증 실패")
            self.words = json.loads((directory / "words.json").read_text(encoding="utf-8"))
            self.excluded_words = metadata["excluded_words"]
            if (not isinstance(self.words, list) or not isinstance(self.excluded_words, list)
                    or not all(isinstance(word, str) for word in self.words + self.excluded_words)
                    or self.words != sorted(set(self.words))
                    or self.excluded_words != sorted(set(self.excluded_words))
                    or set(self.words) & set(self.excluded_words)
                    or set(self.words) | set(self.excluded_words) != set(get_words())
                    or len(self.words) < 1002):
                raise ValueError("단어 목록 불일치 또는 부족")
            self.vectors = np.load(directory / "vectors.npy", mmap_mode="r", allow_pickle=False)
            if (metadata["count"] != len(self.words) or metadata["dimension"] != dimension
                    or self.vectors.shape != (len(self.words), dimension) or self.vectors.dtype != np.dtype("<f4")):
                raise ValueError("단어 벡터 크기 불일치")
            for start in range(0, len(self.words), 4096):
                block = self.vectors[start:start + 4096]
                if not np.isfinite(block).all() or not np.allclose(np.linalg.norm(block, axis=1), 1, atol=0.0001):
                    raise ValueError("잘못된 단어 벡터")
            self.positions = {word: index for index, word in enumerate(self.words)}
        except (OSError, ValueError, KeyError, TypeError) as exc:
            raise WordRanksUnavailableError(
                "단어 유사도 순위를 준비하지 못했어요. scripts/prepare_word_ranks.py를 실행해 주세요."
            ) from exc

    def vector(self, word: str):
        position = self.positions.get(word)
        return self.vectors[position] if position is not None else None

    @lru_cache(maxsize=4)
    def rankings(self, answer: str) -> dict:
        answer_position = self.positions.get(answer)
        if answer_position is None:
            raise WordRanksUnavailableError("정답의 실제 단어 벡터가 없어 순위를 계산할 수 없어요.")
        answer_vector = self.vectors[answer_position]
        scores = cosine_scores(self.vectors, answer_vector)
        sorted_scores = np.sort(np.delete(scores, answer_position))
        scores[answer_position] = -np.inf  # 정답은 별도 0위이며 유사어 순위에서 제외한다.
        order = np.argsort(-scores, kind="stable")
        ranks = {answer: 0}
        previous = None
        rank = 0
        for position, index in enumerate(order, start=1):
            score = scores[index]
            if previous is None or score != previous:
                rank = position
            if rank > 1000:
                break
            ranks[self.words[index]] = rank
            previous = score
        return {"ranks": ranks, "sorted_scores": sorted_scores, "reference": {
            "vocabulary_size": len(self.words),
            "top1": float(scores[order[0]]), "top10": float(scores[order[9]]),
            "top1000": float(scores[order[999]]),
        }}


def rank_for_score(indexed: dict | None, word: str, score: float | None) -> int | None:
    """사전 밖 입력도 같은 고정 비교 집합에 넣어 원 점수의 공동 순위를 구합니다."""
    if indexed is None or score is None or not math.isfinite(score):
        return None
    ranks = indexed["ranks"]
    if ranks.get(word) == 0:
        return 0
    if "sorted_scores" not in indexed:
        # 실제 모델을 사용하지 않는 기존 규칙 검사 모형과의 호환입니다.
        return ranks.get(word)
    scores = indexed["sorted_scores"]
    rank = len(scores) - bisect_right(scores, score) + 1
    return rank if rank <= 1000 else None
