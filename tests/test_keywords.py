from pathlib import Path

from jobagg.config import load_config
from jobagg.keywords import KeywordList, TopicFilter, normalize

ROOT = Path(__file__).resolve().parents[1]
CFG = load_config(ROOT / "config.yaml")
TOPIC = TopicFilter.from_config(CFG)
VACANCY = "Ищем в команду, удалёнка. "  # filler; topic filter only looks at keywords


def domain(text: str) -> list[str]:
    return TOPIC.domain.find(TOPIC.ignore.remove(normalize(text)))


def roles(text: str) -> list[str]:
    return TOPIC.roles.find(normalize(text))


def test_rules():
    kw = KeywordList(["[PM], клиник*, бизнес-аналитик*, real world evidence"])
    assert kw.find(normalize("Работа в КЛИНИКЕ")) == ["клиник*"]
    assert kw.find(normalize("Бизнес аналитик")) == ["бизнес-аналитик*"]
    assert kw.find(normalize("Real-World Evidence")) == ["real world evidence"]
    assert kw.find(normalize("Senior PM, remote")) == ["PM"]
    assert kw.find(normalize("PM: Иван")) == ["PM"]
    assert normalize("Ёлка  —\nбизнес-аналитик") == "елка — бизнес аналитик"


def test_benefits_are_not_domain():
    assert domain(VACANCY + "Python developer. Бонусы: ДМС, спортзал") == []
    assert domain(VACANCY + "Backend engineer. Benefits: private healthcare, gym") == []
    assert domain(VACANCY + "Полис ДМС со стоматологией") == ["стоматолог*"]  # real word left


def test_be_patient_is_not_domain():
    assert domain(VACANCY + "You need to be patient with stakeholders") == []


def test_gcp_is_not_domain():
    assert domain(VACANCY + "DevOps: AWS, GCP, Kubernetes") == []


def test_npm_and_time_are_not_pm():
    assert "PM" not in roles("Frontend: React, npm, webpack")
    assert "PM" not in roles("Daily standup at 5 pm CET")
    assert "PM" not in roles("Созвон в 10:30 PM")


def test_clinical_pm_in_biotech_passes_both():
    reason, dom, role = TOPIC.check("Clinical Project Manager в биотех-компании")
    assert reason is None
    assert "биотех*" in dom
    assert "clinical project manager" in role


def test_reasons_and_switched_off_filter():
    assert TOPIC.check("Python developer, fintech")[0] == "not_domain"
    assert TOPIC.check("Senior Python developer in a hospital")[0] == "not_role"
    assert TopicFilter().check("anything") == (None, "", "")
