"""간맨틀: 실제 모델의 한국어 품질/미등록 입력/메모리/지연을 측정해 JSON으로 남긴다."""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import statistics
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

# 점수를 보고 고른 쌍이 아니라 생활 주제별로 미리 고정한 소규모 검토용 쌍입니다.
EXAMPLES = [
    ("강아지", "개", "책상"), ("산책", "걷다", "냉장고"),
    ("행복", "기쁘다", "볼트"), ("아름답다", "예쁘다", "숟가락"),
    ("고양이", "강아지", "기차"), ("사과", "배", "모니터"),
    ("바다", "파도", "연필"), ("학교", "학생", "냉장고"),
    ("책", "독서", "비행기"), ("음악", "노래", "신발"),
    ("자동차", "버스", "눈물"), ("비", "우산", "컴퓨터"),
    ("병원", "의사", "구름"), ("커피", "차", "축구"),
    ("사랑", "좋아하다", "망치"), ("빠르다", "신속하다", "소금"),
    ("슬프다", "울다", "자동차"), ("먹다", "마시다", "창문"),
    ("춥다", "차갑다", "연필"), ("잠", "꿈", "키보드"),
]


def memory_snapshot(process) -> dict:
    """현재 RSS, 프로세스 시작 이후 최대 RSS, 가상 메모리를 구분합니다."""
    info = process.memory_info()
    peak = getattr(info, "peak_rss", getattr(info, "peak_wset", None))
    source = "psutil peak working set" if peak is not None else None
    if peak is None and (sys.platform.startswith("linux") or sys.platform == "darwin"):
        import resource
        peak = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        peak *= 1 if sys.platform == "darwin" else 1024
        source = "resource.ru_maxrss (macOS bytes / Linux KiB)"
    return {"rss_mb": round(info.rss / 1024**2, 2), "vms_mb": round(info.vms / 1024**2, 2),
            "max_rss_mb": round(peak / 1024**2, 2) if peak is not None else None,
            "max_rss_source": source}


def verify_index(engine, indexed: dict, sample_words: list[str]) -> dict:
    """같은 비교 사전의 전체 점수와 실제 표본 입력의 순위를 별도로 검산합니다."""
    import hashlib
    import numpy as np
    from app.word_ranks import rank_for_score
    from app.words import WORDS_PATH, get_words

    index = engine._rank_index
    dictionary = get_words()
    included, excluded = set(index.words), set(index.excluded_words)
    if (index.words != sorted(included) or index.excluded_words != sorted(excluded)
            or included & excluded or included | excluded != dictionary
            or len(included) + len(excluded) != len(dictionary)):
        raise SystemExit("비교 단어와 제외 단어가 고정 사전을 중복 없이 나누지 않습니다.")
    answer = "산책"  # 실제 오늘 정답을 조회하지 않는 공개된 고정 예제입니다.
    answer_vector = engine.vector(answer).astype(np.float64)
    independent = np.empty(len(index.words), dtype=np.float64)
    # 한꺼번에 float64 행렬을 복사하지 않아 검사 자체의 메모리 증가를 제한합니다.
    for start in range(0, len(index.words), 256):
        block = index.vectors[start:start + 256].astype(np.float64)
        independent[start:start + len(block)] = np.clip(block @ answer_vector * 100.0, -100.0, 100.0)
    independent = np.sort(np.delete(independent, index.positions[answer]))
    scores = np.asarray(indexed["sorted_scores"], dtype=np.float64)
    if len(scores) != len(index.words) - 1 or not np.isfinite(scores).all() or np.any(scores[1:] < scores[:-1]):
        raise SystemExit("정답을 제외한 비교 점수 집합이 잘못되었습니다.")
    if not np.allclose(independent, scores, rtol=0, atol=1e-10):
        raise SystemExit("전체 비교 사전의 독립 float64 점수가 순위 점수와 다릅니다.")
    for key, offset in (("top1", 1), ("top10", 10), ("top1000", 1000)):
        if indexed["reference"][key] != float(scores[-offset]):
            raise SystemExit("실제 순위 기준값이 전체 비교 점수와 다릅니다.")

    boundary_words = [next(word for word, rank in indexed["ranks"].items() if rank == 1)]
    last_rank = max(indexed["ranks"].values())
    boundary_words.append(next(word for word, rank in indexed["ranks"].items() if rank == last_rank))
    checked = []
    for word in dict.fromkeys([answer, *sample_words, *boundary_words]):
        score = engine.score(word, answer)
        actual = rank_for_score(indexed, word, score)
        expected = 0 if word == answer else int(np.count_nonzero(scores > score)) + 1
        expected = expected if expected <= 1000 else None
        if actual != expected:
            raise SystemExit("실제 입력 점수의 독립 순위 계산이 API 순위와 다릅니다.")
        if word in index.positions and indexed["ranks"].get(word) != expected:
            raise SystemExit("등록 단어의 입력 순위가 준비된 전체 어휘 순위와 다릅니다.")
        checked.append({"word": word, "cosine_times_100": score, "rank": actual,
                        "in_comparison_dictionary": word in index.positions})
    return {"source_dictionary_sha256": hashlib.sha256(WORDS_PATH.read_bytes()).hexdigest(),
            "source_dictionary_count": len(dictionary), "comparison_dictionary_count": len(included),
            "comparison_dictionary_sha256": hashlib.sha256(("\n".join(index.words) + "\n").encode("utf-8")).hexdigest(),
            "excluded_count": len(excluded), "excluded_words": index.excluded_words,
            "compared_scores": len(scores), "maximum_independent_score_error": float(np.max(np.abs(independent - scores))),
            "rank_samples": checked}


def quality_comparison(engine) -> dict:
    """이미 로드한 모델로 고정 20개 비교와 공개된 정답 후보 90개의 전체 쌍을 측정합니다."""
    import numpy as np
    from app.word_ranks import cosine_scores

    began = time.perf_counter()
    triples = []
    gaps = []
    for answer, related, unrelated in EXAMPLES:
        near, far = engine.score(related, answer), engine.score(unrelated, answer)
        if not all(math.isfinite(value) and -100 <= value <= 100 for value in (near, far)):
            raise RuntimeError("20개 의미 비교에서 유효한 실제 모델 점수를 계산하지 못했습니다.")
        gaps.append(near - far)
        triples.append({"anchor": answer, "related": related, "unrelated": unrelated,
                        "related_score": round(near, 4), "unrelated_score": round(far, 4),
                        "gap": round(near - far, 4), "related_higher": near > far})
    answers = sorted({line.strip() for line in (ROOT / "backend/app/answers.txt").read_text(encoding="utf-8-sig").splitlines()
                      if line.strip() and not line.lstrip().startswith("#")})
    if len(EXAMPLES) != 20 or len(answers) != 90:
        raise RuntimeError("고정 품질 비교 20개 또는 공개 정답 후보 90개의 구성이 바뀌었습니다.")
    # DB의 오늘 정답은 읽지 않습니다. 모든 후보 벡터를 같은 엔진에서 실제 계산합니다.
    vectors = np.stack([engine.vector(word) for word in answers])
    if vectors.shape != (90, engine.dimension) or not np.isfinite(vectors).all():
        raise RuntimeError("공개 정답 후보 벡터의 개수·차원·유한성 검사에 실패했습니다.")
    # float32 행렬곱으로 별도 근사하지 않고 API/순위와 같은 float64 누산을 사용합니다.
    similarities = np.column_stack([cosine_scores(vectors, answer_vector) for answer_vector in vectors])
    scores = similarities[np.triu_indices(len(answers), k=1)]
    if (len(scores) != 4005 or not np.isfinite(scores).all()
            or not np.allclose(np.diag(similarities), 100, rtol=0, atol=0.0001)
            or float(similarities[0, 1]) != engine.score(answers[0], answers[1])):
        raise RuntimeError("90개 후보 전체 쌍 점수와 실제 API 계산의 일치 검사에 실패했습니다.")
    return {
        "comparison_count": len(triples),
        "related_higher_count": sum(row["related_higher"] for row in triples),
        "median_related_gap": round(float(np.median(gaps)), 4),
        "triples": triples,
        "all_answer_pairs": {
            "answers": len(answers), "pairs": len(scores),
            "percentiles": {str(p): round(float(np.percentile(scores, p)), 4)
                            for p in (0, 5, 25, 50, 75, 95, 100)},
            "percent_in_80s": round(float(np.mean((scores >= 80) & (scores < 90))) * 100, 2),
        },
        "score_kernel": "app.word_ranks.cosine_scores float64",
        "same_kernel_api_check": True,
        "elapsed_seconds": round(time.perf_counter() - began, 3),
    }

def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="측정 결과를 저장할 JSON 파일")
    parser.add_argument("--without-index", action="store_true", help="순위 사전 없이 모델 추론 자체를 측정")
    parser.add_argument("--manifest", type=Path, help="fastText 모델 명세 JSON (기본: model-manifest.json)")
    parser.add_argument("--directory", type=Path, help="측정할 모델 파일 폴더")
    args = parser.parse_args()
    import psutil
    process = psutil.Process()
    before = memory_snapshot(process)
    started = time.perf_counter()
    from app.similarity import SimilarityEngine, VectorUnavailableError
    directory = args.directory
    if args.manifest and directory is None:
        manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
        directory = ROOT / manifest["directory"]
    engine = SimilarityEngine(manifest_path=args.manifest, directory=directory, require_ranks=not args.without_index)
    wall_load = time.perf_counter() - started
    if not engine.ready:
        raise SystemExit(f"실제 모델 준비 실패: {engine.error}")
    loaded_memory = memory_snapshot(process)
    rank_benchmark = None
    if engine._rank_index is not None:
        began = time.perf_counter()
        ranks = engine.rankings("산책")
        first_ms = (time.perf_counter() - began) * 1000
        began = time.perf_counter()
        for _ in range(100):
            engine.rankings("산책")
        cached_rank_ms = (time.perf_counter() - began) * 10
        rank_benchmark = {"vocabulary_size": ranks["reference"]["vocabulary_size"],
                          "first_calculation_ms": round(first_ms, 3),
                          "cached_mean_ms": round(cached_rank_ms, 5)}
    examples = [
        ("강아지", "개", "관련 명사"),
        ("강아지", "책상", "무관 명사"),
        ("산책", "걷다", "관련 동사"),
        ("산책", "냉장고", "무관 명사"),
        ("행복", "기쁘다", "관련 감정"),
        ("행복", "볼트", "무관 명사"),
        ("아름답다", "예쁘다", "관련 형용사"),
        ("아름답다", "숟가락", "무관 명사"),
        ("산책", "산첵", "오탈자"),
        ("산책", "초록구름산책냥", "직접 만든 미등록 조합"),
        ("산책", "산책", "동일 입력"),
    ]
    from app.words import get_words
    oov = next((word for word in ("새로지은달빛산책말", "초록구름산책냥", "반짝달빛구름산책나들이말")
                if word not in get_words() and engine.fasttext.word_id(word) == -1), None)
    if oov is None:
        raise SystemExit("사전과 모델에 모두 없는 한글 검사 입력을 찾지 못했습니다.")
    examples.append(("산책", oov, "비교 사전·fastText 모델 모두 미등록인 한글 조합"))
    rows = []
    unsupported_examples = []
    for example_index, (answer, word, category) in enumerate(examples):
        engine.vector.cache_clear()
        began = time.perf_counter()
        try:
            score = engine.score(word, answer)
        except VectorUnavailableError as exc:
            # 첫 8개 품질 비교와 동일 단어·긴 OOV는 필수입니다. 순서도 유지합니다.
            # 선택적인 오탈자 예제만 실제 0벡터/정보 없음으로 보고하고 제외합니다.
            # NaN·Inf·오버플로 같은 모델 오류는 이 예외에 포함되지 않습니다.
            if example_index < 8 or category != "오탈자":
                raise
            model_word_id = engine.fasttext.word_id(word)
            unsupported_examples.append({
                "answer": answer, "word": word, "category": category,
                "in_source_dictionary": word in get_words(),
                "in_comparison_dictionary": (word in engine._rank_index.positions
                                             if engine._rank_index is not None else None),
                "model_word_id": model_word_id,
                "model_oov": model_word_id == -1,
                "reason_code": "vector_unavailable", "reason": str(exc),
            })
            continue
        elapsed = (time.perf_counter() - began) * 1000
        a, b = engine.vector(word), engine.vector(answer)
        dot = math.fsum(float(x) * float(y) for x, y in zip(a, b))
        norm_a = math.sqrt(math.fsum(float(x) ** 2 for x in a))
        norm_b = math.sqrt(math.fsum(float(x) ** 2 for x in b))
        cosine = dot / (norm_a * norm_b) * 100
        if not math.isclose(score, max(-100.0, min(100.0, dot * 100)), rel_tol=0, abs_tol=1e-10):
            raise SystemExit("독립 float64 내적과 실제 모델 점수가 다릅니다.")
        if not math.isclose(score, cosine, rel_tol=0, abs_tol=0.0001):
            raise SystemExit("실제 모델 점수가 독립 코사인 × 100과 다릅니다.")
        row = {"answer": answer, "word": word, "category": category, "cosine_times_100": round(score, 6),
               "independent_cosine_times_100": round(cosine, 8), "uncached_pair_ms": round(elapsed, 3),
               "dimension": len(a), "normalized_vector_norm": norm_a}
        import numpy as np
        raw = engine.fasttext.get_word_vector(word)
        normalized = raw / np.linalg.norm(raw)
        if (len(a) != 300 or not np.isfinite(a).all() or not math.isclose(norm_a, 1, abs_tol=1e-6)
                or not np.array_equal(a, normalized)):
            raise SystemExit("실제 fastText 원본 벡터의 차원·정규화·일치 검사 실패")
        row.update({"model_word_id": engine.fasttext.word_id(word),
                    "model_oov": engine.fasttext.word_id(word) == -1,
                    "in_comparison_dictionary": word in get_words(),
                    "raw_bin_vector_matches": True})
        rows.append(row)
    if not any(row["model_oov"] for row in rows) or not any(not row["model_oov"] for row in rows):
        raise SystemExit("실제 fastText IV와 OOV 입력을 모두 검사하지 못했습니다.")
    # LRU를 비우면 .bin 서브워드를 다시 계산합니다.
    latencies = []
    for _ in range(20):
        engine.vector.cache_clear()
        began = time.perf_counter()
        engine.score("여행", "산책")
        latencies.append((time.perf_counter() - began) * 1000)
    engine.score("여행", "산책")
    began = time.perf_counter()
    for _ in range(100):
        engine.score("여행", "산책")
    cached_ms = (time.perf_counter() - began) * 10
    if rank_benchmark is not None:
        rank_benchmark["verification"] = verify_index(engine, ranks, [row["word"] for row in rows])
    # 기존 지연/순위 측정을 마친 뒤 같은 모델 인스턴스로 추가 품질을 검사합니다.
    quality = quality_comparison(engine)
    final_memory = memory_snapshot(process)
    comparisons = [{"related": rows[i]["word"], "unrelated": rows[i + 1]["word"], "answer": rows[i]["answer"], "related_higher": rows[i]["cosine_times_100"] > rows[i + 1]["cosine_times_100"]} for i in (0, 2, 4, 6)]
    report = {
        "measured_at_utc": datetime.now(timezone.utc).isoformat(),
        "system": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
        "model": engine.name, "fingerprint": engine.fingerprint,
        "manifest": str(args.manifest or ROOT / "model-manifest.json"),
        "scoring_path": "fasttext_bin_subwords",
        "supports_oov": engine.supports_oov, "dimension": engine.dimension,
        "word_ranks": rank_benchmark,
        "versions": {name: version(name) for name in ("numpy", "psutil")},
        "load_seconds_including_import_and_warmup": round(wall_load, 3),
        "engine_load_seconds": round(engine.load_seconds, 3),
        "rss_before_mb": before["rss_mb"], "rss_after_load_mb": loaded_memory["rss_mb"],
        "rss_after_benchmark_mb": final_memory["rss_mb"],
        "max_rss_mb": final_memory["max_rss_mb"], "max_rss_source": final_memory["max_rss_source"],
        "vms_before_mb": before["vms_mb"], "vms_after_load_mb": loaded_memory["vms_mb"],
        "vms_after_benchmark_mb": final_memory["vms_mb"],
        "uncached_pair_median_ms": round(statistics.median(latencies), 3),
        "uncached_pair_p95_ms": round(sorted(latencies)[18], 3),
        "cached_pair_mean_ms": round(cached_ms, 5),
        "quality_comparisons": comparisons,
        "quality_comparison": quality,
        "final_memory_includes_quality_comparison": True,
        "examples": rows,
        "has_unsupported_examples": bool(unsupported_examples),
        "unsupported_examples": unsupported_examples,
        "caveats": [
            "메모리 값의 단위는 MiB(1024² bytes)다. RSS는 현재 상주 메모리, max_rss는 Python 프로세스 시작 이후 최대치다.",
            "VMS는 상주 RAM이 아니다. Linux/macOS에서는 mmap 주소 공간을 포함하며 Windows psutil VMS는 pagefile/private commit 값이다.",
            "최종 RSS/VMS와 최대 RSS에는 모델 검사·준비 벡터 검산·20개 의미 비교·90개 정답 후보 4,005쌍 품질 계산까지 포함된다. 측정값은 별도 앱 프로세스나 컨테이너 전체 메모리가 아니다.",
            "소수 한국어 예제로 단어게임 전반의 품질을 보증하지 않는다. 실제 Mac 검사 여부 및 QEMU 사용 여부는 실행 담당자가 별도로 기록한다.",
            "선택적인 오탈자 예제의 실제 0벡터/정보 없음은 unsupported_examples에 기록하고 점수를 만들지 않는다. 품질 4쌍·추가 20개 의미 비교·90개 정답 후보·동일 단어·긴 OOV 실패는 벤치마크를 중단한다.",
            "fastText는 실제 모델 IV/OOV 모두 원본 .bin 서브워드를 계산한다. API의 형식 제한은 별도 통합 검사로 확인한다.",
            "uncached는 LRU만 비운 상태이며 OS 파일 캐시까지 비운 시간이 아니다.",
        ],
    }
    rendered = json.dumps(report, ensure_ascii=False, indent=2)
    print(rendered)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    if not all(item["related_higher"] for item in comparisons):
        print("주의: 일부 한국어 관련/무관 비교가 기대와 달랐습니다. 품질 보고서를 검토하세요.", file=sys.stderr)


if __name__ == "__main__":
    main()
