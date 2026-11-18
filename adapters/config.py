"""Environment configuration with explicit requirements per notify target (ADR 0018).

One rule: a blank or missing value is missing. Nothing falls back to an empty
token, so a fresh clone runs the print target and a misconfigured Discord run
stops with the key it needs named.
"""

from __future__ import annotations

import os
from pathlib import Path

from adapters import paths

TARGETS = ("print", "webhook", "discord")
REQUIRED = {
    "print": (),
    "webhook": ("NOTIFY_WEBHOOK_URL",),
    "discord": ("DISCORD_BOT_TOKEN", "DISCORD_CHANNEL_ID"),
}


class MissingSecret(RuntimeError):
    """A required environment value is absent or blank."""

    def __init__(self, key: str):
        super().__init__(f"MISSING_SECRET: {key}")
        self.key = key


def _dotenv_path():
    """Where .env lives: JOBKIT_ENV (blank disables), else ./env."""
    override = os.environ.get("JOBKIT_ENV")
    if override is not None:
        return Path(override) if override else None
    return paths.ROOT / ".env"


def _load_dotenv() -> None:
    env_file = _dotenv_path()
    if env_file is None or not env_file.exists():
        return
    try:
        from dotenv import load_dotenv
    except ImportError:
        return
    load_dotenv(env_file, override=False)


def value(key: str, default: str = "") -> str:
    """The environment value, or the default when unset or blank."""
    raw = os.environ.get(key)
    if raw is None:
        return default
    raw = raw.strip()
    return raw if raw else default


def require(key: str) -> str:
    found = value(key)
    if not found:
        raise MissingSecret(key)
    return found


def notify_config() -> dict:
    """{target, channel, dm_user_id, webhook_url}, validating the target's keys."""
    _load_dotenv()
    target = value("NOTIFY", "print").lower()
    if target not in TARGETS:
        raise ValueError(f"NOTIFY must be one of {TARGETS}, got {target!r}")
    config = {
        "target": target,
        "channel": value("DISCORD_CHANNEL_ID"),
        "webhook_url": value("NOTIFY_WEBHOOK_URL"),
        "dm_user_id": value("DM_USER_ID"),
        "enable_dm": value("ENABLE_DM", "0") == "1",
    }
    for key in REQUIRED[target]:
        config[key.lower()] = require(key)
    if target == "discord":
        config["channel"] = require("DISCORD_CHANNEL_ID")
        config["bot_token"] = require("DISCORD_BOT_TOKEN")
        if config["enable_dm"]:
            config["dm_user_id"] = require("DM_USER_ID")
    return config


def enabled(key: str, default: bool) -> bool:
    return value(key, "1" if default else "0") == "1"


def hiring_cafe_enabled() -> bool:
    _load_dotenv()
    return enabled("ENABLE_HIRING_CAFE", True)


def captcha_enabled() -> bool:
    """Solving a third-party captcha is opt-in (docs/third-party.md)."""
    _load_dotenv()
    return enabled("HC_SOLVE_CAPTCHA", False)


def enrichment_enabled() -> bool:
    _load_dotenv()
    return enabled("ENRICH", False)
