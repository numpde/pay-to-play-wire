"""Acquire and verify the exact wheel closure, independently of receipts.

Selected wheel-only owners from the recorded upstream wheelhouse implementation.
"""

from tools.ops.container_guard import require_container

require_container()

import argparse
import ctypes
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import urllib.request
from contextlib import contextmanager
from pathlib import Path


@contextmanager
def regular_file(path, flags):
    descriptor = os.open(path, flags | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600)
    try:
        if not stat.S_ISREG(os.fstat(descriptor).st_mode):
            raise ValueError(f"Cannot use {str(path)!r}: artifact must be a regular file")
        with os.fdopen(descriptor, "rb", closefd=False) as stream:
            yield stream
    finally:
        os.close(descriptor)


def fsync_directory(path):
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def publish_directory(staged, output):
    """Publish a complete Linux directory without replacing an existing path."""
    libc = ctypes.CDLL(None, use_errno=True)
    rename = libc.renameat2
    rename.argtypes = (ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint)
    rename.restype = ctypes.c_int
    if rename(-100, os.fsencode(staged), -100, os.fsencode(output), 1):
        error = ctypes.get_errno()
        raise OSError(error, os.strerror(error), str(output))


def digest(path):
    checksum = hashlib.sha256()
    with regular_file(path, os.O_RDONLY) as stream:
        while chunk := stream.read(1024 * 1024):
            checksum.update(chunk)
    return checksum.hexdigest()


def requirements(lock):
    """Read fixed name/version entries and their admitted SHA-256 values."""
    packages = {}
    current = None
    with regular_file(lock, os.O_RDONLY) as stream:
        for raw in stream:
            line = raw.decode().strip().removesuffix("\\").rstrip()
            if not line or line.startswith("#"):
                continue
            if match := re.fullmatch(r"--hash=sha256:([0-9a-f]{64})", line):
                if current is None:
                    raise ValueError("Cannot acquire wheels: hash precedes its locked package")
                packages[current].add(match[1])
                continue
            match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([^\s;]+)", line)
            if match is None:
                raise ValueError(f"Cannot acquire wheels: unsupported lock entry {line!r}")
            current = (re.sub(r"[-_.]+", "-", match[1]).lower(), match[2])
            if current in packages:
                raise ValueError(f"Cannot acquire wheels: duplicate locked package {current}")
            packages[current] = set()
    if not packages or not all(packages.values()):
        raise ValueError("Cannot acquire wheels: every locked package must have SHA-256 hashes")
    return packages


def unique_fields(pairs):
    result = {}
    for name, value in pairs:
        if name in result:
            raise ValueError("Cannot admit tool dependency: duplicate declaration field.")
        result[name] = value
    return result


def make_declaration(path):
    with regular_file(path, os.O_RDONLY) as stream:
        tool = json.load(stream, object_pairs_hook=unique_fields)
    if type(tool) is not dict or tool.keys() != {"name", "version", "file", "url", "size", "sha256"}:
        raise ValueError("Cannot admit tool dependency: expected name, version, file, url, size and sha256.")
    if not (
        tool["name"] == "make"
        and type(tool["version"]) is str
        and re.fullmatch(r"[0-9A-Za-z.+~-]+", tool["version"])
        and tool["file"] == f"make_{tool['version']}_amd64.deb"
        and tool["url"] == f"https://deb.debian.org/debian/pool/main/m/make-dfsg/{tool['file']}"
        and type(tool["size"]) is int
        and tool["size"] > 0
        and type(tool["sha256"]) is str
        and re.fullmatch(r"[0-9a-f]{64}", tool["sha256"])
    ):
        raise ValueError("Cannot admit tool dependency: expected a pinned Debian amd64 make package.")
    return tool


def check(lock, directory, make_path):
    """Hash current regular files and require exactly one wheel per locked package."""
    if directory.is_symlink() or not directory.is_dir():
        raise ValueError("Cannot verify wheelhouse: output must be an existing directory without a symlink")
    expected = requirements(lock)
    tool = make_declaration(make_path)
    found = set()
    found_tool = False
    for path in sorted(directory.iterdir()):
        checksum = digest(path)
        if path.name == tool["file"]:
            if checksum != tool["sha256"] or path.stat().st_size != tool["size"]:
                raise ValueError("Cannot verify tool dependency: make package bytes differ from its declaration.")
            found_tool = True
            continue
        pieces = path.name.split("-")
        if not (path.name.endswith(".whl") and len(pieces) >= 5):
            raise ValueError(f"Cannot verify wheelhouse: unexpected file {path.name!r}")
        package = (re.sub(r"[-_.]+", "-", pieces[0]).lower(), pieces[1])
        if package not in expected or package in found:
            raise ValueError(f"Cannot verify wheelhouse: unlisted or duplicate wheel {path.name!r}")
        if checksum not in expected[package]:
            raise ValueError(f"Cannot verify wheelhouse: hash of {path.name!r} is not in the applied lock")
        found.add(package)
    if missing := sorted(set(expected) - found):
        raise ValueError(f"Cannot verify wheelhouse: missing locked packages {missing}")
    if not found_tool:
        raise ValueError("Cannot verify tool dependencies: the locked make package is missing.")


class HttpsRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        if not new_url.startswith("https://"):
            raise ValueError("Cannot download tool dependency: redirect must remain HTTPS.")
        return super().redirect_request(request, fp, code, message, headers, new_url)


def download(lock, output, make_path):
    """Reuse verified bytes or atomically publish a complete acquired wheel set."""
    if output.exists() or output.is_symlink():
        check(lock, output, make_path)
        return
    requirements(lock)
    tool = make_declaration(make_path)
    stage = Path(tempfile.mkdtemp(prefix=f".{output.name}.pending-", dir=output.parent))
    print(f"Acquiring into {stage}; incomplete staging is preserved on failure.", flush=True)
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "download",
            "--require-hashes",
            "--only-binary=:all:",
            "--no-deps",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "--index-url",
            "https://pypi.org/simple",
            "--dest",
            str(stage),
            "-r",
            str(lock),
        ],
        check=True,
        timeout=600,
    )
    opener = urllib.request.build_opener(HttpsRedirects())
    with opener.open(tool["url"], timeout=60) as response, (stage / tool["file"]).open("xb") as stream:
        size = 0
        while chunk := response.read(1024 * 1024):
            size += len(chunk)
            if size > tool["size"]:
                raise ValueError("Cannot acquire make: response exceeds the declared byte count.")
            stream.write(chunk)
    check(lock, stage, make_path)
    for path in stage.iterdir():
        with regular_file(path, os.O_RDONLY) as stream:
            os.fsync(stream.fileno())
    fsync_directory(stage)
    publish_directory(stage, output)
    fsync_directory(output.parent)


def install(lock, directory, make_path):
    """Install the verified closure offline during the image's explicit root step."""
    check(lock, directory, make_path)
    tool = make_declaration(make_path)
    subprocess.run(["dpkg", "--install", str(directory / tool["file"])], check=True, timeout=60)
    observed = subprocess.run(
        ["dpkg-query", "--show", "--showformat=${Version}", "make"],
        check=True,
        capture_output=True,
        text=True,
        timeout=10,
    )
    if observed.stdout != tool["version"]:
        raise ValueError("Cannot install make: installed version differs from its declaration.")
    subprocess.run(
        [
            sys.executable,
            "-m",
            "pip",
            "install",
            "--no-index",
            "--no-cache-dir",
            "--disable-pip-version-check",
            "--only-binary=:all:",
            "--require-hashes",
            "--find-links",
            str(directory),
            "-r",
            str(lock),
        ],
        check=True,
        timeout=120,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("download", "check", "install"))
    parser.add_argument("--lock", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--make-declaration", type=Path, required=True)
    arguments = parser.parse_args()
    if arguments.action == "download":
        download(arguments.lock, arguments.output, arguments.make_declaration)
    elif arguments.action == "install":
        install(arguments.lock, arguments.output, arguments.make_declaration)
    else:
        check(arguments.lock, arguments.output, arguments.make_declaration)
