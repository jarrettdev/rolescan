"""notify.send (adrs/0018): print needs no network, dry_run never sends, and a
missing key stops before anything is posted."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters import notify  # noqa: E402
from adapters.config import MissingSecret  # noqa: E402

POSTS = [{"company": "Acme", "title": "Software Engineer", "location": "Remote - US",
          "salary": "$110000", "apply_url": "https://example.test/jobs/1"}]


def test_format_post_names_the_posting():
    text = notify.format_post(POSTS[0])
    assert "Acme — Software Engineer" in text and "$110000" in text and text.endswith("/1")


def test_print_target_needs_no_network():
    def boom(*a, **k):
        raise AssertionError("network touched")
    original = notify._post_json
    notify._post_json = boom
    try:
        results = notify.send(POSTS, {"target": "print"})
    finally:
        notify._post_json = original
    assert results[0].ok and results[0].target == "print"


def test_dry_run_never_sends():
    calls = []
    original = notify._post_json
    notify._post_json = lambda *a, **k: calls.append(a) or {}
    try:
        results = notify.send(POSTS, {"target": "webhook", "webhook_url": "https://example.test/hook"}, dry_run=True)
    finally:
        notify._post_json = original
    assert calls == [] and results[0].ok and results[0].error == "dry-run"


def test_unknown_target_raises():
    try:
        notify.send(POSTS, {"target": "carrier-pigeon"})
        raise AssertionError("unknown target accepted")
    except notify.NotifyError as error:
        assert "carrier-pigeon" in str(error)


def test_discord_without_token_raises_missing_secret():
    try:
        notify.send(POSTS, {"target": "discord", "channel": "1"})
        raise AssertionError("discord without a token accepted")
    except MissingSecret as error:
        assert error.key == "DISCORD_BOT_TOKEN"


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"NOTIFY:MET {len(tests)} tests")
