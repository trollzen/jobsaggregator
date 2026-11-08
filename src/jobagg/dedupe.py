"""Deduplication.

Rule (master plan v5):
- exact duplicate (same job link, else same contact+title, else same title+company+city)
  -> skipped;
- fuzzy duplicate (same company, similar title, within window) -> written with a
  "possible duplicate" mark pointing to the earlier row hash.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit, urlunsplit

from rapidfuzz import fuzz

from jobagg.models import Job


def norm(s: str) -> str:
    s = s.lower().replace("ё", "е")
    s = re.sub(r"[^\w\s]", " ", s)
    return re.sub(r"\s+", " ", s).strip()


_TRACKING_PREFIX = ("utm_", "mc_")
_TRACKING_NAMES = {"fbclid", "gclid", "yclid", "ref", "source"}


def _is_tracking(param: str) -> bool:
    name = param.split("=", 1)[0].lower()
    return name.startswith(_TRACKING_PREFIX) or name in _TRACKING_NAMES


def norm_url(url: str) -> str:
    """Same job, other formatting -> same string. Keeps query params like ?ID=123
    (they often identify the job), drops only tracking ones (utm_*, fbclid...)."""
    parts = urlsplit(url.strip())
    query = sorted(p for p in parts.query.split("&") if p and not _is_tracking(p))
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower().removeprefix("www."),
            parts.path.rstrip("/"),
            "&".join(query),
            "",
        )
    ).lower()


def job_key(job: Job) -> str:
    if job.job_url:
        base = "url:" + norm_url(job.job_url)
    elif job.contact:
        base = f"contact:{job.contact.lower()}|{norm(job.title)}"
    else:
        base = f"fields:{norm(job.title)}|{norm(job.company)}|{norm(job.city)}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


class Deduper:
    def __init__(self, existing: list[Job], fuzzy_threshold: int = 92, window_days: int = 30):
        self.seen: set[str] = {j.hash for j in existing if j.hash}
        self.origin: dict[str, str] = {h: "таблица" for h in self.seen}  # hash -> where first seen
        self.threshold = fuzzy_threshold
        cutoff = datetime.now() - timedelta(days=window_days)
        self.recent = [j for j in existing if j.company and _parse(j.found_at, cutoff) >= cutoff]

    def check(self, job: Job) -> Job | None:
        """Return job with hash (and maybe possible_dup) or None if exact duplicate."""
        job.hash = job_key(job)
        if job.hash in self.seen:
            return None
        if job.company and job.title:
            c, t = norm(job.company), norm(job.title)
            for other in self.recent:
                if (
                    norm(other.company) == c
                    and fuzz.token_set_ratio(t, norm(other.title)) >= self.threshold
                ):
                    job.possible_dup = other.hash
                    break
        self.seen.add(job.hash)
        self.origin.setdefault(job.hash, job.source or "?")
        self.recent.append(job)
        return job


def _parse(s: str, default: datetime) -> datetime:
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return default
