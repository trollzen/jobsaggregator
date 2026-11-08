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
from dataclasses import dataclass

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
        # "удален*" and "удалён*" are the same after normalize: keep one, so it counts once
        seen: set[str] = set()
        unique = []
        for p in self.patterns:
            if p[1].pattern not in seen:
                seen.add(p[1].pattern)
                unique.append(p)
        self.patterns = unique

    def __bool__(self) -> bool:
        return bool(self.patterns)

    def find(self, norm_text: str) -> list[str]:
        """Labels of patterns found in already normalized text, in config order."""
        found = []
        for label, rx, is_word in self.patterns:
            for m in rx.finditer(norm_text):
                if is_word and _NUMBER_BEFORE.search(norm_text[: m.start()]):
                    continue
                if label not in found:
                    found.append(label)
                break
        return found

    def remove(self, norm_text: str) -> str:
        """Cut every pattern out of the text (used for employer benefits like "ДМС")."""
        for _, rx, _ in sorted(self.patterns, key=lambda p: -len(p[1].pattern)):
            norm_text = rx.sub(" | ", norm_text)
        return norm_text


@dataclass
class TopicResult:
    reason: str | None = None  # None = passed; not_domain | not_mine | not_role
    domain: str = ""  # matched "Сфера" keywords
    role: str = ""  # matched "Роль" keywords (+ "не моё: ..." mark)
    priority: str = ""  # высокий | средний | ""
    experience: str = ""  # matched "Мой опыт" keywords


class TopicFilter:
    """Filters after the vacancy prefilter, in order:
    2 "Сфера" (domain), "Не мои роли" (role_exclude), 3 "Роль" (role).
    Passed posts also get a priority from "Мой опыт". An empty list switches its step off.
    """

    def __init__(
        self,
        domain_keywords: list[str] | None = None,
        domain_ignore_phrases: list[str] | None = None,
        role_keywords: list[str] | None = None,
        role_exclude: list[str] | None = None,
        my_experience: list[str] | None = None,
        high_from: int = 3,
    ):
        self.domain = KeywordList(domain_keywords)
        self.ignore = KeywordList(domain_ignore_phrases)
        self.roles = KeywordList(role_keywords)
        self.exclude = KeywordList(role_exclude)
        self.experience = KeywordList(my_experience)
        self.high_from = high_from

    @classmethod
    def from_config(cls, cfg: dict) -> TopicFilter:
        return cls(
            cfg.get("domain_keywords"),
            cfg.get("domain_ignore_phrases"),
            cfg.get("role_keywords"),
            cfg.get("role_exclude"),
            cfg.get("my_experience"),
            (cfg.get("priority") or {}).get("high_from", 3),
        )

    def check(self, text: str) -> TopicResult:
        norm = normalize(text)
        res = TopicResult()
        if self.domain:
            hits = self.domain.find(self.ignore.remove(norm))
            if not hits:
                return TopicResult("not_domain")
            res.domain = ", ".join(hits[:5])
        role_hits = self.roles.find(norm)
        not_mine = self.exclude.find(norm)
        if not_mine and not role_hits:
            return TopicResult("not_mine", res.domain)
        if self.roles and not role_hits:
            return TopicResult("not_role", res.domain)
        res.role = ", ".join(role_hits[:5])
        if not_mine:
            res.role += ("; " if res.role else "") + "не моё: " + ", ".join(not_mine[:3])
        exp = self.experience.find(norm)
        res.experience = ", ".join(exp)
        if exp:
            res.priority = "высокий" if len(exp) >= self.high_from else "средний"
        return res
