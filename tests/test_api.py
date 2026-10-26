from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient

from lexmind import brain
from lexmind.api import RateLimiter, create_app

from .conftest import fake_llm


@pytest.fixture(autouse=True)
def no_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)


def test_health_and_security_headers(client: TestClient) -> None:
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["articles"] > 300 and r.json()["ai"] is False
    assert "script-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["x-content-type-options"] == "nosniff"


def test_index_and_static(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200 and "LexMind" in r.text
    assert client.get("/static/js/main.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_library_and_article(client: TestClient) -> None:
    lib = client.get("/api/library").json()
    assert lib["source_url"].startswith("https://na.gov.pk/")
    assert any(p["part"].startswith("PART II") for p in lib["outline"])
    art = client.get("/api/articles/10a").json()
    assert art["article"] == "10A" and art["title"] == "Right to fair trial"
    assert client.get("/api/articles/999").status_code == 404


def test_search(client: TestClient) -> None:
    hits = client.get("/api/search", params={"q": "right to education"}).json()
    assert hits[0]["article"] == "25A"
    assert client.get("/api/search", params={"q": "x"}).status_code == 422


def test_ask_without_ai_returns_sources(client: TestClient) -> None:
    r = client.post("/api/ask", json={"question": "Can police hold me without a magistrate?"})
    body = r.json()
    assert r.status_code == 200 and body["mode"] == "search"
    assert "10" in [s["article"] for s in body["sources"]]
    assert "not legal advice" in body["disclaimer"]


def test_ask_with_ai_verifies_citations() -> None:
    llm = fake_llm(
        "No, they must take you to a magistrate within 24 hours [Art. 10]. "
        'The Constitution says you must be "produced before a magistrate within a period of twenty-four hours" '
        "[Art. 10]. You can also get free legal aid from the moon [Art. 999]."
    )
    client = TestClient(create_app(llm=llm, ask_per_minute=0))
    body = client.post("/api/ask", json={"question": "Can police hold me without a magistrate?"}).json()
    assert body["mode"] == "ai"
    assert "[Art. 10]" in body["answer"] and "moon" not in body["answer"]
    assert body["removed"] == ["You can also get free legal aid from the moon [Art. 999]."]
    assert {c["article"]: c["verified"] for c in body["citations"]} == {"10": True, "999": False}


def test_ask_with_no_verified_answer_says_so() -> None:
    client = TestClient(create_app(llm=fake_llm("Totally made up [Art. 500]."), ask_per_minute=0))
    body = client.post("/api/ask", json={"question": "anything about arrest"}).json()
    assert "verified source" in body["answer"]


def test_ask_validation_and_rate_limit() -> None:
    client = TestClient(create_app(ask_per_minute=2))
    assert client.post("/api/ask", json={"question": "hi"}).status_code == 422
    assert client.post("/api/ask", json={"question": "x" * 1001}).status_code == 422
    codes = [client.post("/api/ask", json={"question": "right to education"}).status_code for _ in range(3)]
    assert codes == [200, 200, 429]


def test_ai_failure_returns_502() -> None:
    class Broken:
        def invoke(self, *_: Any, **__: Any) -> Any:
            raise RuntimeError("provider down")

    from langchain_core.runnables import RunnableLambda

    llm = RunnableLambda(lambda _: Broken().invoke())
    client = TestClient(create_app(llm=llm, ask_per_minute=0))
    assert client.post("/api/ask", json={"question": "right to education"}).status_code == 502


def test_rate_limiter_disabled_and_window() -> None:
    assert all(RateLimiter(0).allow("a") for _ in range(50))
    lim = RateLimiter(1)
    assert lim.allow("a") and not lim.allow("a") and lim.allow("b")


def test_rate_limiter_discards_inactive_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    now = iter((0.0, 61.0))
    monkeypatch.setattr("lexmind.api.time.monotonic", lambda: next(now))
    lim = RateLimiter(1)
    assert lim.allow("a")
    assert lim.allow("b")
    assert "a" not in lim.hits
    assert "b" in lim.hits


def test_enabled_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    assert brain.enabled() is False
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    assert brain.enabled() is True
    assert brain.default_llm().model_name == brain.DEFAULT_MODEL
