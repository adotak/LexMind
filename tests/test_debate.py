from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from lexmind import debate
from lexmind.api import create_app
from lexmind.library import Library

from .conftest import fake_llm

CASE = "Police arrested my brother three days ago and have not produced him before a magistrate. This is illegal."


@pytest.fixture(autouse=True)
def no_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def ai_client(*replies: object) -> TestClient:
    return TestClient(create_app(llm=fake_llm(*(json.dumps(r) for r in replies)), ask_per_minute=0))


def test_limits_find_exceptions(library: Library) -> None:
    art10 = library.get("10")
    art19 = library.get("19")
    assert art10 is not None and art19 is not None
    assert any(lim.text.startswith("(3) Nothing in clauses (1) and (2)") for lim in debate.limits(art10))
    assert "reasonable restrictions" in debate.limits(art19)[0].text
    long = debate.limits(art10, per_article=5, width=120)
    assert all(len(lim.text) <= 125 for lim in long) and any(lim.text.endswith("…") for lim in long)


def test_limits_none_for_plain_article(mini: Library) -> None:
    section = mini.get("1")
    assert section is not None and debate.limits(section) == []


def test_score_is_clamped() -> None:
    assert [debate.score(x) for x in (-3, 6.6, 42)] == [0, 7, 10]


def test_debate_without_ai_returns_articles_and_exceptions(client: TestClient) -> None:
    body = client.post("/api/debate", json={"position": CASE}).json()
    assert body["mode"] == "search" and body["verdict"] is None and body["rounds"] == []
    assert "10" in [s["article"] for s in body["sources"]]
    assert any(lim["article"] == "10" for lim in body["limits"])


def test_debate_without_ai_and_no_match(client: TestClient) -> None:
    body = client.post("/api/debate", json={"position": "zzzzqqqq xxxyyyy"}).json()
    assert body["sources"] == [] and "No article" in body["note"]


def test_full_debate_checks_both_sides() -> None:
    client = ai_client(
        {"attacks": [
            {"point": "Preventive detention",
             "argument": "The 24-hour rule does not cover preventive detention [Art. 10]. "
                         "He may be held for a year with no reason [Art. 999]."},
            {"point": "Invented rule", "argument": "Police can hold anyone for a month [Art. 999]."},
            {"point": "Travel time", "argument": "The time for the journey to the magistrate is excluded [Art. 10]."},
        ]},
        {"rebuttals": [
            'Preventive detention needs a law, and even then "no such law shall authorize the detention of a person '
            'for a period exceeding three months" without a Review Board [Art. 10]. A fair trial is also required '
            "[Art. 10A].",
            "I can't answer this from the law.",
        ]},
        {"you": 7.6, "opponent": 12, "summary": "You argued better [Art. 10]. The moon agrees [Art. 999].",
         "weak_spots": ["Prove he isn't held under a preventive detention law", " "]},
    )
    body = client.post("/api/debate", json={"position": CASE, "opponent": "He is a security threat."}).json()
    assert body["mode"] == "ai"
    rounds = body["rounds"]
    assert [r["point"] for r in rounds] == ["Preventive detention", "Travel time"]  # invented attack dropped
    assert "[Art. 999]" not in rounds[0]["attack"]
    assert "three months" in rounds[0]["rebuttal"] and "[Art. 10A]" not in rounds[0]["rebuttal"]
    assert any("10A" in r for r in rounds[0]["removed"])
    assert rounds[1]["rebuttal"] == ""  # no law-backed answer -> weak spot
    v = body["verdict"]
    assert (v["you"], v["opponent"]) == (8, 10)
    assert "moon" not in v["summary"] and "[Art. 10]" in v["summary"]
    assert v["weak_spots"][0] == "You have no law-backed answer yet to: Travel time"
    assert len(v["weak_spots"]) == 2 and "not a prediction" in v["note"]
    assert body["law_backed"] == {"you": 1, "opponent": 2}
    assert {c["article"]: c["verified"] for c in body["citations"]} == {"10": True, "999": False, "10A": False}


def test_debate_stops_when_no_attack_survives() -> None:
    client = ai_client({"attacks": [{"point": "Made up", "argument": "Arrests are always legal [Art. 999]."}]})
    body = client.post("/api/debate", json={"position": CASE}).json()
    assert body["rounds"] == [] and body["verdict"] is None and "couldn't build" in body["note"]


def test_unreadable_ai_reply_is_502() -> None:
    client = TestClient(create_app(llm=fake_llm("not json at all"), ask_per_minute=0))
    assert client.post("/api/debate", json={"position": CASE}).status_code == 502
    client = ai_client({"wrong": []})
    assert client.post("/api/debate", json={"position": CASE}).status_code == 502


def test_debate_validation_and_rate_limit() -> None:
    client = TestClient(create_app(ask_per_minute=1))
    assert client.post("/api/debate", json={"position": "short"}).status_code == 422
    assert client.post("/api/debate", json={"position": CASE, "opponent": "x" * 1501}).status_code == 422
    assert client.post("/api/debate", json={"position": CASE}).status_code == 200
    assert client.post("/api/debate", json={"position": CASE}).status_code == 429
