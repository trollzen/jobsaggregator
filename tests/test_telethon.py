from datetime import UTC, datetime, timedelta

from telethon.tl.types import MessageEntityTextUrl, MessageEntityUrl

from jobagg.config import load_config
from jobagg.main import run
from jobagg.sources.telethon_src import TelethonSource, message_to_post
from jobagg.store import CsvStore

TEXT = (
    "Вакансия: Data Analyst\nКомпания: MedCo\nЗарплата: 2000-3000 $\n"
    "Отклик: medco.example/apply и тут"
)


class FakeMsg:
    def __init__(self, mid, text=TEXT, days_ago=0):
        self.id = mid
        self.message = text
        self.date = datetime.now(UTC) - timedelta(days=days_ago)
        start = text.index("medco.example")
        self.entities = [
            MessageEntityUrl(offset=start, length=len("medco.example/apply")),
            MessageEntityTextUrl(offset=text.index("тут"), length=3, url="https://hr.example/x"),
        ]

    def get_entities_text(self):
        return [(e, self.message[e.offset : e.offset + e.length]) for e in self.entities]


class FakeClient:
    def __init__(self, msgs):
        self.msgs = msgs

    def iter_messages(self, entity, min_id=0, limit=None):
        out = [m for m in sorted(self.msgs, key=lambda m: -m.id) if m.id > min_id]
        return out[:limit]


def test_message_to_post_links_and_private_url():
    p = message_to_post(FakeMsg(7), "closed", -1001234567890)
    assert p.links == ["https://medco.example/apply", "https://hr.example/x"]
    assert p.url == "https://t.me/c/1234567890/7"


def test_fetch_respects_state_and_backfill():
    src = TelethonSource(
        [{"name": "closed", "id": -1001}],
        client=FakeClient([FakeMsg(1, days_ago=30), FakeMsg(2), FakeMsg(3)]),
    )
    assert [p.message_id for p in src.fetch("closed")] == [2, 3]
    assert [p.message_id for p in src.fetch("closed", after_id=2)] == [3]


def test_run_with_closed_channel(tmp_path):
    cfg = load_config("config.yaml")
    cfg["channels"] = []
    cfg["telethon"]["channels"] = [{"name": "closed", "id": -1001}]
    cfg["domain_keywords"] = cfg["role_keywords"] = []  # fake post: generic IT
    tg = TelethonSource(cfg["telethon"]["channels"], client=FakeClient([FakeMsg(5)]))
    store = CsvStore(tmp_path / "jobs.csv", tmp_path / "state.json")
    stats = run(cfg, store=store, tg_source=tg)
    assert stats["written"] == 1 and store.load_state() == {"closed": 5}
    job = store.load_jobs()[0]
    assert job.title == "Data Analyst"
