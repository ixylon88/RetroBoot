"""Fetch verified, fixed compiler sources/binaries into build/toolchain (Linux x64)."""

import hashlib
import json
import platform
import shutil
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOOLCHAIN = ROOT / "build" / "toolchain"
LOCK = ROOT / "tools" / "toolchain-lock.json"


def sha256(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def verify(path, expected):
    if not path.is_file() or sha256(path) != expected:
        raise ValueError(f"Checksum mismatch: {path}")


def download(info, path):
    if path.exists():
        verify(path, info["sha256"])
        return
    temporary = path.with_suffix(path.suffix + ".partial")
    print(f"Downloading {path.name}", flush=True)
    request = urllib.request.Request(info["url"], headers={"User-Agent": "RetroBoot-build"})
    try:
        with urllib.request.urlopen(request, timeout=60) as source, temporary.open("wb") as target:
            shutil.copyfileobj(source, target, length=1024 * 1024)
        verify(temporary, info["sha256"])
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def main():
    if sys.version_info < (3, 12):
        raise ValueError("Python 3.12 or later is required")
    if platform.system() != "Linux" or platform.machine() not in ("x86_64", "amd64"):
        raise ValueError("The pinned native toolchain currently requires Linux x86_64")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    cache = TOOLCHAIN / "downloads"
    cache.mkdir(parents=True, exist_ok=True)
    ow_archive, nasm_archive = cache / "watcom.tar.xz", cache / "nasm.tar.xz"
    download(lock["open_watcom"], ow_archive)
    download(lock["nasm"], nasm_archive)
    ow_dir = TOOLCHAIN / "watcom"
    ow_dir.mkdir(exist_ok=True)
    # Extract only these two regular files, ignoring every other archive path.
    with tarfile.open(ow_archive) as archive:
        for name, digest in lock["open_watcom"]["executables"].items():
            member = archive.getmember(f"./binl64/{name}")
            if not member.isfile():
                raise ValueError(f"Expected a regular compiler executable: {name}")
            destination = ow_dir / name
            with archive.extractfile(member) as source, destination.open("wb") as target:
                shutil.copyfileobj(source, target)
            verify(destination, digest)
            destination.chmod(0o755)

    source_dir = TOOLCHAIN / ("nasm-" + lock["nasm"]["version"])
    with tarfile.open(nasm_archive) as archive:
        archive.extractall(TOOLCHAIN, filter="data")
    subprocess.run(["./configure"], cwd=source_dir, check=True)
    subprocess.run(["make", "-j2", "nasm"], cwd=source_dir, check=True)
    (source_dir / "nasm").chmod(0o755)
    print(f"Toolchain ready: {TOOLCHAIN}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, tarfile.TarError, subprocess.CalledProcessError) as error:
        print(f"Toolchain setup: {error}", file=sys.stderr)
        sys.exit(1)
