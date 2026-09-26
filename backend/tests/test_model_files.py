"""실제 작은 파일로 모델 검증 캐시의 재사용·무효화·읽기 전용 동작을 검사합니다."""
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import stat
import time

import pytest

from app import model_files

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_model.py"
SPEC = importlib.util.spec_from_file_location("prepare_model_cache_test", SCRIPT)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)


@pytest.fixture
def model(tmp_path):
    payload = b"small original model"
    path = tmp_path / "model.bin"
    path.write_bytes(payload)
    item = {"path": "model.bin", "size": len(payload),
            "sha256": hashlib.sha256(payload).hexdigest()}
    return path, item


@pytest.fixture
def hashes(monkeypatch):
    calls = []
    original = model_files._sha256

    def counted(path):
        calls.append(path)
        return original(path)

    monkeypatch.setattr(model_files, "_sha256", counted)
    return calls


def test_full_hash_once_then_identical_local_file_reuses_cache(model, hashes):
    path, item = model
    assert model_files.verify_file(path, item)
    assert hashes == [path]
    assert not (path.parent / model_files.CACHE_NAME).exists()
    assert model_files.remember_verified(path, item)
    assert hashes == [path]  # 전체 검증을 마친 호출자용 발행 함수는 재해시하지 않습니다.
    assert model_files.verify_file(path, item)
    assert hashes == [path]
    if os.name != "nt":
        assert stat.S_IMODE((path.parent / model_files.CACHE_NAME).stat().st_mode) == 0o644


def test_same_size_changed_content_invalidates_cached_mtime(model, hashes):
    path, item = model
    assert model_files.verify_file(path, item)
    assert model_files.remember_verified(path, item)
    previous = path.stat()
    path.write_bytes(b"x" * item["size"])
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000_000))
    assert not model_files.verify_file(path, item)
    assert hashes == [path, path]


@pytest.mark.skipif(os.name == "nt", reason="Windows ctime은 생성 시각이므로 Linux 변경 시각 검사와 다릅니다.")
def test_restoring_mtime_does_not_hide_changed_ctime(model, hashes):
    path, item = model
    assert model_files.verify_file(path, item)
    assert model_files.remember_verified(path, item)
    previous = path.stat()
    time.sleep(0.01)
    path.write_bytes(b"x" * item["size"])
    os.utime(path, ns=(previous.st_atime_ns, previous.st_mtime_ns))
    assert path.stat().st_mtime_ns == previous.st_mtime_ns
    assert path.stat().st_ctime_ns != previous.st_ctime_ns
    assert not model_files.verify_file(path, item)
    assert hashes == [path, path]


@pytest.mark.parametrize("broken", [
    b"{", b"\xff", b'{"format":2,"files":{}}', b'{"format":1,"files":[]}',
    b" " * (64 * 1024 + 1), b"[" * 2000 + b"]" * 2000,
])
def test_missing_or_unreadable_cache_format_falls_back_to_full_sha(model, hashes, broken):
    path, item = model
    cache = path.parent / model_files.CACHE_NAME
    cache.write_bytes(broken)
    assert model_files.verify_file(path, item)
    assert hashes == [path]
    assert cache.read_bytes() == broken  # 읽기 경로는 손상된 캐시조차 수정하지 않습니다.


def test_changed_expected_sha_never_reuses_old_verified_entry(model, hashes):
    path, item = model
    assert model_files.verify_file(path, item)
    assert model_files.remember_verified(path, item)
    changed = {**item, "sha256": hashlib.sha256(b"x" * item["size"]).hexdigest()}
    assert not model_files.verify_file(path, changed)
    assert hashes == [path, path]


def test_copy_with_preserved_mtime_requires_full_hash(model, tmp_path, hashes):
    path, item = model
    assert model_files.verify_file(path, item)
    assert model_files.remember_verified(path, item)
    other = tmp_path / "copied"
    other.mkdir()
    copied = other / path.name
    shutil.copy2(path, copied)
    shutil.copy2(path.parent / model_files.CACHE_NAME, other / model_files.CACHE_NAME)
    assert copied.stat().st_mtime_ns == path.stat().st_mtime_ns
    assert copied.stat().st_ino != path.stat().st_ino
    assert model_files.verify_file(copied, item)
    assert hashes == [path, copied]


def test_runtime_never_attempts_cache_writes_on_hit_or_miss(model, hashes, monkeypatch):
    path, item = model
    assert model_files.verify_file(path, item)
    assert model_files.remember_verified(path, item)
    cache = path.parent / model_files.CACHE_NAME
    original = cache.read_bytes()

    def forbidden(*_, **__):
        pytest.fail("읽기 전용 앱이 캐시 기록을 시도했습니다.")

    monkeypatch.setattr(model_files, "remember_verified", forbidden)
    monkeypatch.setattr(model_files.tempfile, "NamedTemporaryFile", forbidden)
    monkeypatch.setattr(model_files.os, "replace", forbidden)
    assert model_files.verify_file(path, item)
    assert hashes == [path]
    assert cache.read_bytes() == original
    cache.unlink()
    assert model_files.verify_file(path, item)
    assert hashes == [path, path]
    assert not cache.exists()


def test_nested_model_paths_share_one_cache_without_absolute_mount_keys(tmp_path, hashes):
    flat = tmp_path / "tokenizer.json"
    nested = tmp_path / "onnx" / "model_quantized.onnx"
    nested.parent.mkdir()
    for path in (flat, nested):
        payload = path.name.encode()
        path.write_bytes(payload)
        item = {"path": path.relative_to(tmp_path).as_posix(), "size": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest()}
        assert model_files.verify_file(path, item)
        assert model_files.remember_verified(path, item)
        assert model_files.verify_file(path, item)
    cache = json.loads((tmp_path / model_files.CACHE_NAME).read_text(encoding="utf-8"))
    assert set(cache["files"]) == {"tokenizer.json", "onnx/model_quantized.onnx"}
    assert hashes == [flat, nested]
    assert not (nested.parent / model_files.CACHE_NAME).exists()


def test_file_change_during_full_hash_is_rejected_even_when_digest_matches(model, monkeypatch):
    path, item = model
    original = model_files._sha256

    def changed_during_hash(target):
        digest = original(target)
        previous = target.stat()
        target.write_bytes(b"x" * item["size"])
        os.utime(target, ns=(previous.st_atime_ns, previous.st_mtime_ns + 1_000_000_000))
        return digest

    monkeypatch.setattr(model_files, "_sha256", changed_during_hash)
    assert not model_files.verify_file(path, item)


def test_explicit_full_validation_ignores_an_existing_cache(model, hashes):
    path, item = model
    assert model_files.verify_file(path, item)
    assert model_files.remember_verified(path, item)
    assert prepare.validate(path, item)
    assert hashes == [path, path]


def test_optional_cache_write_failure_does_not_accept_bad_model(model, monkeypatch):
    path, item = model
    assert model_files.verify_file(path, item)

    def read_only(*_, **__):
        raise PermissionError("test read-only directory")

    monkeypatch.setattr(model_files.tempfile, "NamedTemporaryFile", read_only)
    assert not model_files.remember_verified(path, item)
    assert model_files.verify_file(path, item)
    path.write_bytes(b"x" * item["size"])
    assert not model_files.verify_file(path, item)
    assert not (path.parent / model_files.CACHE_NAME).exists()


@pytest.mark.parametrize("check", [False, True], ids=["prepare-publishes", "check-is-read-only"])
def test_prepare_existing_file_and_check_mode_both_run_full_sha(model, hashes, monkeypatch, check):
    path, item = model
    manifest = path.parent / "manifest.json"
    manifest.write_text(json.dumps({"model_id": "test/model", "revision": "fixed",
                                   "algorithm": "fasttext-bin-subword-mean-l2-cosine100-v1",
                                   "directory": "unused", "files": [item]}), encoding="utf-8")
    args = [str(SCRIPT), "--manifest", str(manifest), "--directory", str(path.parent)]
    if check:
        args.append("--check")
    monkeypatch.setattr("sys.argv", args)
    prepare.main()
    assert hashes == [path]
    assert (path.parent / model_files.CACHE_NAME).exists() is not check


def test_download_publishes_cache_for_final_file_after_full_partial_validation(model, hashes, monkeypatch):
    path, item = model
    payload = path.read_bytes()
    path.write_bytes(b"previous model")

    class Response(io.BytesIO):
        status = 200
        headers = {"Content-Length": str(len(payload))}

    monkeypatch.setattr(prepare.urllib.request, "urlopen", lambda *_args, **_kwargs: Response(payload))
    prepare.download(path, item, "https://example.invalid/model.bin")
    assert path.read_bytes() == payload
    assert hashes == [path.with_suffix(".bin.partial")]
    assert model_files.verify_file(path, item)
    assert hashes == [path.with_suffix(".bin.partial")]
