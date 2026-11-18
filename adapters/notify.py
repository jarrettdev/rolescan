"""Notify adapter (ADR 0018): one public surface for print, webhook and Discord.

`send` is synchronous, returns one result per posting, and never touches the
network when dry_run is set. A missing key raises NotifyError naming the target
before anything is sent.
"""

from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass

from adapters.config import MissingSecret

API = "https://discord.com/api/v10"
USER_AGENT = "rolescan/0.1.0 (+https://github.com/jarrettdev/rolescan)"


class NotifyError(RuntimeError):
    """The target could not be reached or refused the message."""


@dataclass
class Result:
    ok: bool
    target: str
    company: str = ""
    error: str = ""


def format_post(post: dict) -> str:
    """One posting as a plain message: company, title, location, pay, link."""
    parts = [p for p in (post.get("company"), post.get("title")) if p]
    head = " — ".join(parts) if parts else (post.get("apply_url") or "posting")
    detail = " · ".join(str(post[k]) for k in ("location", "salary") if post.get(k))
    lines = [head]
    if detail:
        lines.append(detail)
    if post.get("apply_url"):
        lines.append(str(post["apply_url"]))
    return "\n".join(lines)


def _post_json(url: str, payload: dict, headers: dict, timeout: int = 20) -> dict:
    body = json.dumps(payload).encode()
    request = urllib.request.Request(url, data=body, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "User-Agent": USER_AGENT, **headers})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read() or b"{}")


def _discord_target(cfg: dict) -> str:
    if cfg.get("enable_dm") and cfg.get("dm_user_id"):
        channel = _post_json(f"{API}/users/@me/channels", {"recipient_id": cfg["dm_user_id"]},
                             {"Authorization": f"Bot {cfg['bot_token']}"})
        return channel.get("id") or cfg["channel"]
    return cfg["channel"]


def send(posts: list[dict], cfg: dict, dry_run: bool = False) -> list[Result]:
    """Deliver every posting to the configured target; one Result each."""
    target = cfg.get("target", "print")
    results: list[Result] = []
    if target not in ("print", "webhook", "discord"):
        raise NotifyError(f"unknown notify target {target!r}")
    if target == "discord" and not cfg.get("bot_token"):
        raise MissingSecret("DISCORD_BOT_TOKEN")
    channel = _discord_target(cfg) if target == "discord" and not dry_run else ""
    for post in posts:
        text = format_post(post)
        if dry_run or target == "print":
            print(text)
            print("-" * 40)
            results.append(Result(True, target, post.get("company", ""), "dry-run" if dry_run else ""))
            continue
        try:
            if target == "webhook":
                _post_json(cfg["webhook_url"], {"content": text}, {})
            else:
                _post_json(f"{API}/channels/{channel}/messages", {"content": text},
                           {"Authorization": f"Bot {cfg['bot_token']}"})
                time.sleep(1.0)
            results.append(Result(True, target, post.get("company", "")))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, OSError) as error:
            results.append(Result(False, target, post.get("company", ""), str(error)))
    return results


def as_dicts(results: list[Result]) -> list[dict]:
    return [asdict(result) for result in results]
