"""순위는 표시 점수의 추정이 아니라 전체 벡터의 원래 점수 순서여야 합니다."""
import json

import numpy as np
import pytest

from app import word_ranks
from app.word_ranks import WordRankIndex, WordRanksUnavailableError, cosine_scores, digest, rank_for_score


def vectors(count=1003, dimension=300):
    matrix = np.zeros((count, dimension), dtype="<f4")
    matrix[0, 0] = 1
    cosines = np.linspace(0.99, -0.1, count - 1, dtype=np.float32)
    matrix[1:, 0] = cosines
    matrix[1:, 1] = np.sqrt(1 - cosines ** 2)
    return matrix


def index_for_rules():
    index = WordRankIndex.__new__(WordRankIndex)
    index.words = ["정답"] + [f"검사{i}" for i in range(1, 1003)]
    index.positions = {word: i for i, word in enumerate(index.words)}
    index.vectors = vectors()
    return index


def test_actual_top_thousand_excludes_answer_and_outside_is_not_estimated():
    index = index_for_rules()
    result = index.rankings("정답")
    assert result["ranks"]["정답"] == 0
    assert result["ranks"]["검사1"] == 1
    assert result["ranks"]["검사10"] == 10
    assert result["ranks"]["검사1000"] == 1000
    assert result["ranks"].get("검사1001") is None
    assert result["ranks"].get("사전에없는말") is None
    for place in (1, 10, 1000):
        raw = float(np.clip(np.dot(index.vectors[place], index.vectors[0]), -1.0, 1.0) * 100.0)
        assert result["reference"][f"top{place}"] == pytest.approx(raw, abs=0.0001)
    assert result["reference"]["top1000"] < 0  # 음수도 0점으로 보정하지 않는다.
    assert result["reference"]["vocabulary_size"] == 1003
    assert len(result["words"]) == 1000
    assert result["words"][0] == {
        "word": "검사1", "similarity": result["reference"]["top1"], "rank": 1,
    }
    assert result["words"][9]["similarity"] == result["reference"]["top10"]
    assert result["words"][999]["similarity"] == result["reference"]["top1000"]
    assert all(row["word"] != "정답" for row in result["words"])


def test_exact_score_ties_share_rank_including_thousand_boundary():
    index = index_for_rules()
    index.vectors[2] = index.vectors[1]
    index.vectors[1001] = index.vectors[1000]
    result = index.rankings("정답")
    ranks = result["ranks"]
    assert [ranks[f"검사{i}"] for i in (1, 2, 3)] == [1, 1, 3]
    assert ranks["검사1000"] == ranks["검사1001"] == 1000
    assert ranks.get("검사1002") is None
    assert [row["rank"] for row in result["words"][:3]] == [1, 1, 3]
    assert [row["word"] for row in result["words"][:3]] == ["검사1", "검사2", "검사3"]
    assert len(result["words"]) == 1000
    assert result["words"][-1]["word"] == "검사1000"


def test_display_rounding_does_not_create_a_joint_word_rank():
    index = index_for_rules()
    index.vectors[1, 0] = np.float32(0.999991)
    index.vectors[2, 0] = np.float32(0.999989)
    result = index.rankings("정답")
    assert round(float(index.vectors[1, 0] * 100), 2) == round(float(index.vectors[2, 0] * 100), 2)
    assert result["ranks"]["검사1"] == 1
    assert result["ranks"]["검사2"] == 2


def test_unknown_answer_fails_instead_of_faking_reference_scores():
    with pytest.raises(WordRanksUnavailableError):
        index_for_rules().rankings("없는정답")


@pytest.mark.parametrize("dimension", [12, 300])
def test_single_vector_and_whole_matrix_use_identical_score_accumulation(dimension):
    random = np.random.default_rng(42)
    matrix = random.normal(size=(1003, dimension)).astype("<f4")
    matrix /= np.linalg.norm(matrix, axis=1, keepdims=True)
    answer = matrix[17]
    together = cosine_scores(matrix, answer)
    separate = np.array([cosine_scores(row.reshape(1, -1), answer)[0] for row in matrix])
    assert together.dtype == np.float64
    assert np.array_equal(together, separate)
    for index in (0, 17, 1002):
        independent = min(100.0, max(-100.0, sum(float(a) * float(b) for a, b in zip(matrix[index], answer)) * 100))
        assert together[index] == pytest.approx(independent, abs=1e-12)


def test_oov_and_dictionary_words_share_exact_ties_and_thousand_boundary():
    index = index_for_rules()
    index.vectors[2] = index.vectors[1]
    index.vectors[1001] = index.vectors[1000]
    result = index.rankings("정답")
    scores = cosine_scores(index.vectors, index.vectors[0])
    assert result["sorted_scores"].dtype == np.float64
    assert len(result["sorted_scores"]) == len(index.words) - 1
    assert np.array_equal(result["sorted_scores"], np.sort(scores[1:]))
    for word, score in zip(index.words, scores):
        assert rank_for_score(result, word, score) == result["ranks"].get(word)
    assert rank_for_score(result, "사전밖첫단어", scores[1]) == 1
    assert rank_for_score(result, "사전밖최상위", np.nextafter(scores[1], np.inf)) == 1
    assert rank_for_score(result, "사전밖공동다음", np.nextafter(scores[1], -np.inf)) == 3
    assert rank_for_score(result, "사전밖경계", scores[1000]) == 1000
    assert rank_for_score(result, "사전밖범위밖", np.nextafter(scores[1000], -np.inf)) is None
    assert rank_for_score(result, "정답", scores[0]) == 0


def test_rank_helper_preserves_missing_and_rule_fixture_behavior():
    assert rank_for_score(None, "단어", 10.0) is None
    fixture = {"ranks": {"정답": 0, "단어": 7}}
    assert rank_for_score(fixture, "단어", 10.0) == 7
    assert rank_for_score(fixture, "정답", 100.0) == 0
    assert rank_for_score(fixture, "없는단어", 10.0) is None
    assert rank_for_score(fixture, "단어", None) is None
    assert rank_for_score(fixture, "단어", float("nan")) is None


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    names = [chr(0xAC00 + i) for i in range(1003)]
    dictionary = tmp_path / "dictionary.txt"
    dictionary.write_text("\n".join(names) + "\n", encoding="utf-8")
    monkeypatch.setattr(word_ranks, "WORDS_PATH", dictionary)
    monkeypatch.setattr(word_ranks, "get_words", lambda: frozenset(names))
    (tmp_path / "words.json").write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    np.save(tmp_path / "vectors.npy", vectors(), allow_pickle=False)
    metadata = {"format": 2, "model_fingerprint": "test-model", "dictionary_sha256": digest(dictionary),
                "count": len(names), "dimension": 300, "excluded_words": [], "files": {}}
    for name in ("words.json", "vectors.npy"):
        metadata["files"][name] = {"size": (tmp_path / name).stat().st_size, "sha256": digest(tmp_path / name)}
    (tmp_path / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    return tmp_path, names, metadata


def test_loader_checks_corpus_and_reuses_real_vectors(prepared):
    directory, names, _ = prepared
    index = WordRankIndex(directory, "test-model")
    assert isinstance(index.vectors, np.memmap)
    assert np.array_equal(index.vector(names[12]), vectors()[12])
    assert index.vector("누락") is None
    assert index.rankings(names[0])["ranks"][names[1000]] == 1000


@pytest.mark.parametrize("fault", ["missing", "format", "model", "dictionary", "checksum", "count", "dimension", "vocabulary", "nan", "norm"])
def test_missing_stale_or_corrupt_index_is_rejected(prepared, fault):
    directory, _, metadata = prepared
    if fault == "missing":
        (directory / "vectors.npy").unlink()
    elif fault == "format":
        metadata["format"] = 1
    elif fault == "model":
        metadata["model_fingerprint"] = "other-model"
    elif fault == "dictionary":
        metadata["dictionary_sha256"] = "0" * 64
    elif fault == "checksum":
        metadata["files"]["vectors.npy"]["sha256"] = "0" * 64
    elif fault in ("count", "dimension"):
        metadata[fault] -= 1
    else:
        name = "words.json" if fault == "vocabulary" else "vectors.npy"
        if fault == "vocabulary":
            (directory / name).write_text(json.dumps(["다른단어"] * 1003), encoding="utf-8")
        else:
            matrix = vectors()
            matrix[3] = np.nan if fault == "nan" else 0
            np.save(directory / name, matrix, allow_pickle=False)
        metadata["files"][name] = {"size": (directory / name).stat().st_size, "sha256": digest(directory / name)}
    (directory / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(WordRanksUnavailableError):
        WordRankIndex(directory, "test-model")


@pytest.fixture
def prepared_format2(prepared):
    directory, names, metadata = prepared
    names.append(chr(0xAC00 + len(names)))
    (directory / "dictionary.txt").write_text("\n".join(names) + "\n", encoding="utf-8")
    valid = names[:-2]
    excluded = names[-2:]
    (directory / "words.json").write_text(json.dumps(valid, ensure_ascii=False), encoding="utf-8")
    np.save(directory / "vectors.npy", vectors(len(valid), 300), allow_pickle=False)
    metadata.update(format=2, dictionary_sha256=digest(directory / "dictionary.txt"),
                    count=len(valid), dimension=300, excluded_words=excluded)
    for name in ("words.json", "vectors.npy"):
        metadata["files"][name] = {"size": (directory / name).stat().st_size, "sha256": digest(directory / name)}
    (directory / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    return directory, valid, metadata


def test_format2_accepts_300_dimensions_and_records_exact_excluded_partition(prepared_format2):
    directory, valid, metadata = prepared_format2
    index = WordRankIndex(directory, "test-model", dimension=300)
    assert index.words == valid
    assert index.excluded_words == metadata["excluded_words"]
    assert index.vectors.shape == (1002, 300)
    assert index.vector(metadata["excluded_words"][0]) is None
    assert index.rankings(valid[0])["reference"]["vocabulary_size"] == 1002
    with pytest.raises(WordRanksUnavailableError):
        WordRankIndex(directory, "test-model", dimension=299)


@pytest.mark.parametrize("fault", ["missing", "overlap", "omitted", "foreign", "duplicate", "unsorted", "not-list", "too-few"])
def test_format2_requires_disjoint_complete_dictionary_partition(prepared_format2, fault):
    directory, valid, metadata = prepared_format2
    if fault == "missing":
        del metadata["excluded_words"]
    elif fault == "overlap":
        metadata["excluded_words"] = sorted(metadata["excluded_words"] + [valid[0]])
    elif fault == "omitted":
        metadata["excluded_words"] = metadata["excluded_words"][1:]
    elif fault == "foreign":
        metadata["excluded_words"] = sorted(metadata["excluded_words"] + ["사전밖"])
    elif fault == "duplicate":
        metadata["excluded_words"] = sorted(metadata["excluded_words"] * 2)
    elif fault == "unsorted":
        metadata["excluded_words"] = list(reversed(metadata["excluded_words"]))
    elif fault == "not-list":
        metadata["excluded_words"] = {word: True for word in metadata["excluded_words"]}
    else:
        metadata["excluded_words"] = sorted(metadata["excluded_words"] + [valid.pop()])
        metadata["count"] = len(valid)
        (directory / "words.json").write_text(json.dumps(valid), encoding="utf-8")
        np.save(directory / "vectors.npy", vectors(len(valid), 300), allow_pickle=False)
        for name in ("words.json", "vectors.npy"):
            metadata["files"][name] = {"size": (directory / name).stat().st_size, "sha256": digest(directory / name)}
    (directory / "manifest.json").write_text(json.dumps(metadata), encoding="utf-8")
    with pytest.raises(WordRanksUnavailableError):
        WordRankIndex(directory, "test-model", dimension=300)
