"""모델 다운로드의 재개·HTTP 범위·원본 보존을 작은 임시 파일로 검사합니다.

실제 네트워크와 models/ 파일은 사용하지 않습니다.
"""
import hashlib
import importlib.util
import io
import json
from pathlib import Path

import pytest


SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "prepare_model.py"
SPEC = importlib.util.spec_from_file_location("prepare_model_download_test", SCRIPT)
prepare = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare)
PAYLOAD = b"abcdef"
URL = "https://example.invalid/model.bin"


class Response:
    """urllib의 상태·헤더·스트림만 흉내 내는 검사 응답입니다."""
    def __init__(self, payload, status=200, headers=None, fail_after=None):
        self.status = status
        self.headers = headers if headers is not None else {"Content-Length": str(len(payload))}
        self.stream = io.BytesIO(payload)
        self.fail_after = fail_after

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.stream.close()

    def read(self, size):
        if self.fail_after is not None:
            left = self.fail_after - self.stream.tell()
            if left <= 0:
                raise OSError("TEST ONLY: interrupted connection")
            size = min(size, left)
        return self.stream.read(size)


@pytest.fixture
def files(tmp_path):
    path = tmp_path / "model.bin"
    path.write_bytes(b"previous model")
    partial = path.with_suffix(".bin.partial")
    item = {"path": "model.bin", "size": len(PAYLOAD), "sha256": hashlib.sha256(PAYLOAD).hexdigest()}
    return path, partial, item


def connect(monkeypatch, *responses):
    """정해 둔 응답 외에는 다운로드하지 못하게 하고 요청 헤더를 기록합니다."""
    pending = iter(responses)
    requests = []

    def urlopen(request, timeout):
        assert timeout == 120
        requests.append(request)
        return next(pending)

    monkeypatch.setattr(prepare.urllib.request, "urlopen", urlopen)
    return requests


@pytest.mark.parametrize("headers", [None, {}], ids=["content-length", "stream-until-eof"])
def test_fresh_download_checks_digest_before_replacing_previous_file(files, monkeypatch, headers):
    path, partial, item = files
    requests = connect(monkeypatch, Response(PAYLOAD, headers=headers))
    prepare.download(path, item, URL)
    assert requests[0].get_header("Range") is None
    assert requests[0].get_header("Accept-encoding") == "identity"
    assert path.read_bytes() == PAYLOAD
    assert not partial.exists()


def test_exact_206_range_resumes_partial_file(files, monkeypatch):
    path, partial, item = files
    partial.write_bytes(PAYLOAD[:3])
    requests = connect(monkeypatch, Response(PAYLOAD[3:], 206,
                       {"Content-Range": "bytes 3-5/6", "Content-Length": "3"}))
    prepare.download(path, item, URL)
    assert requests[0].get_header("Range") == "bytes=3-"
    assert path.read_bytes() == PAYLOAD
    assert not partial.exists()


def test_server_ignoring_range_with_200_restarts_instead_of_appending(files, monkeypatch):
    path, partial, item = files
    partial.write_bytes(b"bad")
    requests = connect(monkeypatch, Response(PAYLOAD))
    prepare.download(path, item, URL)
    assert requests[0].get_header("Range") == "bytes=3-"
    assert path.read_bytes() == PAYLOAD
    assert not partial.exists()


@pytest.mark.parametrize("status,overrides", [
    (206, {"Content-Range": None}),
    (206, {"Content-Range": "bytes 2-5/6"}),
    (206, {"Content-Range": "bytes 3-4/6"}),
    (206, {"Content-Range": "bytes 3-5/7"}),
    (206, {"Content-Range": "bytes 3-5/*"}),
    (206, {"Content-Length": "4"}),
    (206, {"Content-Length": "invalid"}),
    (206, {"Content-Encoding": "gzip"}),
    (200, {}),
    (200, {"Content-Range": None}),
    (201, {}),
], ids=["missing-range", "wrong-start", "wrong-end", "wrong-total", "unknown-total",
        "wrong-length", "invalid-length", "compressed", "range-on-200", "short-200", "wrong-status"])
def test_invalid_headers_preserve_both_partial_and_previous_file(files, monkeypatch, status, overrides):
    path, partial, item = files
    partial.write_bytes(PAYLOAD[:3])
    headers = {"Content-Range": "bytes 3-5/6", "Content-Length": "3", **overrides}
    headers = {key: value for key, value in headers.items() if value is not None}
    connect(monkeypatch, Response(PAYLOAD[3:], status, headers))
    with pytest.raises(prepare.DownloadError):
        prepare.download(path, item, URL)
    assert partial.read_bytes() == PAYLOAD[:3]
    assert path.read_bytes() == b"previous model"


def test_connection_failure_keeps_received_bytes_and_next_run_resumes(files, monkeypatch, capsys):
    path, partial, item = files
    requests = connect(monkeypatch, Response(PAYLOAD, fail_after=3),
                       Response(PAYLOAD[3:], 206, {"Content-Range": "bytes 3-5/6"}))
    with pytest.raises(OSError):
        prepare.download(path, item, URL)
    assert partial.read_bytes() == PAYLOAD[:3]
    assert path.read_bytes() == b"previous model"
    assert "부분 파일 3 bytes를 남겼습니다" in capsys.readouterr().out
    prepare.download(path, item, URL)
    assert requests[1].get_header("Range") == "bytes=3-"
    assert path.read_bytes() == PAYLOAD
    assert not partial.exists()


def test_complete_verified_partial_is_published_without_network(files, monkeypatch):
    path, partial, item = files
    partial.write_bytes(PAYLOAD)
    requests = connect(monkeypatch)
    prepare.download(path, item, URL)
    assert requests == []
    assert path.read_bytes() == PAYLOAD
    assert not partial.exists()


def test_checksum_failure_keeps_old_file_and_next_run_restarts_at_zero(files, monkeypatch, capsys):
    path, partial, item = files
    requests = connect(monkeypatch, Response(b"xxxxxx"), Response(PAYLOAD))
    with pytest.raises(prepare.DownloadError, match="SHA-256"):
        prepare.download(path, item, URL)
    assert partial.read_bytes() == b"xxxxxx"
    assert path.read_bytes() == b"previous model"
    prepare.download(path, item, URL)
    assert requests[1].get_header("Range") is None
    assert "처음부터 다시 받습니다" in capsys.readouterr().out
    assert path.read_bytes() == PAYLOAD
    assert not partial.exists()


def test_truncated_response_keeps_partial_without_replacing_old_file(files, monkeypatch):
    path, partial, item = files
    connect(monkeypatch, Response(PAYLOAD[:3], headers={"Content-Length": "6"}))
    with pytest.raises(prepare.DownloadError, match="모두 받기 전에"):
        prepare.download(path, item, URL)
    assert partial.read_bytes() == PAYLOAD[:3]
    assert path.read_bytes() == b"previous model"


def test_oversized_response_is_not_appended_beyond_manifest_size(files, monkeypatch):
    path, partial, item = files
    partial.write_bytes(PAYLOAD[:3])
    connect(monkeypatch, Response(PAYLOAD[3:] + b"x", 206,
                                {"Content-Range": "bytes 3-5/6", "Content-Length": "3"}))
    with pytest.raises(prepare.DownloadError, match="크기를 초과"):
        prepare.download(path, item, URL)
    assert partial.read_bytes() == PAYLOAD[:3]
    assert path.read_bytes() == b"previous model"


def test_oversized_existing_partial_restarts_at_zero(files, monkeypatch):
    path, partial, item = files
    partial.write_bytes(PAYLOAD + b"x")
    requests = connect(monkeypatch, Response(PAYLOAD))
    prepare.download(path, item, URL)
    assert requests[0].get_header("Range") is None
    assert path.read_bytes() == PAYLOAD
    assert not partial.exists()


def arguments(monkeypatch, tmp_path, item, *extra):
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"model_id": "example/model", "revision": "fixed-version",
                                    "algorithm": "fasttext-bin-subword-mean-l2-cosine100-v1",
                                    "directory": "unused", "files": [item]}), encoding="utf-8")
    monkeypatch.setattr("sys.argv", [str(SCRIPT), "--manifest", str(manifest),
                                    "--directory", str(tmp_path), *extra])


def test_check_mode_uses_manifest_and_never_downloads_or_changes_partial(files, monkeypatch, tmp_path):
    path, partial, item = files
    path.write_bytes(PAYLOAD)
    partial.write_bytes(b"unfinished")
    requests = connect(monkeypatch)
    arguments(monkeypatch, tmp_path, item, "--check")
    prepare.main()
    assert requests == []
    assert path.read_bytes() == PAYLOAD
    assert partial.read_bytes() == b"unfinished"


def test_main_does_not_print_network_exception_url_or_token(files, monkeypatch, tmp_path, capsys):
    path, partial, item = files
    partial.write_bytes(PAYLOAD[:3])
    arguments(monkeypatch, tmp_path, item)

    def failed_request(*_, **__):
        raise OSError("https://example.invalid/file?token=TEST_PRIVATE_VALUE")

    monkeypatch.setattr(prepare.urllib.request, "urlopen", failed_request)
    with pytest.raises(SystemExit) as failure:
        prepare.main()
    assert "OSError" in str(failure.value)
    assert "TEST_PRIVATE_VALUE" not in str(failure.value) + capsys.readouterr().out
    assert partial.read_bytes() == PAYLOAD[:3]
    assert path.read_bytes() == b"previous model"
