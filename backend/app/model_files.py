"""모델 전체 SHA-256 검사와 선택적인 로컬 검증 캐시. 표준 라이브러리만 사용합니다.

캐시는 같은 기대 해시/크기와 파일 식별 정보가 모두 같을 때만 재사용합니다.
로컬 관리자가 파일과 캐시를 함께 조작하는 공격의 암호학적 방어 수단은 아닙니다.
앱의 verify_file은 읽기만 하며, 쓰기 가능한 준비 도구만 remember_verified를 호출합니다.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import tempfile

CACHE_NAME = ".verified-model.json"
_MAX_CACHE_BYTES = 64 * 1024
_STAT_FIELDS = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")


def _record(path: Path, item: dict) -> dict | None:
    """파일의 현재 상태와 기대값을 묶습니다. 누락/잘못된 크기는 캐시할 수 없습니다."""
    expected_size = item.get("size")
    expected_sha = item.get("sha256")
    if type(expected_size) is not int or expected_size < 0:
        return None
    if not isinstance(expected_sha, str) or not re.fullmatch(r"[0-9a-f]{64}", expected_sha):
        return None
    try:
        info = path.stat()
    except OSError:
        return None
    if not stat.S_ISREG(info.st_mode) or info.st_size != expected_size:
        return None
    return {"expected_sha256": expected_sha, "expected_size": expected_size,
            **{name: getattr(info, name) for name in _STAT_FIELDS}}


def _cache_location(path: Path, item: dict) -> tuple[Path, str] | None:
    """상대 모델 경로를 키로 사용해 /model-work와 /models 마운트에서도 재사용합니다."""
    relative = item.get("path")
    if not isinstance(relative, str) or "\\" in relative:
        return None
    parts = PurePosixPath(relative).parts
    if not parts or PurePosixPath(relative).is_absolute() or ".." in parts:
        return None
    if tuple(path.parts[-len(parts):]) != parts:
        return None
    root = path
    for _ in parts:
        root = root.parent
    return root / CACHE_NAME, "/".join(parts)


def _read_cache(path: Path) -> dict:
    try:
        with path.open("rb") as stream:
            raw = stream.read(_MAX_CACHE_BYTES + 1)
        if len(raw) > _MAX_CACHE_BYTES:
            return {}
        value = json.loads(raw)
        if (not isinstance(value, dict) or type(value.get("format")) is not int
                or value["format"] != 1 or not isinstance(value.get("files"), dict)):
            return {}
        return value["files"]
    except (OSError, ValueError, UnicodeError, RecursionError):
        return {}


def _matches(entry: object, record: dict) -> bool:
    return (isinstance(entry, dict) and entry.keys() == record.keys()
            and all(type(entry[key]) is type(value) and entry[key] == value
                    for key, value in record.items()))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify_file(path: Path, item: dict, *, use_cache: bool = True) -> bool:
    """읽기 전용 검증. 캐시를 못 쓰면 전체 파일을 읽으며 캐시를 기록하지 않습니다."""
    path = Path(path)
    before = _record(path, item)
    if before is None:
        return False
    location = _cache_location(path, item) if use_cache else None
    if location is not None:
        cache_path, key = location
        if _matches(_read_cache(cache_path).get(key), before):
            return _record(path, item) == before
    try:
        digest = _sha256(path)
    except OSError:
        return False
    # 검증 도중 교체되거나 수정된 파일은 원래 해시가 맞아도 통과시키지 않습니다.
    return digest == item["sha256"] and _record(path, item) == before


def remember_verified(path: Path, item: dict) -> bool:
    """전체 SHA 검증 성공과 최종 rename을 마친 호출자만 사용합니다. 재해시하지 않습니다.

    item은 model-manifest.json files[]의 원본 항목입니다. 쓰기 실패 시 False를 반환하며
    모델 검증 성공 자체는 취소하지 않습니다. 이 함수만 호출해 파일을 검증하면 안 됩니다.
    """
    path = Path(path)
    location = _cache_location(path, item)
    record = _record(path, item)
    if location is None or record is None:
        return False
    cache_path, key = location
    entries = _read_cache(cache_path)
    if _matches(entries.get(key), record):
        return True
    entries[key] = record
    data = json.dumps({"format": 1, "files": entries}, ensure_ascii=False,
                      sort_keys=True, separators=(",", ":")) + "\n"
    if len(data.encode("utf-8")) > _MAX_CACHE_BYTES:
        return False
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", newline="\n",
                                         prefix=".verified-model-", suffix=".tmp",
                                         dir=cache_path.parent, delete=False) as output:
            temporary = Path(output.name)
            output.write(data)
        # root로 준비해도 권한이 제한된 런타임 사용자가 캐시를 읽을 수 있어야 합니다.
        temporary.chmod(0o644)
        os.replace(temporary, cache_path)
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass
