from __future__ import annotations
import os
import shutil
import tempfile
from contextlib import contextmanager
from typing import Generator


@contextmanager
def readonly_cookies_copy(cookies_file: str | None) -> Generator[str | None, None, None]:
    """Hand callers a throwaway copy of a cookies file.

    yt-dlp and gallery-dl both rewrite their `cookies`/`cookiefile` path in
    place after a run (to persist server-issued cookie updates). A site
    treating a request as logged-out can cause them to write back a jar with
    the session cookie stripped, silently destroying the real login session.
    Give them a scratch copy instead so the real cookies file is never mutated.
    """
    if not cookies_file or not os.path.exists(cookies_file):
        yield cookies_file
        return
    fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="cookies_")
    os.close(fd)
    try:
        shutil.copyfile(cookies_file, tmp_path)
        yield tmp_path
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
