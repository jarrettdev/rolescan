"""Interior primitive `write` (hub integrity/primitives.md): durable append.

Nouns call _write instead of doing raw file I/O in their verbs."""

import fcntl
import os
import tempfile


def _write(path, data: bytes) -> None:
    """Append data to path in one write under an exclusive file lock."""
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.write(fd, data)
    finally:
        os.close(fd)


def _replace(path, data: bytes) -> None:
    """Replace path with data atomically: write a sibling temp file, then rename."""
    d, base = os.path.split(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=d, prefix=f".{base}.")  # unique: two writers never share it
    try:
        os.write(fd, data)
        os.fsync(fd)
        os.fchmod(fd, 0o644)
    finally:
        os.close(fd)
    os.replace(tmp, path)


def _load(path) -> bytes | None:
    """Whole file contents, or None when it does not exist."""
    try:
        fd = os.open(path, os.O_RDONLY)
    except FileNotFoundError:
        return None
    try:
        chunks = []
        while True:
            b = os.read(fd, 1 << 16)
            if not b:
                return b"".join(chunks)
            chunks.append(b)
    finally:
        os.close(fd)
