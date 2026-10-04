"""동봉한 고정 버전 사전에서 허용 단어를 재생성합니다. 외부 접속/추가 패키지는 없습니다."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import unicodedata

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "backend" / "app" / "dictionary"
REVISION = "07c339220d92ce06ccbae62a345c7314a7e724ce"
SOURCE_SHA256 = "70f577f2e4683df5b0a2ede0981970da9646088a0c6811b2a174c52139566adc"
ALLOWED_POS = {"명사", "대명사", "수사", "동사", "형용사", "부사", "관형사", "감탄사"}


def build():
    source = (DIRECTORY / "source.yaml").read_bytes()
    if hashlib.sha256(source).hexdigest() != SOURCE_SHA256:
        raise ValueError("고정 원본 사전의 SHA-256이 다릅니다. 출처와 버전을 먼저 확인하세요.")
    # 범용 YAML 파서가 아닙니다. 체크섬으로 고정한 원본의 pos/word 레코드만 읽습니다.
    words, forbidden = set(), set()
    position = None
    count = 0
    for line in source.decode("utf-8").splitlines():
        if line.startswith("- pos: "):
            position = line.removeprefix("- pos: ")
        elif line.startswith("  word: "):
            count += 1
            word = unicodedata.normalize("NFC", line.removeprefix("  word: "))
            if position == "특수:금지어":
                forbidden.add(word)
            if position in ALLOWED_POS and re.fullmatch(r"[가-힣]{1,40}", word):
                words.add(word)
    if count != 53817:
        raise ValueError("원본 레코드 수가 다릅니다. 추출 형식을 다시 확인하세요.")
    words.difference_update(forbidden)
    answers = {
        line.strip()
        for line in (ROOT / "backend/app/answers.txt").read_text(encoding="utf-8-sig").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }
    if not answers.issubset(words):
        raise ValueError(
            "정답 후보 중 허용 사전에 없는 단어가 있습니다. 사전/정답 후보를 함께 검토하세요."
        )
    output = ("\n".join(sorted(words)) + "\n").encode("utf-8")
    manifest = {
        "name": "hunspell-dict-ko 표제어",
        "version": "0.7.94",
        "revision": REVISION,
        "license": "GPL-3.0-or-later",
        "source": {
            "url": f"https://raw.githubusercontent.com/spellcheck-ko/hunspell-dict-ko/{REVISION}/dict-ko-data.yaml",
            "path": "source.yaml",
            "sha256": SOURCE_SHA256,
            "size": len(source),
            "entries": count,
        },
        "rules": {
            "parts_of_speech": sorted(ALLOWED_POS),
            "format": "NFC [가-힣]{1,40}",
            "exclude_forbidden": True,
        },
        "output": {
            "path": "words.txt",
            "count": len(words),
            "size": len(output),
            "sha256": hashlib.sha256(output).hexdigest(),
        },
    }
    return output, (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="파일을 바꾸지 않고 재생성 결과와 비교"
    )
    args = parser.parse_args()
    output, manifest = build()
    for name, content in (("words.txt", output), ("manifest.json", manifest)):
        target = DIRECTORY / name
        if args.check:
            if not target.is_file() or target.read_bytes() != content:
                raise SystemExit(f"사전 검사 실패: {name}")
        else:
            target.write_bytes(content)
    print(
        f"사전 {'검사' if args.check else '생성'} 통과: {len(output.splitlines()):,}개, {len(output):,}바이트"
    )
