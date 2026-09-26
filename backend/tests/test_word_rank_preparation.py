"""준비 파일 재개의 출처 보존을 임시 파일로 검사합니다. 모델·운영 DB는 사용하지 않습니다."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "scripts"))
from app import similarity, word_ranks, words
from app.word_ranks import WordRanksUnavailableError, digest
import prepare_word_ranks


@pytest.fixture
def checkpoint(tmp_path, monkeypatch):
    names = [chr(0xAC00 + index) for index in range(1003)]
    dictionary = tmp_path / "words.txt"
    dictionary.write_text("\n".join(names) + "\n", encoding="utf-8")
    model_directory = tmp_path / "model"
    destination = model_directory / "word-ranks"
    destination.mkdir(parents=True)
    (tmp_path / "model-manifest.json").write_text(json.dumps({"directory": "model"}), encoding="utf-8")
    answers = tmp_path / "backend" / "app" / "answers.txt"
    answers.parent.mkdir(parents=True)
    answers.write_text("\n".join(names[:90]) + "\n", encoding="utf-8")
    vectors = np.zeros((len(names), 300), dtype="<f4")
    for index in range(len(names)):
        vectors[index, index % 300] = 1.0
    old_vectors = np.zeros_like(vectors)
    old_vectors[:, 100] = 1.0  # 정상적인 단위 벡터지만 이전 모델에서 만든 다른 결과입니다.
    np.save(destination / "vectors.npy", old_vectors, allow_pickle=False)
    (destination / "words.json").write_text(json.dumps(names, ensure_ascii=False), encoding="utf-8")
    (destination / "manifest.json").write_text(json.dumps({"model_fingerprint": "old-model"}), encoding="utf-8")
    signature = {"format": 2, "model_fingerprint": "new-model", "dictionary_sha256": digest(dictionary),
                 "count": len(names), "dimension": 300}
    (destination / "progress.json").write_text(json.dumps({"signature": signature, "completed": len(names)}), encoding="utf-8")
    engine = SimpleNamespace(ready=True, fingerprint="new-model", dimension=300,
                             vector=Mock(side_effect=lambda word: vectors[names.index(word)]))
    constructor = Mock(return_value=engine)
    # 첫 검증은 이전 모델의 완료 파일을 거부하고, 정상 새 결과가 만들어지면 두 번째 검증을 합니다.
    validator = Mock(side_effect=[WordRanksUnavailableError("TEST ONLY: old model"), SimpleNamespace(words=names)])
    monkeypatch.setattr(similarity, "SimilarityEngine", constructor)
    monkeypatch.setattr(word_ranks, "WordRankIndex", validator)
    monkeypatch.setattr(words, "WORDS_PATH", dictionary)
    monkeypatch.setattr(words, "get_words", lambda: frozenset(names))
    monkeypatch.setattr(prepare_word_ranks, "ROOT", tmp_path)
    monkeypatch.setattr(sys, "argv", ["prepare_word_ranks.py", "--directory", str(model_directory)])
    return SimpleNamespace(destination=destination, names=names, vectors=vectors,
                           signature=signature, engine=engine, validator=validator, root=tmp_path,
                           constructor=constructor, dictionary=dictionary)


def snapshot(directory):
    return {path.name: path.read_bytes() for path in directory.iterdir() if path.is_file()}


def test_completed_checkpoint_without_partial_cannot_relabel_old_final_vectors(checkpoint):
    prepared = checkpoint
    before = snapshot(prepared.destination)
    assert not (prepared.destination / "vectors.partial.npy").exists()
    with pytest.raises(SystemExit, match="기존 완료 파일을 재사용하지 않습니다"):
        prepare_word_ranks.main()
    assert snapshot(prepared.destination) == before
    assert json.loads((prepared.destination / "manifest.json").read_text(encoding="utf-8"))["model_fingerprint"] == "old-model"
    prepared.engine.vector.assert_not_called()
    prepared.validator.assert_called_once_with(prepared.destination, "new-model", dimension=300)


@pytest.mark.parametrize("completed", [1002, 1003], ids=["unfinished", "complete"])
def test_existing_partial_resumes_and_publishes_only_its_own_vectors(checkpoint, completed):
    prepared = checkpoint
    partial = prepared.vectors.copy()
    partial[completed:] = 0.0
    np.save(prepared.destination / "vectors.partial.npy", partial, allow_pickle=False)
    (prepared.destination / "progress.json").write_text(
        json.dumps({"signature": prepared.signature, "completed": completed}), encoding="utf-8")
    prepare_word_ranks.main()
    actual = np.load(prepared.destination / "vectors.npy", allow_pickle=False)
    assert np.array_equal(actual, prepared.vectors)
    assert not (prepared.destination / "vectors.partial.npy").exists()
    assert not (prepared.destination / "progress.json").exists()
    manifest = json.loads((prepared.destination / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["model_fingerprint"] == "new-model"
    assert manifest["files"]["vectors.npy"]["sha256"] == digest(prepared.destination / "vectors.npy")
    assert prepared.validator.call_count == 2
    if completed == len(prepared.names):
        prepared.engine.vector.assert_not_called()
    else:
        prepared.engine.vector.assert_called_once_with(prepared.names[completed])


@pytest.fixture
def fasttext_preparation(tmp_path, monkeypatch):
    names = [chr(0xAC00 + index) for index in range(1004)]
    dictionary = tmp_path / "dictionary.txt"
    dictionary.write_text("\n".join(names) + "\n", encoding="utf-8")
    model_directory = tmp_path / "candidate"
    model_directory.mkdir()
    manifest = tmp_path / "candidate-manifest.json"
    manifest.write_text(json.dumps({"directory": "candidate"}), encoding="utf-8")
    answers = tmp_path / "backend" / "app" / "answers.txt"
    answers.parent.mkdir(parents=True)
    answers.write_text("\n".join(names[:90]) + "\n", encoding="utf-8")
    matrix = np.zeros((len(names), 300), dtype="<f4")
    for index in range(len(names)):
        matrix[index, index % 300] = 1
    positions = {word: index for index, word in enumerate(names)}
    controls = SimpleNamespace(excluded={names[99], names[-1]}, failure=None,
                               invalid_word=None, invalid_vector=None)

    def vector(word):
        if word == controls.failure:
            raise RuntimeError("TEST ONLY: unexpected model failure")
        if word == controls.invalid_word:
            return controls.invalid_vector
        if word in controls.excluded:
            raise similarity.VectorUnavailableError("TEST ONLY: no vector")
        return matrix[positions[word]]

    engine = SimpleNamespace(ready=True, error=None, fingerprint="fasttext-test", dimension=300,
                             supports_oov=True, vector=Mock(side_effect=vector))
    constructor = Mock(return_value=engine)
    monkeypatch.setattr(similarity, "SimilarityEngine", constructor)
    monkeypatch.setattr(words, "WORDS_PATH", dictionary)
    monkeypatch.setattr(words, "get_words", lambda: frozenset(names))
    monkeypatch.setattr(word_ranks, "WORDS_PATH", dictionary)
    monkeypatch.setattr(word_ranks, "get_words", lambda: frozenset(names))
    monkeypatch.setattr(prepare_word_ranks, "ROOT", tmp_path)
    monkeypatch.delenv("MODEL_DIR", raising=False)
    monkeypatch.setattr(sys, "argv", ["prepare_word_ranks.py", "--manifest", str(manifest)])
    return SimpleNamespace(names=names, matrix=matrix, controls=controls, engine=engine,
                           constructor=constructor, manifest=manifest, directory=model_directory,
                           destination=model_directory / "word-ranks")


def test_new_manifest_prepares_300_dimensions_excluding_only_unavailable_vectors(fasttext_preparation):
    prepared = fasttext_preparation
    prepare_word_ranks.main()
    prepared.constructor.assert_called_once_with(directory=prepared.directory, manifest_path=prepared.manifest)
    metadata = json.loads((prepared.destination / "manifest.json").read_text(encoding="utf-8"))
    assert metadata["format"] == 2
    assert metadata["dimension"] == 300 and metadata["count"] == 1002
    assert metadata["excluded_words"] == sorted(prepared.controls.excluded)
    names = json.loads((prepared.destination / "words.json").read_text(encoding="utf-8"))
    expected_positions = [index for index, word in enumerate(prepared.names) if word not in prepared.controls.excluded]
    assert names == [prepared.names[index] for index in expected_positions]
    assert np.array_equal(np.load(prepared.destination / "vectors.npy"), prepared.matrix[expected_positions])
    assert set(prepared.names[:90]) <= set(names)
    assert not (prepared.destination / "progress.json").exists()
    assert not (prepared.destination / "vectors.partial.npy").exists()


def test_unexpected_failure_is_not_excluded_and_resume_keeps_prior_exclusions(fasttext_preparation):
    prepared = fasttext_preparation
    prepared.controls.failure = prepared.names[1001]
    with pytest.raises(RuntimeError, match="unexpected model failure"):
        prepare_word_ranks.main()
    progress = json.loads((prepared.destination / "progress.json").read_text(encoding="utf-8"))
    assert progress["completed"] == 1000
    assert progress["excluded_words"] == [prepared.names[99]]
    assert not (prepared.destination / "manifest.json").exists()
    prepared.controls.failure = None
    prepared.engine.vector.reset_mock()
    prepare_word_ranks.main()
    assert [call.args[0] for call in prepared.engine.vector.call_args_list] == prepared.names[1000:]
    metadata = json.loads((prepared.destination / "manifest.json").read_text(encoding="utf-8"))
    assert metadata["excluded_words"] == sorted(prepared.controls.excluded)
    assert metadata["count"] == 1002


@pytest.mark.parametrize("answer_position", [0, 89], ids=["first-candidate", "last-candidate"])
def test_any_unavailable_answer_candidate_stops_preparation(fasttext_preparation, answer_position):
    prepared = fasttext_preparation
    prepared.controls.excluded.add(prepared.names[answer_position])
    with pytest.raises(SystemExit, match="정답 후보"):
        prepare_word_ranks.main()
    assert not (prepared.destination / "manifest.json").exists()
    progress = json.loads((prepared.destination / "progress.json").read_text(encoding="utf-8"))
    assert progress["completed"] == 0
    assert progress["excluded_words"] == []


@pytest.mark.parametrize("fault", ["zero", "nan", "dimension"])
def test_invalid_vectors_are_errors_instead_of_silent_exclusions(fasttext_preparation, fault):
    prepared = fasttext_preparation
    prepared.controls.invalid_word = prepared.names[95]
    prepared.controls.invalid_vector = {
        "zero": np.zeros(300, dtype="<f4"),
        "nan": np.full(300, np.nan, dtype="<f4"),
        "dimension": np.ones(299, dtype="<f4"),
    }[fault]
    with pytest.raises(SystemExit, match="유효한 정규화 벡터"):
        prepare_word_ranks.main()
    assert not (prepared.destination / "manifest.json").exists()
    progress = json.loads((prepared.destination / "progress.json").read_text(encoding="utf-8"))
    assert progress["excluded_words"] == []


@pytest.mark.parametrize("fault", ["future", "duplicate", "missing", "nonzero"])
def test_corrupt_exclusion_checkpoint_is_rejected_without_more_inference(fasttext_preparation, fault):
    prepared = fasttext_preparation
    prepared.controls.failure = prepared.names[1001]
    with pytest.raises(RuntimeError):
        prepare_word_ranks.main()
    checkpoint = prepared.destination / "progress.json"
    progress = json.loads(checkpoint.read_text(encoding="utf-8"))
    if fault == "future":
        progress["excluded_words"].append(prepared.names[-1])
    elif fault == "duplicate":
        progress["excluded_words"] *= 2
    elif fault == "missing":
        progress["excluded_words"] = []
    else:
        progress["excluded_words"].insert(0, prepared.names[98])
    checkpoint.write_text(json.dumps(progress), encoding="utf-8")
    before = snapshot(prepared.destination)
    prepared.controls.failure = None
    prepared.engine.vector.reset_mock()
    with pytest.raises(SystemExit):
        prepare_word_ranks.main()
    prepared.engine.vector.assert_not_called()
    assert snapshot(prepared.destination) == before


def test_interrupted_final_publish_reuses_complete_partial_without_new_vectors(fasttext_preparation, monkeypatch):
    prepared = fasttext_preparation
    original_write = prepare_word_ranks.write_json

    def interrupted_write(path, value):
        if path.name == "manifest.json":
            raise OSError("TEST ONLY: interrupted final publication")
        original_write(path, value)

    with monkeypatch.context() as patch:
        patch.setattr(prepare_word_ranks, "write_json", interrupted_write)
        with pytest.raises(OSError, match="interrupted final"):
            prepare_word_ranks.main()
    assert (prepared.destination / "vectors.partial.npy").exists()
    progress = json.loads((prepared.destination / "progress.json").read_text(encoding="utf-8"))
    assert progress["completed"] == len(prepared.names)
    prepared.engine.vector.reset_mock()
    prepare_word_ranks.main()
    prepared.engine.vector.assert_not_called()
    index = word_ranks.WordRankIndex(prepared.destination, "fasttext-test", dimension=300)
    assert len(index.words) == 1002
    assert index.excluded_words == sorted(prepared.controls.excluded)
    assert not (prepared.destination / "progress.json").exists()
    assert not (prepared.destination / "vectors.partial.npy").exists()
