"""Rule-based extraction (works with ai.mode: off). LLMExtractor comes in stage 5."""

from __future__ import annotations

import re

from jobagg.models import Job, Post

LABELS = {
    "title": r"(?:вакансия|должность|позиция|position|role|vacancy|job title)",
    "company": r"(?:компания|company|работодатель|employer)",
    "location": r"(?:локация|location|город|city|место работы|office)",
    "salary": r"(?:зарплата|зп|з/п|оклад|salary|compensation|вилка)",
}
LABEL_RE = {
    k: re.compile(rf"\b{v}\s*[:\-—–]\s*(.+)$", re.IGNORECASE | re.MULTILINE)
    for k, v in LABELS.items()
}
EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
TG_USER_RE = re.compile(r"(?<![\w/])@([A-Za-z][\w]{3,31})")
HASHTAG_RE = re.compile(r"#\w+")
NUM = r"(\d[\d\s.,]*\d|\d)\s*(k|к|тыс\.?)?"
SALARY_RANGE_RE = re.compile(rf"{NUM}\s*(?:-|–|—|до|to)\s*{NUM}", re.IGNORECASE)
SALARY_FROM_RE = re.compile(rf"(?:от|from)\s*{NUM}", re.IGNORECASE)
CURRENCIES = [
    ("USD", r"\$|usd|долл"),
    ("EUR", r"€|eur|евро"),
    ("RUB", r"₽|руб|rub|\bр\.?\b"),
    ("AMD", r"֏|amd|драм"),
    ("KZT", r"₸|kzt|тенге"),
    ("GEL", r"₾|gel|лари"),
]
REMOTE_RE = re.compile(r"remote|удал[её]н|удаленка|удалёнка|wfh|из любой точки", re.I)
HYBRID_RE = re.compile(r"hybrid|гибрид", re.I)
ONSITE_RE = re.compile(r"on-?site|офис|office", re.I)
SENIORITY = [
    ("intern", r"intern|стажер|стажёр"),
    ("junior", r"junior|джун"),
    ("middle", r"middle|мидл"),
    ("senior", r"senior|сеньор|синьор"),
    ("lead", r"lead|лид|head of|руководитель"),
]
TME_RE = re.compile(r"^https?://(t\.me|telegram\.me)/", re.I)


def _num(raw: str, mult: str | None) -> float | None:
    s = re.sub(r"[\s]", "", raw).replace(",", ".")
    if s.count(".") > 1 or (s.count(".") == 1 and len(s.split(".")[1]) == 3):
        s = s.replace(".", "")
    try:
        v = float(s)
    except ValueError:
        return None
    if mult:
        v *= 1000
    return v


def _clean(value: str) -> str:
    value = HASHTAG_RE.sub("", value)
    return value.strip(" *_•-—–:|").strip()


def parse_salary(text: str) -> tuple[float | None, float | None, str]:
    currency = ""
    for code, pat in CURRENCIES:
        if re.search(pat, text, re.I):
            currency = code
            break
    m = SALARY_RANGE_RE.search(text)
    if m:
        lo, hi = _num(m.group(1), m.group(2)), _num(m.group(3), m.group(4))
        if lo and hi and m.group(4) and not m.group(2):
            lo *= 1000  # "100-150k"
        if lo and hi and lo <= hi:
            return lo, hi, currency
    m = SALARY_FROM_RE.search(text)
    if m:
        return _num(m.group(1), m.group(2)), None, currency
    return None, None, currency


class RuleExtractor:
    method = "rules"

    def extract(self, post: Post) -> list[Job]:
        text = post.text
        lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
        fields: dict[str, str] = {}
        for key, rx in LABEL_RE.items():
            m = rx.search(text)
            if m:
                fields[key] = _clean(m.group(1))

        title = fields.get("title") or self._guess_title(lines)
        location = fields.get("location", "")

        sal_text = fields.get("salary") or text
        salary_min, salary_max, currency = (
            parse_salary(sal_text)
            if (fields.get("salary") or re.search(LABELS["salary"], text, re.I))
            else (None, None, "")
        )

        work_mode = ""
        if REMOTE_RE.search(text):
            work_mode = "remote"
        elif HYBRID_RE.search(text):
            work_mode = "hybrid"
        elif ONSITE_RE.search(text):
            work_mode = "onsite"

        seniority = ""
        for level, pat in SENIORITY:
            if re.search(pat, title or "", re.I):
                seniority = level
                break

        job_url = next(
            (
                u
                for u in post.links
                if u.startswith("http") and not TME_RE.match(u) and not u.startswith("mailto:")
            ),
            "",
        )
        contact = ""
        emails = EMAIL_RE.findall(text)
        users = [u for u in TG_USER_RE.findall(text)]
        if users:
            contact = "@" + users[0]
        elif emails:
            contact = emails[0]
        else:
            tg = next(
                (
                    u
                    for u in post.links
                    if TME_RE.match(u) and "/" not in u.split("t.me/", 1)[-1].strip("/")
                ),
                "",
            )
            if tg:
                contact = "@" + tg.rstrip("/").rsplit("/", 1)[-1]

        description = " ".join(lines[1:4])[:300] if len(lines) > 1 else ""
        return [
            Job(
                post_date=post.date.strftime("%Y-%m-%d %H:%M") if post.date else "",
                title=title[:150],
                seniority=seniority,
                company=fields.get("company", "")[:100],
                city=location[:100],
                work_mode=work_mode,
                salary_min=salary_min,
                salary_max=salary_max,
                currency=currency,
                description=description,
                post_url=post.url,
                job_url=job_url,
                contact=contact,
                source=post.channel,
                method=self.method,
            )
        ]

    @staticmethod
    def _guess_title(lines: list[str]) -> str:
        for ln in lines[:3]:
            cleaned = _clean(ln)
            if 3 <= len(cleaned) <= 120 and not cleaned.lower().startswith(("http", "#")):
                return cleaned
        return ""
