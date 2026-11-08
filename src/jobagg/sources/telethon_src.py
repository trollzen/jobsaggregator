"""Read closed (private) Telegram channels through the Telegram API (Telethon).

Needs: TG_API_ID, TG_API_HASH (my.telegram.org) and a session file created once
by `python scripts/tg_login.py`. The account must be a member of the channels.
Run it from a machine with a stable IP (your computer), not from GitHub Actions.
"""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime, timedelta

from jobagg.models import Post

log = logging.getLogger(__name__)


def message_to_post(msg, channel_name: str, channel_id: int) -> Post:
    """Convert a Telethon Message to Post (links from text and hidden text-links)."""
    from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

    links: list[str] = []
    for ent, inner in msg.get_entities_text() if msg.entities else []:
        url = ""
        if isinstance(ent, MessageEntityTextUrl):
            url = ent.url
        elif isinstance(ent, MessageEntityUrl):
            url = inner if inner.startswith("http") else "https://" + inner
        if url and url not in links:
            links.append(url)
    internal_id = str(abs(channel_id)).removeprefix("100")
    return Post(
        channel=channel_name,
        message_id=msg.id,
        date=msg.date,
        text=msg.message or "",
        links=links,
        link=f"https://t.me/c/{internal_id}/{msg.id}",
    )


class TelethonSource:
    def __init__(self, channels: list[dict], session: str = "tg.session", client=None):
        """channels: [{"name": "short_name", "id": -100123...}] from config.yaml."""
        self.ids = {c["name"]: int(c["id"]) for c in channels}
        if client is None:
            from telethon.sync import TelegramClient

            client = TelegramClient(
                session, int(os.environ["TG_API_ID"]), os.environ["TG_API_HASH"]
            )
            client.connect()
            if not client.is_user_authorized():
                raise RuntimeError("Telegram session is not authorized: run scripts/tg_login.py")
            client.get_dialogs()  # fills the entity cache so numeric ids resolve
        self.client = client

    def fetch(
        self, channel: str, after_id: int = 0, max_posts: int = 200, backfill_days: int = 7
    ) -> list[Post]:
        channel_id = self.ids[channel]
        cutoff = datetime.now(UTC) - timedelta(days=backfill_days)
        posts: list[Post] = []
        # newest first; Telethon sleeps automatically on short FloodWait errors
        for msg in self.client.iter_messages(channel_id, min_id=after_id, limit=max_posts):
            if after_id == 0 and msg.date and msg.date < cutoff:
                break
            if msg.message or getattr(msg, "media", None):  # image without caption: counted
                posts.append(message_to_post(msg, channel, channel_id))
        return sorted(posts, key=lambda p: p.message_id)

    def close(self) -> None:
        self.client.disconnect()
