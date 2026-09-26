"""한글 입력 형식과 고정 비교 사전. fastText는 형식이 맞는 사전 밖 입력도 허용합니다."""
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import re
import unicodedata

WORDS_PATH = Path(__file__).with_name("dictionary") / "words.txt"
MANIFEST_PATH = WORDS_PATH.with_name("manifest.json")
HANGUL_WORD = re.compile(r"[가-힣]{1,40}")


class WordsUnavailableError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_words() -> frozenset[str]:
    """버전·해시가 고정된 작은 사전을 한 번 읽습니다. 실패 시 입력을 통과시키지 않습니다."""
    try:
        content = WORDS_PATH.read_bytes()
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        if hashlib.sha256(content).hexdigest() != manifest["output"]["sha256"]:
            raise ValueError("사전 체크섬 불일치")
        words = frozenset(content.decode("utf-8").splitlines())
        if not words or len(words) != manifest["output"]["count"]:
            raise ValueError("사전 단어 수 불일치")
        if any(not HANGUL_WORD.fullmatch(word) or unicodedata.normalize("NFC", word) != word for word in words):
            raise ValueError("사전 형식 오류")
        return words
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise WordsUnavailableError("입력 사전을 준비하지 못했어요. 서버의 dictionary 파일을 확인해 주세요.") from exc


def is_allowed_word(word: str, *, allow_oov: bool = False) -> bool:
    word = unicodedata.normalize("NFC", word.strip())
    return bool(HANGUL_WORD.fullmatch(word)) and (allow_oov or word in get_words())
