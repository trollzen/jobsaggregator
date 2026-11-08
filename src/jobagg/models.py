"""Data models: raw post and normalized job row (schema from master plan, section 4)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class Post(BaseModel):
    channel: str
    message_id: int
    date: datetime | None = None
    text: str = ""
    links: list[str] = Field(default_factory=list)
    link: str = ""  # set for private channels (t.me/c/...)

    @property
    def url(self) -> str:
        return self.link or f"https://t.me/{self.channel}/{self.message_id}"


class Job(BaseModel):
    post_date: str = ""
    found_at: str = ""
    title: str = ""
    role: str = ""
    seniority: str = ""
    company: str = ""
    country: str = ""
    city: str = ""
    work_mode: str = ""  # remote | hybrid | onsite | ""
    salary_min: float | None = None
    salary_max: float | None = None
    currency: str = ""
    skills: list[str] = Field(default_factory=list)
    match: int | None = None
    description: str = ""
    post_url: str = ""
    job_url: str = ""
    contact: str = ""
    source: str = ""
    status: str = "новая"
    method: str = "rules"  # ai | rules
    possible_dup: str = ""
    hash: str = ""


# Column header (in the sheet) -> Job field. Order = default column order.
COLUMNS: list[tuple[str, str]] = [
    ("Дата поста", "post_date"),
    ("Найдено", "found_at"),
    ("Должность", "title"),
    ("Роль", "role"),
    ("Уровень", "seniority"),
    ("Компания", "company"),
    ("Страна", "country"),
    ("Город", "city"),
    ("Формат работы", "work_mode"),
    ("Зарплата от", "salary_min"),
    ("Зарплата до", "salary_max"),
    ("Валюта", "currency"),
    ("Навыки", "skills"),
    ("Match", "match"),
    ("Описание", "description"),
    ("Ссылка на пост", "post_url"),
    ("Ссылка на вакансию", "job_url"),
    ("Контакт", "contact"),
    ("Источник", "source"),
    ("Статус", "status"),
    ("Метод", "method"),
    ("Возможный дубль", "possible_dup"),
    ("Хэш", "hash"),
]
HEADER = [h for h, _ in COLUMNS]
FIELD_BY_HEADER = dict(COLUMNS)
STATUS_VALUES = ["новая", "откликнулся", "интервью", "отказ"]


def job_to_cell(job: Job, field: str) -> str | float | int:
    value = getattr(job, field)
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(value)
    return value


def row_to_job(header: list[str], row: list[str]) -> Job:
    """Rebuild a partial Job from a sheet/CSV row (used for dedupe)."""
    data: dict = {}
    for i, h in enumerate(header):
        field = FIELD_BY_HEADER.get(h)
        if (
            field
            and i < len(row)
            and field
            in ("title", "company", "city", "hash", "post_date", "job_url", "contact", "found_at")
        ):
            data[field] = row[i]
    return Job(**data)
