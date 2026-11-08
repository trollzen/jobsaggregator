"""Rough filter without AI: drop short posts, non-vacancy markers, posts without job words."""

from __future__ import annotations

from jobagg.models import Post


class Prefilter:
    def __init__(
        self,
        min_length: int = 80,
        include_keywords: list[str] | None = None,
        exclude_keywords: list[str] | None = None,
    ):
        self.min_length = min_length
        self.include = [k.lower() for k in (include_keywords or [])]
        self.exclude = [k.lower() for k in (exclude_keywords or [])]

    @classmethod
    def from_config(cls, cfg: dict) -> Prefilter:
        return cls(
            min_length=cfg.get("min_length", 80),
            include_keywords=cfg.get("include_keywords"),
            exclude_keywords=cfg.get("exclude_keywords"),
        )

    def reason(self, post: Post) -> str | None:
        """None if the post passes, otherwise a short reason."""
        text = post.text.lower()
        if len(text) < self.min_length:
            return "short"
        if any(k in text for k in self.exclude):
            return "excluded"
        if self.include and not any(k in text for k in self.include):
            return "no_keywords"
        return None

    def passes(self, post: Post) -> bool:
        return self.reason(post) is None
