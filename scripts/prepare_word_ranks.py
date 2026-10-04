"""허용 사전 전체를 실제 모델로 한 번 계산합니다. 중단하면 완료 구간부터 재개합니다."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import sys
import time
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def write_json(path: Path, value):
    partial = path.with_name(path.name + ".writing")
    partial.write_text(
        json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    partial.replace(path)


def validate_progress(matrix, names, excluded, completed):
    """완료 구간의 유효 행과 제외 행 표시가 진행 정보와 일치하는지 검사합니다."""
    import numpy as np

    for start in range(0, completed, 4096):
        stop = min(start + 4096, completed)
        block = matrix[start:stop]
        valid = np.array([word not in excluded for word in names[start:stop]], dtype=bool)
        if (
            not np.isfinite(block).all()
            or not np.allclose(np.linalg.norm(block[valid], axis=1), 1, atol=0.0001)
            or np.any(block[~valid] != 0)
        ):
            raise SystemExit("준비 중 벡터의 유한값·정규화 또는 제외 기록이 맞지 않습니다.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="기존 산출물만 검증")
    parser.add_argument("--directory", type=Path, help="실제 모델 파일이 있는 디렉터리")
    parser.add_argument(
        "--manifest", type=Path, default=ROOT / "model-manifest.json", help="준비할 모델 명세"
    )
    args = parser.parse_args()
    from app.similarity import SimilarityEngine, VectorUnavailableError
    from app.word_ranks import WordRankIndex, WordRanksUnavailableError, digest
    from app.words import WORDS_PATH, get_words
    import numpy as np

    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    directory = args.directory or Path(os.getenv("MODEL_DIR", str(ROOT / manifest["directory"])))
    engine = SimilarityEngine(directory=directory, manifest_path=args.manifest)
    if not engine.ready:
        raise SystemExit(engine.error)
    dimension = engine.dimension
    if type(dimension) is not int or dimension <= 0:
        raise SystemExit("모델의 벡터 차원이 올바르지 않습니다.")
    names = sorted(get_words())
    answers = {
        unicodedata.normalize("NFC", line.strip())
        for line in (ROOT / "backend" / "app" / "answers.txt")
        .read_text(encoding="utf-8-sig")
        .splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not answers or not answers <= set(names):
        raise SystemExit("정답 후보가 비어 있거나 원본 비교 사전에 없는 정답 후보가 있습니다.")
    destination = directory / "word-ranks"
    try:
        prepared = WordRankIndex(destination, engine.fingerprint, dimension=dimension)
        if not answers <= set(prepared.words):
            raise SystemExit("현재 순위 자료에서 실제 벡터가 없는 정답 후보가 있습니다.")
        print("단어 순위 자료 검증 완료. 다시 계산하지 않습니다.", flush=True)
        return
    except WordRanksUnavailableError:
        if args.check:
            raise SystemExit("단어 순위 자료가 없거나 모델·사전·체크섬이 맞지 않습니다.")

    signature = {
        "format": 2,
        "model_fingerprint": engine.fingerprint,
        "dictionary_sha256": digest(WORDS_PATH),
        "count": len(names),
        "dimension": dimension,
    }
    destination.mkdir(parents=True, exist_ok=True)
    checkpoint = destination / "progress.json"
    matrix_path = destination / "vectors.partial.npy"
    start = 0
    excluded = set()
    if checkpoint.exists():
        progress = json.loads(checkpoint.read_text(encoding="utf-8"))
        if progress.get("signature") != signature:
            raise SystemExit(
                "이전 준비 파일의 모델·사전 버전이 다릅니다. 다른 모델 폴더에서 준비하세요."
            )
        start = progress["completed"]
        if type(start) is not int or not 0 <= start <= len(names):
            raise SystemExit("준비 진행 정보가 잘못되었습니다.")
        excluded_words = progress.get("excluded_words", [])
        if (
            not isinstance(excluded_words, list)
            or not all(isinstance(word, str) for word in excluded_words)
            or excluded_words != sorted(set(excluded_words))
            or not set(excluded_words) <= set(names[:start])
        ):
            raise SystemExit("준비 진행 정보의 제외 단어 목록이 잘못되었습니다.")
        excluded = set(excluded_words)
        if (
            start == len(names)
            and not matrix_path.exists()
            and (destination / "vectors.npy").exists()
        ):
            # 이전 모델의 정상 벡터를 새 모델 결과로 잘못 인증하지 않습니다.
            raise SystemExit(
                "준비 중 벡터 파일이 없어 기존 완료 파일을 재사용하지 않습니다. 별도 폴더에서 순위 자료를 다시 준비해 주세요."
            )
        if not matrix_path.exists():
            raise SystemExit("준비 진행 정보에 대응하는 부분 벡터 파일이 없습니다.")
        matrix = np.lib.format.open_memmap(matrix_path, mode="r+")
        if matrix.shape != (len(names), dimension) or matrix.dtype != np.dtype("<f4"):
            raise SystemExit("준비 중 벡터 파일의 크기가 맞지 않습니다.")
        validate_progress(matrix, names, excluded, start)
    else:
        if matrix_path.exists():
            raise SystemExit(
                "진행 정보가 없는 부분 벡터 파일은 재사용하지 않습니다. 별도 폴더에서 준비하세요."
            )
        matrix = np.lib.format.open_memmap(
            matrix_path, mode="w+", dtype="<f4", shape=(len(names), dimension)
        )
        matrix.flush()
        write_json(checkpoint, {"signature": signature, "completed": 0, "excluded_words": []})
    if excluded & answers:
        raise SystemExit("실제 벡터가 없는 정답 후보가 있어 준비를 중단했습니다.")
    began = time.perf_counter()
    print(f"단어 벡터 준비 시작: {start:,}/{len(names):,}", flush=True)
    for index in range(start, len(names)):
        try:
            vector = np.asarray(engine.vector(names[index]), dtype="<f4")
        except VectorUnavailableError:
            if names[index] in answers:
                raise SystemExit("실제 벡터가 없는 정답 후보가 있어 준비를 중단했습니다.") from None
            # 다른 오류는 제외로 바꾸지 않습니다. 0행과 목록을 함께 체크포인트에 남깁니다.
            matrix[index] = 0
            excluded.add(names[index])
        else:
            if (
                vector.shape != (dimension,)
                or not np.isfinite(vector).all()
                or not np.isclose(np.linalg.norm(vector), 1, atol=0.0001)
            ):
                raise SystemExit("모델이 유효한 정규화 벡터를 만들지 못해 준비를 중단했습니다.")
            matrix[index] = vector
        completed = index + 1
        if completed % 1000 == 0 or completed == len(names):
            matrix.flush()
            write_json(
                checkpoint,
                {
                    "signature": signature,
                    "completed": completed,
                    "excluded_words": sorted(excluded),
                },
            )
            print(
                f"단어 벡터 준비: {completed:,}/{len(names):,} ({time.perf_counter() - began:.1f}초)",
                flush=True,
            )
    matrix.flush()
    validate_progress(matrix, names, excluded, len(names))
    valid_positions = [index for index, word in enumerate(names) if word not in excluded]
    valid_names = [names[index] for index in valid_positions]
    if len(valid_names) < 1002:
        raise SystemExit(
            "유효한 비교 단어가 1,002개 미만이라 상위 1,000위 기준을 만들 수 없습니다."
        )
    # 완료 자료를 게시하는 중 중단돼도 원본 부분 행과 체크포인트로 다시 만들 수 있습니다.
    ready_path = destination / "vectors.ready.npy"
    ready = np.lib.format.open_memmap(
        ready_path, mode="w+", dtype="<f4", shape=(len(valid_names), dimension)
    )
    for start in range(0, len(valid_positions), 4096):
        ready[start : start + 4096] = matrix[valid_positions[start : start + 4096]]
    ready.flush()
    del ready
    del matrix
    write_json(destination / "words.json", valid_names)
    ready_path.replace(destination / "vectors.npy")
    files = {
        name: {"size": (destination / name).stat().st_size, "sha256": digest(destination / name)}
        for name in ("words.json", "vectors.npy")
    }
    write_json(
        destination / "manifest.json",
        {
            **signature,
            "count": len(valid_names),
            "excluded_words": sorted(excluded),
            "files": files,
        },
    )
    WordRankIndex(destination, engine.fingerprint, dimension=dimension)
    if checkpoint.exists():
        checkpoint.unlink()
    matrix_path.unlink()
    print(
        json.dumps(
            {
                "ready": True,
                "count": len(valid_names),
                "excluded_count": len(excluded),
                "dimension": dimension,
                "bytes": sum(item["size"] for item in files.values()),
                "files": files,
            },
            ensure_ascii=False,
        ),
        flush=True,
    )


if __name__ == "__main__":
    main()
