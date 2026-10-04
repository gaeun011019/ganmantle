"""간맨틀: 고정 모델을 내려받고 바이트 크기와 SHA-256을 검증한다. 표준 라이브러리만 사용."""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import re
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.model_files import remember_verified, verify_file


class DownloadError(RuntimeError):
    """URL이나 인증 정보를 포함하지 않는 다운로드 검증 오류입니다."""


def validate(path: Path, item: dict) -> bool:
    """명시적 준비/--check/부분 파일 검증은 캐시와 무관하게 전체 SHA를 확인합니다."""
    return verify_file(path, item, use_cache=False)


def save_verification(path: Path, item: dict) -> None:
    """전체 검증과 최종 파일 교체 뒤 선택 캐시를 기록합니다."""
    if not remember_verified(path, item):
        print(
            "모델 검증은 완료했지만 캐시를 저장하지 못했습니다. 다음 시작 시 전체 검증합니다.",
            flush=True,
        )


def download(path: Path, item: dict, url: str) -> None:
    """부분 파일을 이어받고 검증된 파일만 교체합니다. 메모리 사용량은 파일 크기와 무관합니다."""
    partial = path.with_suffix(path.suffix + ".partial")
    expected = item["size"]
    offset = partial.stat().st_size if partial.is_file() else 0
    if offset >= expected:
        if validate(partial, item):
            partial.replace(path)
            save_verification(path, item)
            print(f"이미 받은 부분 파일 검증 완료: {item['path']}", flush=True)
            return
        # 완성 크기의 손상 파일은 Range로 복구할 수 없습니다. 다음 실행은 0부터 받습니다.
        # 새 응답을 검증하기 전에는 이 파일도 지우거나 비우지 않습니다.
        print(
            f"부분 파일 크기 또는 SHA-256 검증 실패: {item['path']} — 처음부터 다시 받습니다.",
            flush=True,
        )
        offset = 0
    headers = {"User-Agent": "ganmantle-model-preparation/1", "Accept-Encoding": "identity"}
    if offset:
        headers["Range"] = f"bytes={offset}-"
    request = urllib.request.Request(url, headers=headers)
    print(f"다운로드: {item['path']} ({offset:,}/{expected:,} bytes부터)", flush=True)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.headers.get("Content-Encoding", "identity").lower() != "identity":
                raise DownloadError("압축된 HTTP 응답은 파일 바이트 범위와 비교할 수 없습니다.")
            if response.status == 206:
                content_range = response.headers.get("Content-Range", "")
                match = re.fullmatch(r"bytes ([0-9]+)-([0-9]+)/([0-9]+)", content_range)
                if not match or tuple(map(int, match.groups())) != (offset, expected - 1, expected):
                    raise DownloadError("HTTP Content-Range가 요청 범위 또는 모델 크기와 다릅니다.")
                received = offset
                mode = "ab" if offset else "wb"
            elif response.status == 200:
                if response.headers.get("Content-Range") is not None:
                    raise DownloadError("HTTP 200 응답에 잘못된 Content-Range가 있습니다.")
                # Range를 지원하지 않는 서버는 전체 파일을 보냅니다. 이어 붙이지 않습니다.
                received = 0
                mode = "wb"
            else:
                raise DownloadError(f"지원하지 않는 HTTP 응답 상태: {response.status}")
            content_length = response.headers.get("Content-Length")
            if content_length is not None and (
                not re.fullmatch(r"[0-9]+", content_length)
                or int(content_length) != expected - received
            ):
                raise DownloadError("HTTP Content-Length가 받을 모델 바이트 수와 다릅니다.")
            with partial.open(mode) as output:
                while data := response.read(min(1024 * 1024, expected - received + 1)):
                    if received + len(data) > expected:
                        raise DownloadError("HTTP 응답 본문이 모델 명세의 크기를 초과했습니다.")
                    output.write(data)
                    received += len(data)
            if received != expected:
                raise DownloadError("HTTP 응답이 모델 파일을 모두 받기 전에 끝났습니다.")
        if not validate(partial, item):
            raise DownloadError("받은 파일의 크기 또는 SHA-256이 모델 명세와 다릅니다.")
        # 검증된 새 파일만 원자적으로 교체합니다. 실패하면 기존 최종 파일을 보존합니다.
        partial.replace(path)
        save_verification(path, item)
    except (Exception, KeyboardInterrupt):
        kept = partial.stat().st_size if partial.is_file() else 0
        print(
            f"다운로드 중단: {item['path']} — 부분 파일 {kept:,} bytes를 남겼습니다. 같은 명령으로 다시 시도하세요.",
            flush=True,
        )
        raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="다운로드 없이 기존 파일만 확인")
    parser.add_argument("--directory", help="다른 모델 저장 경로")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=ROOT / "model-manifest.json",
        help="준비할 fastText 모델 명세",
    )
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    if manifest["algorithm"] != "fasttext-bin-subword-mean-l2-cosine100-v1":
        raise SystemExit("fastText .bin 모델 명세가 필요합니다.")
    destination = Path(args.directory or os.getenv("MODEL_DIR", str(ROOT / manifest["directory"])))
    for item in manifest["files"]:
        path = destination / item["path"]
        if validate(path, item):
            if not args.check:
                save_verification(path, item)
            print(f"검증 완료: {item['path']} ({item['size']:,} bytes)", flush=True)
            continue
        if args.check:
            raise SystemExit(f"모델 파일 누락 또는 검증 실패: {path}")
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://huggingface.co/{manifest['model_id']}/resolve/{manifest['revision']}/{item['path']}"
        try:
            download(path, item, url)
        except KeyboardInterrupt:
            raise SystemExit(
                "다운로드를 중단했습니다. 부분 파일을 남겼으므로 같은 명령으로 재개할 수 있습니다."
            ) from None
        except Exception as error:
            # 네트워크 예외의 URL/헤더에는 일시적인 인증 값이 있을 수 있어 출력하지 않습니다.
            reason = str(error) if isinstance(error, DownloadError) else type(error).__name__
            raise SystemExit(f"모델 다운로드 실패: {item['path']} ({reason})") from None
        print(f"저장 및 SHA-256 검증 완료: {path}", flush=True)
    print(f"간맨틀 모델 준비 완료: {destination}", flush=True)


if __name__ == "__main__":
    main()
