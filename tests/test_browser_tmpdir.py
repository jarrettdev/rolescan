"""adrs/0012: a scrape's browser temp files live in one folder that is deleted when the scrape ends."""
import os
import sys
import tempfile
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
import hc_scraper  # noqa: E402
from hc_scraper import BROWSER_TMP_PREFIX, browser_tmpdir  # noqa: E402

hc_scraper.log = lambda *a, **k: None


def test_tmpdir_set_and_removed():
    with tempfile.TemporaryDirectory() as base:
        before = os.environ.get("TMPDIR")
        with browser_tmpdir(base=base) as d:
            assert os.path.isdir(d) and os.path.dirname(d) == base
            assert os.path.basename(d).startswith(BROWSER_TMP_PREFIX)
            assert os.environ["TMPDIR"] == d and tempfile.gettempdir() == d
            open(os.path.join(d, "junk"), "w").write("x")  # what Chrome would leave
        assert not os.path.exists(d)
        assert os.environ.get("TMPDIR") == before


def test_removed_on_error():
    with tempfile.TemporaryDirectory() as base:
        before = os.environ.get("TMPDIR")
        try:
            with browser_tmpdir(base=base) as d:
                raise RuntimeError("scrape failed")
        except RuntimeError:
            pass
        assert not os.path.exists(d)
        assert os.environ.get("TMPDIR") == before


def test_restores_existing_tmpdir():
    with tempfile.TemporaryDirectory() as base:
        os.environ["TMPDIR"] = base
        try:
            with browser_tmpdir(base=base):
                pass
            assert os.environ["TMPDIR"] == base
        finally:
            os.environ.pop("TMPDIR", None)
            tempfile.tempdir = None


def test_stale_swept_fresh_kept_others_untouched():
    with tempfile.TemporaryDirectory() as base:
        now = time.time()
        stale = os.path.join(base, BROWSER_TMP_PREFIX + "old")
        fresh = os.path.join(base, BROWSER_TMP_PREFIX + "running")
        other = os.path.join(base, "someone-else")
        for d in (stale, fresh, other):
            os.mkdir(d)
        os.utime(stale, (now - 7 * 3600, now - 7 * 3600))
        os.utime(other, (now - 30 * 86400, now - 30 * 86400))
        with browser_tmpdir(base=base, now=now):
            pass
        assert not os.path.exists(stale)
        assert os.path.isdir(fresh) and os.path.isdir(other)


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"test_browser_tmpdir: {len(tests)} passed")
