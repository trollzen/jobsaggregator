from datetime import UTC, datetime
from pathlib import Path

from jobagg.config import load_config
from jobagg.dedupe import Deduper, job_key
from jobagg.extract import RuleExtractor, parse_salary
from jobagg.main import run
from jobagg.models import HEADER, Job, Post
from jobagg.prefilter import Prefilter
from jobagg.sources.telegram_web import parse_page
from jobagg.store import CsvStore, build_rows

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = (Path(__file__).parent / "fixtures" / "channel_page.html").read_text(encoding="utf-8")


def posts():
    return parse_page(FIXTURE, "testjobs")


def test_parse_page():
    ps = posts()
    assert [p.message_id for p in ps] == [101, 102, 103, 104]
    assert ps[0].date == datetime(2026, 11, 7, 10, tzinfo=UTC)
    assert "Senior Python Developer" in ps[0].text
    assert ps[0].links == ["https://acme.example/jobs/42?utm_source=tg"]


def test_prefilter():
    cfg = load_config(ROOT / "config.yaml")
    pf = Prefilter.from_config(cfg["prefilter"])
    ps = posts()
    assert [pf.reason(p) for p in ps] == [None, "excluded", "short", None]


def test_rule_extractor():
    job = RuleExtractor().extract(posts()[0])[0]
    assert job.title == "Senior Python Developer"
    assert job.seniority == "senior"
    assert job.company == "Acme Health"
    assert job.city == "Ереван, Армения"
    assert (job.salary_min, job.salary_max, job.currency) == (3000, 4500, "USD")
    assert job.job_url.startswith("https://acme.example/jobs/42")
    assert job.contact == "@acme_hr"
    assert job.work_mode == "remote"

    en = RuleExtractor().extract(posts()[3])[0]
    assert en.title == "Product Manager (Healthcare AI)"
    assert en.company == "MedTech Inc"
    assert en.contact == "jobs@medtech.example"
    assert (en.salary_min, en.currency) == (4000, "EUR")


def test_parse_salary_k():
    assert parse_salary("ЗП 150-200k руб") == (150000, 200000, "RUB")


def test_dedupe_exact_and_fuzzy():
    a = Job(title="Senior Python Developer", company="Acme", job_url="https://acme.example/j/1")
    b = Job(
        title="Senior Python Developer", company="Acme", job_url="https://www.acme.example/j/1/"
    )  # same link, other formatting
    c = Job(title="Python Developer (Senior)", company="Acme", contact="@hr")
    d = Job(title="Data Analyst", company="Acme", contact="@hr")
    dd = Deduper([], fuzzy_threshold=90)
    first = dd.check(a)
    assert first is not None
    assert dd.check(b) is None
    c2 = dd.check(c)
    assert c2 is not None and c2.possible_dup == first.hash
    d2 = dd.check(d)
    assert d2 is not None and d2.possible_dup == ""
    assert job_key(a) == job_key(b)


def test_build_rows_by_header_name():
    header = ["Моя колонка", "Должность", "Статус"]
    assert build_rows(header, [Job(title="QA")]) == [["", "QA", "новая"]]
    assert len(HEADER) == 27
    assert HEADER[-4:] == ["Сфера (совпадение)", "Роль (совпадение)", "Приоритет", "Совпадения"]


class FakeSource:
    def fetch(self, channel, after_id=0, max_posts=200, backfill_days=7):
        return [p for p in posts() if p.message_id > after_id]


def test_run_twice_writes_nothing_new(tmp_path):
    cfg = load_config(ROOT / "config.yaml")
    cfg["channels"] = ["testjobs"]
    cfg["domain_keywords"] = cfg["role_keywords"] = []  # fixture posts: generic IT
    store = CsvStore(tmp_path / "jobs.csv", tmp_path / "state.json")
    s1 = run(cfg, source=FakeSource(), store=store)
    assert s1["written"] == 2 and s1["read"] == 4
    assert store.load_state() == {"testjobs": 104}
    s2 = run(cfg, source=FakeSource(), store=store)
    assert s2["read"] == 0 and s2["written"] == 0
    # state lost -> posts re-read, dedupe catches them
    (tmp_path / "state.json").unlink()
    s3 = run(cfg, source=FakeSource(), store=store)
    assert s3["duplicates"] == 2 and s3["written"] == 0


def test_health_check_fails_when_all_channels_fail(tmp_path):
    class Broken:
        def fetch(self, *a, **k):
            raise RuntimeError("down")

    cfg = load_config(ROOT / "config.yaml")
    cfg["channels"] = ["testjobs"]
    cfg["telethon"]["channels"] = []
    store = CsvStore(tmp_path / "jobs.csv", tmp_path / "state.json")
    stats = run(cfg, source=Broken(), store=store)
    assert stats["channels_failed"] == 1 and stats["healthy"] is False


def test_post_url():
    assert Post(channel="x", message_id=5).url == "https://t.me/x/5"
