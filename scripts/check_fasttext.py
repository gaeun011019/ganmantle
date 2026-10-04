"""검증 전용: fasttext-wheel==0.9.2로 만든 작은 .bin과 mmap 계산을 대조합니다.

실행: python scripts/check_fasttext.py
검증 환경에만 설치: python -m pip install fasttext-wheel==0.9.2
결과: test-results/fasttext-reference.json (Git 제외)
현재 한국어 모델·DB는 읽지 않습니다. 임시 학습 파일만 사용하며 가짜 참조로
대체하지 않습니다. 공식 라이브러리가 없거나 다른 버전이면 검사에 실패합니다.
공식 0.9.2의 train_unsupervised는 seed 인자를 받지 않아 기본 seed=0과 thread=1을
사용합니다. 이 검사는 구현 호환성 검사이며 한국어 의미 품질 검사가 아닙니다.
"""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import gc
from importlib import metadata
import json
from pathlib import Path
import platform
import sys
from tempfile import TemporaryDirectory
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
OUTPUT = ROOT / "test-results" / "fasttext-reference.json"
INSTALL = "검증 환경에서 python -m pip install fasttext-wheel==0.9.2를 먼저 실행하세요."


def check_model(fasttext, np, directory: Path, corpus: Path, minn: int, maxn: int) -> dict:
    from app.fasttext_bin import FastTextBin, FastTextVectorError

    settings = dict(
        model="skipgram",
        dim=12,
        bucket=128,
        minn=minn,
        maxn=maxn,
        minCount=1,
        epoch=5,
        thread=1,
        ws=3,
        neg=2,
        verbose=0,
    )
    trained = fasttext.train_unsupervised(input=str(corpus), **settings)
    filename = directory / f"tiny-{minn}-{maxn}.bin"
    trained.save_model(str(filename))
    del trained
    gc.collect()
    if not 0 < filename.stat().st_size < 1024 * 1024:
        raise AssertionError("임시 검증 모델은 1 MiB 미만이어야 합니다.")
    # 경로를 인자로 받지 않습니다. 방금 생성한 작은 임시 모델만 native로 읽습니다.
    native = fasttext.load_model(str(filename))
    seed = getattr(native.f.getArgs(), "seed", None)
    if seed not in (None, 0):
        raise AssertionError("공식 기본 seed=0과 다릅니다.")
    cases = [
        ("IV 한글", "강아지", True),
        ("IV 짧은 단어", "가", True),
        ("IV 반복 글자", "가가가가가", True),
        ("IV UTF-8", "café", True),
        ("IV 4바이트 UTF-8", "😀", True),
        ("문장 끝 토큰", "</s>", True),
        ("OOV 한글", "초록구름산책냥", False),
        ("OOV 혼합 UTF-8", "café한국어😀", False),
        ("OOV NFD", unicodedata.normalize("NFD", "가나다"), False),
        ("OOV 반복 subword", "가" * 24, False),
        (
            "OOV 서로 다른 subword의 bucket 충돌",
            "".join(chr(0xAC00 + i) for i in range(160)),
            False,
        ),
        ("OOV 1음절", "쀍", False),
        ("OOV 2음절", "쀍뾱", False),
    ]
    report = {
        "settings": settings,
        "seed_from_native_args": seed,
        "file_bytes": filename.stat().st_size,
        "vectors": [],
        "cosines": [],
    }
    vector_pairs = {}
    with closing(FastTextBin(filename)) as mapped:
        assert mapped.dimension == 12 and mapped.bucket == 128
        assert (mapped.minn, mapped.maxn) == (minn, maxn)
        report["vocabulary_size"] = mapped.nwords
        for label, word, expected_known in cases:
            native_id = native.get_word_id(word)
            assert (native_id >= 0) == expected_known, f"참조 IV/OOV 분류가 다릅니다: {label}"
            assert mapped.word_id(word) == native_id, f"word ID가 다릅니다: {label}"
            subwords, native_ids = native.get_subwords(word)
            ids = [int(value) for value in native_ids]
            assert mapped._subword_ids(word) == ids, f"subword 순서·hash가 다릅니다: {label}"
            reference = np.asarray(native.get_word_vector(word), dtype=np.float32)
            assert reference.shape == (12,) and np.isfinite(reference).all(), label
            row = {
                "case": label,
                "in_vocabulary": expected_known,
                "subwords": len(ids),
                "repeated_ids": len(ids) - len(set(ids)),
            }
            # 작은 학습 모델에는 아직 학습되지 않은 0값 bucket도 있습니다.
            # NFD 등도 실제 native 결과가 0이면 같은 방식으로 명시 거절해야 합니다.
            if minn == 5 and label in ("OOV 1음절", "OOV 2음절"):
                assert not ids and not np.any(reference), (
                    f"5글자 ngram 미만 OOV는 0이어야 합니다: {label}"
                )
                row["zero_required_by_length"] = True
            if not np.any(reference):
                try:
                    mapped.get_word_vector(word)
                except FastTextVectorError:
                    row["zero_vector_rejected"] = True
                else:
                    raise AssertionError(
                        f"공식 0벡터 입력을 명시적으로 거절하지 않았습니다: {label}"
                    )
            else:
                actual = mapped.get_word_vector(word)
                assert actual.dtype == np.float32 and actual.shape == (12,), label
                np.testing.assert_allclose(actual, reference, rtol=1e-6, atol=1e-6, err_msg=label)
                row["max_absolute_difference"] = float(np.max(np.abs(actual - reference)))
                vector_pairs[label] = (reference, actual)
            if label == "OOV 반복 subword":
                assert row["repeated_ids"] > 0, (
                    "반복 subword 검사 입력이 반복 ID를 만들지 않았습니다."
                )
            if label == "OOV 서로 다른 subword의 bucket 충돌":
                seen = {}
                collision = False
                for text, index in zip(subwords, ids):
                    if index in seen and seen[index] != text:
                        collision = True
                    seen[index] = text
                assert collision, "서로 다른 subword의 실제 hash 충돌을 만들지 못했습니다."
                row["distinct_subwords_collide"] = True
            report["vectors"].append(row)

        def cosine100(left, right):
            # 양쪽 벡터 각각을 같은 독립 공식으로 정규화하여 점수까지 비교합니다.
            left = left.astype(np.float64)
            right = right.astype(np.float64)
            return float(np.dot(left / np.linalg.norm(left), right / np.linalg.norm(right)) * 100)

        anchor_reference, anchor_actual = vector_pairs["IV 한글"]
        for label, (reference, actual) in vector_pairs.items():
            expected_score = cosine100(anchor_reference, reference)
            actual_score = cosine100(anchor_actual, actual)
            np.testing.assert_allclose(
                actual_score, expected_score, rtol=1e-6, atol=1e-6, err_msg=label
            )
            report["cosines"].append(
                {
                    "case": label,
                    "reference": expected_score,
                    "mapped": actual_score,
                    "difference": abs(actual_score - expected_score),
                }
            )
    del native
    gc.collect()
    report["passed"] = True
    return report


def main() -> int:
    started = time.perf_counter()
    report = {
        "passed": False,
        "test_only": True,
        "real_native_reference": True,
        "production_model_loaded": False,
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(),
        "machine": platform.machine(),
        "system": platform.platform(),
        "rtol": 1e-6,
        "atol": 1e-6,
        "models": [],
    }
    try:
        try:
            wheel_version = metadata.version("fasttext-wheel")
            import fasttext
        except (metadata.PackageNotFoundError, ImportError) as exc:
            raise RuntimeError(INSTALL) from exc
        if wheel_version != "0.9.2":
            raise RuntimeError(
                f"fasttext-wheel==0.9.2가 필요합니다(현재 {wheel_version}). {INSTALL}"
            )
        import numpy as np

        report["versions"] = {"fasttext-wheel": wheel_version, "numpy": np.__version__}
        with TemporaryDirectory(prefix="ganmantle-fasttext-reference-") as temporary:
            directory = Path(temporary)
            corpus = directory / "tiny-corpus.txt"
            lines = [
                "강아지 개 산책 걷다 여행 바다 하늘 가",
                "한글 단어 유사도 게임 테스트 가나다 가가가가가",
                "café naïve apple banana 😀 🙂 한국어 영어",
            ]
            corpus.write_text("\n".join(lines * 40) + "\n", encoding="utf-8")
            for minn, maxn in ((3, 6), (5, 5)):
                report["models"].append(check_model(fasttext, np, directory, corpus, minn, maxn))
        report["temporary_files_removed"] = True
        report["passed"] = True
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
    report["seconds"] = round(time.perf_counter() - started, 3)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    summary = {
        "passed": report["passed"],
        "models": len(report["models"]),
        "vector_cases": sum(len(model["vectors"]) for model in report["models"]),
        "cosine_cases": sum(len(model["cosines"]) for model in report["models"]),
        "seconds": report["seconds"],
        "result": "test-results/fasttext-reference.json",
    }
    if "error" in report:
        summary["error"] = report["error"]
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
