"""작은 직접 생성 .bin으로 형식·subword 규칙을 확인합니다(실모델 품질 검사 아님)."""

from contextlib import closing
import struct

import numpy as np
import pytest

from app.fasttext_bin import FastTextBin, FastTextFormatError, FastTextVectorError, _hash


def write_binary(tmp_path, *, words=("가", "</s>"), bucket=17, minn=3, maxn=6, matrix=None):
    """공식 v12의 저장 필드를 명시해 읽기 구현과 독립적인 작은 파일을 만듭니다."""
    dim = 3
    data = bytearray(struct.pack("<ii", 793712314, 12))
    data += struct.pack("<12id", dim, 5, 5, 1, 5, 1, 2, 1, bucket, minn, maxn, 100, 0.0001)
    positions = {"dictionary": len(data)}
    data += struct.pack("<iiiqq", len(words), len(words), 0, 100, -1)
    for word in words:
        data += word.encode("utf-8") + b"\0" + struct.pack("<qb", 10, 0)
    positions["input_flag"] = len(data)
    data += b"\0"
    positions["input_shape"] = len(data)
    data += struct.pack("<qq", len(words) + bucket, dim)
    positions["input_data"] = len(data)
    if matrix is None:
        matrix = np.arange(1, (len(words) + bucket) * dim + 1, dtype=np.float32).reshape(-1, dim)
    data += matrix.astype("<f4").tobytes()
    positions["output_flag"] = len(data)
    data += b"\0"
    positions["output_shape"] = len(data)
    data += struct.pack("<qq", len(words), dim)
    # 계산에 쓰지 않는 출력 행렬은 입력과 완전히 다른 값입니다.
    data += np.full((len(words), dim), -9999, dtype="<f4").tobytes()
    path = tmp_path / "model.bin"
    path.write_bytes(data)
    return path, data, matrix, positions


@pytest.mark.parametrize(
    ("word", "expected"),
    [
        ("hello", 1335831723),
        ("한글", 2522324609),
        ("<가>", 2790065039),
        ("가나", 966334256),
    ],
)
def test_hash_uses_signed_utf8_bytes(word, expected):
    assert _hash(word.encode("utf-8")) == expected
    # '한글'에 unsigned-byte FNV를 쓰면 3865498753으로 달라집니다.


def test_known_word_averages_word_id_and_subword_and_preserves_file(tmp_path):
    path, original, matrix, _ = write_binary(tmp_path)
    with closing(FastTextBin(path)) as model:
        assert model.dimension == 3 and model.nwords == 2
        assert model.word_id("가") == 0 and model.word_id("모르는단어") == -1
        assert isinstance(model._input, np.memmap) and not model._input.flags.writeable
        expected = (matrix[0] + matrix[2 + 2790065039 % 17]) * np.float32(0.5)
        result = model.get_word_vector("가")
        np.testing.assert_array_equal(result, expected)
        assert result.dtype == np.float32
        result[:] = 0  # 반환 값은 파일의 행이나 뷰를 노출하지 않습니다.
        np.testing.assert_array_equal(model.get_word_vector("가"), expected)
    assert path.read_bytes() == original


def test_oov_uses_character_boundaries_and_both_boundary_markers(tmp_path):
    path, _, matrix, _ = write_binary(tmp_path, minn=3, maxn=4)
    with closing(FastTextBin(path)) as model:
        # '<가나>', 글자 길이 3~4: '<가나', '<가나>', '가나>'의 세 subword.
        ids = [2 + value % 17 for value in (1557458778, 2268387948, 3120515850)]
        assert model.word_id("가나") == -1
        assert model._subword_ids("가나") == ids
        expected = np.zeros(3, dtype=np.float32)
        for index in ids:
            expected += matrix[index]
        expected *= np.float32(1 / 3)
        np.testing.assert_array_equal(model.get_word_vector("가나"), expected)


def test_repeated_hashes_keep_their_multiplicity(tmp_path):
    path, _, matrix, _ = write_binary(tmp_path, words=("가가가", "</s>"), bucket=1)
    with closing(FastTextBin(path)) as model:
        assert model._subword_ids("가가가") == [0, 2, 2, 2, 2, 2, 2]
        expected = (matrix[0] + matrix[2] * np.float32(6)) * np.float32(1 / 7)
        np.testing.assert_allclose(model.get_word_vector("가가가"), expected, rtol=1e-7)
        assert not np.allclose(expected, (matrix[0] + matrix[2]) / 2)


def test_eos_and_single_character_boundary_exclusion(tmp_path):
    path, _, matrix, _ = write_binary(tmp_path, minn=1, maxn=1)
    with closing(FastTextBin(path)) as model:
        assert model._subword_ids("가") == [0, 2 + 3016172053 % 17]
        assert model._subword_ids("</s>") == [1]
        np.testing.assert_array_equal(model.get_word_vector("</s>"), matrix[1])


def test_short_oov_without_ngrams_is_not_a_fake_zero_score(tmp_path):
    path, _, matrix, _ = write_binary(tmp_path, minn=5, maxn=5)
    with closing(FastTextBin(path)) as model:
        np.testing.assert_array_equal(model.get_word_vector("가"), matrix[0])
        with pytest.raises(FastTextVectorError, match="subword"):
            model.get_word_vector("나")


@pytest.mark.parametrize(
    "value, expected_error",
    [
        (0, FastTextVectorError),
        (np.nan, FastTextFormatError),
        (np.inf, FastTextFormatError),
        (np.finfo(np.float32).max, FastTextFormatError),
    ],
    ids=["zero-input-error", "nan-model-error", "infinity-model-error", "overflow-model-error"],
)
def test_only_zero_is_input_error_while_nonfinite_and_overflow_are_model_errors(
    tmp_path, value, expected_error
):
    matrix = np.full((19, 3), value, dtype=np.float32)
    path, _, _, _ = write_binary(tmp_path, matrix=matrix)
    with closing(FastTextBin(path)) as model:
        with pytest.raises(expected_error):
            model.get_word_vector("가")


@pytest.mark.parametrize("word", ["", "가\0나", None])
def test_invalid_vector_input(tmp_path, word):
    path, _, _, _ = write_binary(tmp_path)
    with closing(FastTextBin(path)) as model:
        with pytest.raises(FastTextVectorError):
            model.get_word_vector(word)


@pytest.mark.parametrize(
    ("field", "fmt", "value"),
    [
        ("magic", "<i", 1),
        ("version", "<i", 11),
        ("dimension", "<i", 0),
        ("model", "<i", 3),
        ("bucket", "<i", 0),
        ("minn", "<i", 9),
        ("loss", "<i", 99),
        ("sampling", "<d", np.nan),
        ("nwords", "<i", 1),
        ("nlabels", "<i", 1),
        ("ntokens", "<q", -1),
        ("pruned", "<q", 0),
        ("input_flag", "<B", 1),
        ("output_flag", "<B", 1),
        ("input_shape", "<q", 20),
        ("input_columns", "<q", 4),
        ("output_shape", "<q", 3),
        ("output_columns", "<q", 4),
    ],
)
def test_invalid_or_unsupported_file_fields(tmp_path, field, fmt, value):
    path, data, _, offsets = write_binary(tmp_path)
    offsets.update(
        magic=0,
        version=4,
        dimension=8,
        model=36,
        bucket=40,
        minn=44,
        loss=32,
        sampling=56,
        nwords=68,
        nlabels=72,
        ntokens=76,
        pruned=84,
        input_columns=offsets["input_shape"] + 8,
        output_columns=offsets["output_shape"] + 8,
    )
    struct.pack_into(fmt, data, offsets[field], value)
    path.write_bytes(data)
    with pytest.raises(FastTextFormatError):
        FastTextBin(path)


@pytest.mark.parametrize("change", ["empty", "header", "dictionary", "input", "output", "trailing"])
def test_truncation_and_trailing_bytes(tmp_path, change):
    path, data, _, offsets = write_binary(tmp_path)
    cuts = {
        "empty": 0,
        "header": 7,
        "dictionary": 94,
        "input": offsets["input_data"] + 5,
        "output": len(data) - 1,
    }
    path.write_bytes(data + b"unexpected" if change == "trailing" else data[: cuts[change]])
    with pytest.raises(FastTextFormatError):
        FastTextBin(path)


def test_dictionary_preserves_non_utf8_bytes_without_changing_word_ids(tmp_path):
    path, data, matrix, _ = write_binary(tmp_path)
    data[92] = 0xFF  # 공식 std::string 사전에서 허용하는 원본 바이트 토큰입니다.
    raw_key = bytes(data[92:95])
    path.write_bytes(data)
    with closing(FastTextBin(path)) as model:
        assert model.nwords == 2 and len(model._words) == 2
        assert model._words[raw_key] == 0
        assert model.word_id("가") == -1 and model.word_id("</s>") == 1
        np.testing.assert_array_equal(model.get_word_vector("</s>"), matrix[1])
        # 정상 UTF-8 입력은 그대로 인코딩하고, 모르는 단어는 기존 subword를 사용합니다.
        np.testing.assert_array_equal(model.get_word_vector("가"), matrix[2 + 2790065039 % 17])
    assert path.read_bytes() == data


@pytest.mark.parametrize("change", ["duplicate", "empty", "entry_type", "negative_count"])
def test_invalid_dictionary_entries(tmp_path, change):
    path, data, _, _ = write_binary(
        tmp_path, words=("가", "가") if change == "duplicate" else ("가", "</s>")
    )
    if change == "empty":
        data[92] = 0
    elif change == "entry_type":
        data[104] = 1
    elif change == "negative_count":
        struct.pack_into("<q", data, 96, -1)
    path.write_bytes(data)
    with pytest.raises(FastTextFormatError):
        FastTextBin(path)


def test_close_releases_model_and_blocks_further_inference(tmp_path):
    path, _, _, _ = write_binary(tmp_path)
    model = FastTextBin(path)
    model.close()
    model.close()
    with pytest.raises(FastTextFormatError, match="닫혀"):
        model.get_word_vector("가")
    path.unlink()  # Windows에서도 모델 파일 핸들을 닫았는지 확인합니다.
