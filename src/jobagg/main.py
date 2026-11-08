"""Entry point: read channels -> prefilter -> extract -> dedupe -> store -> save state."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

from jobagg.config import load_config, load_env
from jobagg.dedupe import Deduper
from jobagg.extract import RuleExtractor
from jobagg.keywords import TopicFilter
from jobagg.prefilter import Prefilter
from jobagg.sources.telegram_web import TelegramWebSource
from jobagg.store import make_store

log = logging.getLogger("jobagg")


def build_sources(cfg: dict, source=None, tg_source=None) -> list[tuple[str, object]]:
    """(channel name, source) pairs: public channels via t.me/s, closed via Telethon."""
    fetch_cfg = cfg["fetch"]
    pairs: list[tuple[str, object]] = []
    if cfg["channels"]:
        web = source or TelegramWebSource(
            timeout_s=fetch_cfg.get("timeout_s", 20), delay_s=fetch_cfg.get("delay_s", 1.5)
        )
        pairs += [(ch, web) for ch in cfg["channels"]]
    tg_channels = cfg["telethon"].get("channels") or []
    if tg_channels:
        if tg_source is None:
            try:
                from jobagg.sources.telethon_src import TelethonSource

                tg_source = TelethonSource(
                    tg_channels, session=cfg["telethon"].get("session", "tg.session")
                )
            except Exception as e:
                log.error("Telegram API unavailable, closed channels skipped: %s", e)
                tg_source = _Broken(e)
        pairs += [(c["name"], tg_source) for c in tg_channels]
    return pairs


class _Broken:
    def __init__(self, err: Exception):
        self.err = err

    def fetch(self, *args, **kwargs):
        raise RuntimeError(self.err)


def run(cfg: dict, dry_run: bool = False, source=None, store=None, tg_source=None) -> dict:
    fetch_cfg = cfg["fetch"]
    sources = build_sources(cfg, source, tg_source)
    store = store or make_store(cfg["store"])
    prefilter = Prefilter.from_config(cfg["prefilter"])
    topic = TopicFilter.from_config(cfg)
    extractor = RuleExtractor()  # LLMExtractor in stage 5 (ai.mode: hybrid)

    state = store.load_state()
    deduper = Deduper(
        store.load_jobs(),
        cfg["dedupe"].get("fuzzy_threshold", 92),
        cfg["dedupe"].get("window_days", 30),
    )
    stats = {
        "channels_ok": 0,
        "channels_failed": 0,
        "read": 0,
        "filtered_out": 0,  # sum of the three below
        "not_vacancy": 0,
        "not_domain": 0,
        "not_mine": 0,
        "not_role": 0,
        "extracted": 0,
        "duplicates": 0,
        "possible_dups": 0,
        "written": 0,
    }
    new_state = dict(state)
    to_write = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    for channel, src in sources:
        try:
            posts = src.fetch(
                channel,
                after_id=state.get(channel, 0),
                max_posts=fetch_cfg.get("max_posts_per_channel", 200),
                backfill_days=fetch_cfg.get("backfill_days", 7),
            )
        except Exception as e:  # one channel must not break the run
            log.error("channel %s failed: %s", channel, e)
            stats["channels_failed"] += 1
            continue
        stats["channels_ok"] += 1
        stats["read"] += len(posts)
        ch = {"not_vacancy": 0, "not_domain": 0, "not_mine": 0, "not_role": 0}
        for post in posts:
            if not prefilter.passes(post):
                ch["not_vacancy"] += 1
                continue
            res = topic.check(post.text)
            if res.reason:
                ch[res.reason] += 1
                continue
            for job in extractor.extract(post):
                stats["extracted"] += 1
                job.found_at = now
                job.domain_match = res.domain
                job.role_match = res.role
                job.priority = res.priority
                job.experience_match = res.experience
                checked = deduper.check(job)
                if checked is None:
                    stats["duplicates"] += 1
                    continue
                if checked.possible_dup:
                    stats["possible_dups"] += 1
                to_write.append(checked)
        for key, n in ch.items():
            stats[key] += n
            stats["filtered_out"] += n
        log.info(
            "channel %s: posts=%d not_vacancy=%d not_domain=%d not_mine=%d not_role=%d left=%d",
            channel,
            len(posts),
            *ch.values(),
            len(posts) - sum(ch.values()),
        )
        if posts:
            new_state[channel] = max(p.message_id for p in posts)

    if dry_run:
        for j in to_write:
            log.info("[dry-run] %s | %s | %s | %s", j.title, j.company, j.contact, j.post_url)
    else:
        # rows first, state second: a crash in between only causes re-processing,
        # which dedupe catches.
        stats["written"] = store.append(to_write)
        store.save_state(new_state)

    health_fail = (
        cfg["health"].get("fail_if_no_posts", True) and sources and stats["channels_ok"] == 0
    )
    stats["healthy"] = not health_fail
    return stats


def dump_posts(cfg: dict, limit: int, out_dir: str = "out") -> Path:
    sources = build_sources(cfg)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    path = Path(out_dir) / f"posts_{datetime.now():%Y%m%d_%H%M}.jsonl"
    report = []
    with open(path, "w", encoding="utf-8") as f:
        for channel, src in sources:
            try:
                posts = src.fetch(channel, max_posts=limit, backfill_days=3650)
                report.append(
                    f"{channel}: OK, {len(posts)} posts, dated={sum(1 for p in posts if p.date)}"
                )
            except Exception as e:
                report.append(f"{channel}: FAILED ({e})")
                continue
            for p in posts:
                f.write(json.dumps(p.model_dump(mode="json"), ensure_ascii=False) + "\n")
    for line in report:
        print(line)
    _summary("## Dump posts\n" + "\n".join(f"- {r}" for r in report))
    return path


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="jobagg")
    ap.add_argument("--config", default="config.yaml")
    ap.add_argument("--dry-run", action="store_true", help="do not write rows or state")
    ap.add_argument(
        "--dump-posts",
        type=int,
        metavar="N",
        help="save last N posts per channel to out/posts_*.jsonl and exit",
    )
    ap.add_argument("--store", choices=["csv", "sheets"], help="override store.type")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    load_env()
    cfg = load_config(args.config)
    if args.store:
        cfg["store"]["type"] = args.store
    if args.dump_posts:
        dump_posts(cfg, args.dump_posts)
        return 0

    stats = run(cfg, dry_run=args.dry_run)
    line = (
        "read={read} not_vacancy={not_vacancy} not_domain={not_domain} "
        "not_mine={not_mine} not_role={not_role} "
        "filtered_out={filtered_out} extracted={extracted} "
        "duplicates={duplicates} possible_dups={possible_dups} written={written} "
        "channels_ok={channels_ok} channels_failed={channels_failed}"
    ).format(**stats)
    print("SUMMARY " + line)
    _summary(f"## Run summary\n`{line}`")
    if not stats["healthy"]:
        log.error("health check failed: no channel returned posts")
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
