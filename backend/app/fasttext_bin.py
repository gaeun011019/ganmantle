"""fastText v12 비양자화 .bin의 입력 행렬만 읽기 전용으로 연결합니다.

학습·분류·양자화·축약 사전은 지원하지 않습니다. 원본 출력 행렬은 적재하지
않습니다. 파일 SHA-256과 버전 고정은 호출하는 SimilarityEngine의 책임입니다.
형식과 subword 계산은 공식 v0.9.2 args.cc/dictionary.cc/fasttext.cc를 따릅니다.
https://github.com/facebookresearch/fastText/tree/v0.9.2/src

MIT License — Copyright (c) 2016-present, Facebook, Inc.
Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:
The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.
THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
from __future__ import annotations

import mmap
from pathlib import Path
import struct

import numpy as np


class FastTextFormatError(ValueError):
    """지원하지 않거나 손상된 원본 파일입니다."""


class FastTextVectorError(ValueError):
    """해당 입력을 계산할 정보가 없거나 결과가 유한한 0벡터입니다."""


def _hash(data: bytes) -> int:
    """공식 호환 FNV-1a: UTF-8 바이트를 unsigned가 아닌 signed int8로 해석."""
    value = 2166136261
    for byte in data:
        value = ((value ^ (byte if byte < 128 else byte - 256)) * 16777619) & 0xFFFFFFFF
    return value


class FastTextBin:
    """CC/Wiki 계열의 비양자화 CBOW/skip-gram 모델에서 단어 벡터를 구합니다."""

    def __init__(self, filename: str | Path) -> None:
        self._input = None
        self._words: dict[bytes, int] = {}  # 전체 단어의 UTF-8 키와 ID만 보관합니다.
        with Path(filename).open("rb") as stream:
            stream.seek(0, 2)
            if stream.tell() < 8:
                raise FastTextFormatError("fastText 파일 헤더가 잘렸습니다.")
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                offset = 0

                def read(fmt: str):
                    nonlocal offset
                    length = struct.calcsize(fmt)
                    if offset + length > len(data):
                        raise FastTextFormatError("fastText 파일 필드가 잘렸습니다.")
                    values = struct.unpack_from(fmt, data, offset)
                    offset += length
                    return values

                magic, version = read("<ii")
                if magic != 793712314 or version != 12:
                    raise FastTextFormatError("fastText magic 793712314, 버전 12만 지원합니다.")
                args = read("<12id")
                self.dimension, self.bucket, self.minn, self.maxn = args[0], args[8], args[9], args[10]
                if args[7] not in (1, 2):
                    raise FastTextFormatError("fastText 단어벡터 CBOW/skip-gram 모델만 지원합니다.")
                if not (1 <= self.dimension <= 4096 and self.bucket > 0
                        and 1 <= self.minn <= self.maxn <= 256
                        and args[6] in (1, 2, 3, 4)
                        and args[1] > 0 and args[2] > 0 and args[3] >= 0
                        and args[4] >= 0 and args[5] > 0 and args[11] > 0
                        and np.isfinite(args[12]) and args[12] >= 0):
                    raise FastTextFormatError("fastText 차원·subword·학습 설정 필드가 잘못되었습니다.")
                size, self.nwords, nlabels, ntokens, pruned = read("<iiiqq")
                if not (size == self.nwords > 0 and nlabels == 0 and ntokens >= 0
                        and size <= (len(data) - offset) // 10):
                    raise FastTextFormatError("fastText 사전 개수·유형·크기가 잘못되었습니다.")
                if pruned != -1:
                    raise FastTextFormatError("축약된 fastText 사전은 지원하지 않습니다.")
                for index in range(size):
                    end = data.find(b"\0", offset, min(len(data), offset + 65537))
                    if end <= offset:
                        raise FastTextFormatError("fastText 사전 단어의 끝이나 길이가 잘못되었습니다.")
                    word = data[offset:end]
                    # 공식 std::string 사전은 UTF-8이 아닌 토큰도 보존합니다.
                    # 원본 bytes를 유지해야 단어 ID와 행렬 행 번호가 바뀌지 않습니다.
                    offset = end + 1
                    count, kind = read("<qb")
                    if count < 0 or kind != 0 or word in self._words:
                        raise FastTextFormatError("fastText 사전 항목의 유형·빈도·중복이 잘못되었습니다.")
                    self._words[word] = index
                if read("<B")[0] != 0:
                    raise FastTextFormatError("양자화된 fastText 입력 행렬은 지원하지 않습니다.")
                rows, columns = read("<qq")
                if (rows, columns) != (self.nwords + self.bucket, self.dimension):
                    raise FastTextFormatError("fastText 입력 행렬 크기가 사전·차원과 다릅니다.")
                input_offset = offset
                offset += rows * columns * 4
                if read("<B")[0] != 0:
                    raise FastTextFormatError("양자화된 fastText 출력 행렬은 지원하지 않습니다.")
                output_rows, output_columns = read("<qq")
                if (output_rows, output_columns) != (self.nwords, self.dimension):
                    raise FastTextFormatError("fastText 출력 행렬 크기가 사전·차원과 다릅니다.")
                if offset + output_rows * output_columns * 4 != len(data):
                    raise FastTextFormatError("fastText 행렬 데이터가 잘렸거나 파일 뒤에 추가 데이터가 있습니다.")
                # 사전 스캔용 mmap은 곧 닫고, input 행렬만 별도 연결합니다.
                self._input = np.memmap(stream, dtype="<f4", mode="r", offset=input_offset,
                                        shape=(rows, columns), order="C")
                # 희소한 단어 행 조회에서 Linux의 불필요한 순차 미리 읽기를 줄입니다.
                try:
                    self._input._mmap.madvise(mmap.MADV_RANDOM)
                except (AttributeError, OSError):
                    pass  # 지원하지 않는 환경에서도 계산 방식과 결과는 같습니다.

    def word_id(self, word: str) -> int:
        """모델 사전에 없으면 -1입니다. 게임의 입력 허용 사전과는 다릅니다."""
        return self._words.get(word.encode("utf-8"), -1)

    def _subword_ids(self, word: str) -> list[int]:
        encoded = word.encode("utf-8")
        known = self._words.get(encoded, -1)
        ids = [known] if known >= 0 else []
        if word == "</s>":
            return ids
        wrapped = b"<" + encoded + b">"
        for start in range(len(wrapped)):
            if wrapped[start] & 0xC0 == 0x80:
                continue  # UTF-8 연속 바이트에서 새 글자를 시작하지 않습니다.
            end = start
            for length in range(1, self.maxn + 1):
                if end >= len(wrapped):
                    break
                end += 1
                while end < len(wrapped) and wrapped[end] & 0xC0 == 0x80:
                    end += 1
                if length >= self.minn and not (length == 1 and (start == 0 or end == len(wrapped))):
                    ids.append(self.nwords + _hash(wrapped[start:end]) % self.bucket)
        return ids  # 같은 hash가 반복돼도 횟수를 보존해야 공식 평균과 같습니다.

    def get_word_vector(self, word: str) -> np.ndarray:
        """원본 input의 word/subword 행 평균을 float32로 반환합니다(L2 정규화 전)."""
        if self._input is None:
            raise FastTextFormatError("fastText 모델이 닫혀 있습니다.")
        if not isinstance(word, str) or not word or "\0" in word:
            raise FastTextVectorError("fastText에 계산할 단어가 필요합니다.")
        ids = self._subword_ids(word)
        if not ids:
            raise FastTextVectorError("모델이 이 단어의 subword 벡터를 만들 수 없습니다.")
        vector = np.zeros(self.dimension, dtype=np.float32)
        try:
            with np.errstate(over="raise", invalid="raise"):
                for index in ids:
                    np.add(vector, self._input[index], out=vector)
                vector *= np.float32(1.0 / len(ids))
        except FloatingPointError as exc:
            raise FastTextFormatError("fastText 벡터 계산이 유한한 범위를 벗어났습니다.") from exc
        # 손상된 수치는 입력 미지원으로 제외하면 안 됩니다. 모델 준비 전체를 중단합니다.
        if not np.isfinite(vector).all():
            raise FastTextFormatError("fastText 입력 행렬에 유효하지 않은 수치가 있습니다.")
        if not np.any(vector):
            raise FastTextVectorError("fastText가 유한한 0벡터를 만들었습니다.")
        return vector

    def close(self) -> None:
        """검사·모델 교체 시 Windows 파일 핸들도 즉시 해제합니다."""
        if self._input is not None:
            self._input._mmap.close()
            self._input = None
        self._words.clear()
