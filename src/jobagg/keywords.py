"""Keyword filters "Сфера" (domain) and "Роль" (role), rules only, no AI.

Pattern syntax in config.yaml (one list item may hold several patterns, comma-separated):
    [word]   whole word only ("[PM]" does not match "npm"); also not right after
             a 1-2 digit number, so "5 pm" / "10:30 PM" is not PM
    word*    word start ("клиник*" matches "клиника", "клиникой")
    other    phrase anywhere in the text
Matching ignores case, treats "ё" as "е" and a hyphen as a space.
"""

from __future__ import annotations

import re

_HYPHENS = re.compile(r"[-‐‑‒–−]")
_SPACES = re.compile(r"\s+")
# a time or small count right before an abbreviation: "5 pm", "10:30 PM"
_NUMBER_BEFORE = re.compile(r"(?<!\d)\d{1,2}(?::\d{2})?\s*$")


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = _HYPHENS.sub(" ", text)
    return _SPACES.sub(" ", text).strip()


def split_items(items: list[str] | None) -> list[str]:
    """Config list -> flat list of patterns ("a, b" items are split by comma)."""
    out: list[str] = []
    for item in items or []:
        out += [p.strip() for p in str(item).split(",") if p.strip()]
    return out


class KeywordList:
    def __init__(self, items: list[str] | None):
        self.patterns: list[tuple[str, re.Pattern, bool]] = []  # (label, regex, is_word)
        for raw in split_items(items):
            if raw.startswith("[") and raw.endswith("]"):
                body = normalize(raw[1:-1])
                rx = re.compile(rf"(?<!\w){re.escape(body)}(?!\w)")
                self.patterns.append((raw[1:-1], rx, True))
            elif raw.endswith("*"):
                body = normalize(raw[:-1])
                self.patterns.append((raw, re.compile(rf"(?<!\w){re.escape(body)}\w*"), False))
            else:
                self.patterns.append((raw, re.compile(re.escape(normalize(raw))), False))

    def __bool__(self) -> bool:
        return bool(self.patterns)

    def find(self, norm_text: str) -> list[str]:
        """Labels of patterns found in already normalized text, in config order."""
        found = []
        for label, rx, is_word in self.patterns:
            for m in rx.finditer(norm_text):
                if is_word and _NUMBER_BEFORE.search(norm_text[: m.start()]):
                    continue
                found.append(label)
                break
        return found

    def remove(self, norm_text: str) -> str:
        """Cut every pattern out of the text (used for employer benefits like "ДМС")."""
        for _, rx, _ in sorted(self.patterns, key=lambda p: -len(p[1].pattern)):
            norm_text = rx.sub(" | ", norm_text)
        return norm_text


class TopicFilter:
    """Filter 2 "Сфера" then filter 3 "Роль". An empty list switches its filter off."""

    def __init__(
        self,
        domain_keywords: list[str] | None = None,
        domain_ignore_phrases: list[str] | None = None,
        role_keywords: list[str] | None = None,
    ):
        self.domain = KeywordList(domain_keywords)
        self.ignore = KeywordList(domain_ignore_phrases)
        self.roles = KeywordList(role_keywords)

    @classmethod
    def from_config(cls, cfg: dict) -> TopicFilter:
        return cls(
            cfg.get("domain_keywords"),
            cfg.get("domain_ignore_phrases"),
            cfg.get("role_keywords"),
        )

    def check(self, text: str) -> tuple[str | None, str, str]:
        """(reason or None if passed, domain matches, role matches)."""
        norm = normalize(text)
        domain = ""
        if self.domain:
            hits = self.domain.find(self.ignore.remove(norm))
            if not hits:
                return "not_domain", "", ""
            domain = ", ".join(hits[:5])
        role = ""
        if self.roles:
            hits = self.roles.find(norm)
            if not hits:
                return "not_role", domain, ""
            role = ", ".join(hits[:5])
        return None, domain, role
