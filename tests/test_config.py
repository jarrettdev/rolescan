"""Config is explicit (adrs/0018): a blank value is missing, each target names
its own keys, and no secret is needed to run the print target."""
import contextlib
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from adapters import config  # noqa: E402


@contextlib.contextmanager
def env(**values):
    old = {key: os.environ.get(key) for key in values}
    for key, value in values.items():
        if value is None:
            os.environ.pop(key, None)
        else:
            os.environ[key] = value
    try:
        yield
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


def test_missing_key_names_it():
    with env(JOBKIT_ENV="", NOTIFY="discord", DISCORD_BOT_TOKEN=None, DISCORD_CHANNEL_ID="123"):
        try:
            config.notify_config()
            raise AssertionError("missing token accepted")
        except config.MissingSecret as error:
            assert error.key == "DISCORD_BOT_TOKEN"
            assert "DISCORD_BOT_TOKEN" in str(error)


def test_empty_value_is_missing():
    with env(JOBKIT_ENV="", NOTIFY="webhook", NOTIFY_WEBHOOK_URL="   "):
        try:
            config.notify_config()
            raise AssertionError("blank URL accepted")
        except config.MissingSecret as error:
            assert error.key == "NOTIFY_WEBHOOK_URL"


def test_notify_print_needs_no_secret():
    with env(JOBKIT_ENV="", NOTIFY=None, DISCORD_BOT_TOKEN=None, DISCORD_CHANNEL_ID=None):
        assert config.notify_config()["target"] == "print"


def test_notify_discord_requires_enable_dm():
    with env(JOBKIT_ENV="", NOTIFY="discord", DISCORD_BOT_TOKEN="bot", DISCORD_CHANNEL_ID="123",
             ENABLE_DM="1", DM_USER_ID=None):
        try:
            config.notify_config()
            raise AssertionError("DM enabled without a user id")
        except config.MissingSecret as error:
            assert error.key == "DM_USER_ID"


def test_slack_is_absent():
    for name in ("adapters/config.py", "adapters/notify.py", "process_stream.py"):
        text = (ROOT / name).read_text().lower()
        assert "slack" not in text, name


def test_source_flags():
    with env(JOBKIT_ENV="", ENABLE_HIRING_CAFE=None, HC_SOLVE_CAPTCHA=None, ENRICH=None):
        assert config.hiring_cafe_enabled() is True
        assert config.captcha_enabled() is False
        assert config.enrichment_enabled() is False
    with env(JOBKIT_ENV="", ENABLE_HIRING_CAFE="0", HC_SOLVE_CAPTCHA="1"):
        assert config.hiring_cafe_enabled() is False and config.captcha_enabled() is True


if __name__ == "__main__":
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for t in tests:
        t()
    print(f"CONFIG:MET {len(tests)} tests")
