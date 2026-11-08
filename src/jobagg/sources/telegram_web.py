"""Read public Telegram channels through the web preview https://t.me/s/<channel>.

No account, keys or session are needed. Each page holds ~20 latest posts;
older posts are reached with ?before=<message_id>.
"""

from __future__ import annotations

import html as htmllib
import logging
import time
from datetime import UTC, datetime, timedelta

import httpx
from bs4 import BeautifulSoup

from jobagg.models import Post

log = logging.getLogger(__name__)

BASE = "https://t.me/s/{channel}"
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; jobagg/0.1)"}


class ChannelUnavailable(Exception):
    """Preview is disabled, channel does not exist or redirects away."""


def parse_page(html: str, channel: str) -> list[Post]:
    soup = BeautifulSoup(html, "html.parser")
    posts: list[Post] = []
    for msg in soup.select("div.tgme_widget_message[data-post]"):
        data_post = msg.get("data-post", "")
        try:
            ch, mid = data_post.rsplit("/", 1)
            message_id = int(mid)
        except ValueError:
            continue
        text_el = msg.select_one("div.tgme_widget_message_text")
        text = text_el.get_text("\n", strip=True) if text_el else ""
        links: list[str] = []
        if text_el:
            for a in text_el.select("a[href]"):
                href = htmllib.unescape(a["href"]).strip()
                if href.startswith(("http://", "https://")) and href not in links:
                    links.append(href)
        date = None
        time_el = msg.select_one("a.tgme_widget_message_date time[datetime]")
        if time_el:
            try:
                date = datetime.fromisoformat(time_el["datetime"])
            except ValueError:
                date = None
        posts.append(
            Post(channel=ch or channel, message_id=message_id, date=date, text=text, links=links)
        )
    return posts


class TelegramWebSource:
    def __init__(
        self,
        timeout_s: float = 20,
        delay_s: float = 1.5,
        retries: int = 3,
        client: httpx.Client | None = None,
    ):
        self.client = client or httpx.Client(
            timeout=timeout_s, headers=HEADERS, follow_redirects=False
        )
        self.delay_s = delay_s
        self.retries = retries

    def _get(self, url: str, params: dict | None = None) -> str:
        last_exc: Exception | None = None
        for attempt in range(self.retries):
            try:
                r = self.client.get(url, params=params)
                if r.status_code in (301, 302):
                    raise ChannelUnavailable(f"{url} redirects (preview disabled?)")
                if r.status_code == 429 or r.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"status {r.status_code}", request=r.request, response=r
                    )
                r.raise_for_status()
                return r.text
            except ChannelUnavailable:
                raise
            except httpx.HTTPError as e:
                last_exc = e
                wait = 2**attempt * 2
                log.warning("GET %s failed (%s), retry in %ss", url, e, wait)
                time.sleep(wait)
        raise last_exc  # type: ignore[misc]

    def fetch(
        self, channel: str, after_id: int = 0, max_posts: int = 200, backfill_days: int = 7
    ) -> list[Post]:
        """Return posts newer than after_id, oldest first.

        On first run (after_id == 0) stop at max_posts or backfill_days.
        """
        url = BASE.format(channel=channel)
        cutoff = datetime.now(UTC) - timedelta(days=backfill_days)
        collected: dict[int, Post] = {}
        before: int | None = None
        while True:
            html = self._get(url, params={"before": before} if before else None)
            page = parse_page(html, channel)
            if not page:
                if before is None:
                    raise ChannelUnavailable(f"{channel}: no posts on preview page")
                break
            stop = False
            for p in page:
                if p.message_id <= after_id:
                    stop = True
                    continue
                if after_id == 0 and p.date and p.date < cutoff:
                    stop = True
                    continue
                collected[p.message_id] = p
            if len(collected) >= max_posts:
                stop = True
            oldest = min(p.message_id for p in page)
            if stop or oldest <= 1 or (before is not None and oldest >= before):
                break
            before = oldest
            time.sleep(self.delay_s)
        posts = sorted(collected.values(), key=lambda p: p.message_id)
        return posts[-max_posts:]
