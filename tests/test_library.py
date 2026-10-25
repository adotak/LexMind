from __future__ import annotations

import re
from pathlib import Path

import pytest

from lexmind.library import Library, default_library, expand, stem, tokenize


def test_constitution_is_complete(library: Library) -> None:
    articles = [s.article for s in library.sections]
    assert len(articles) > 300
    assert len(set(articles)) == len(articles)
    for a in ["1", "2A", "8", "9A", "10", "10A", "19A", "25A", "185", "199", "280"]:
        assert library.get(a) is not None, a
    assert all(s.title for s in library.sections)


def test_article_text_is_clean(library: Library) -> None:
    for s in library.sections:
        assert "[" not in s.text and "]" not in s.text, s.article
        assert "__" not in s.text and " *" not in s.text, s.article
        assert "ANNEX" not in s.text, s.article
        assert s.text, s.article


def test_fundamental_rights_metadata(library: Library) -> None:
    art = library.get("10")
    assert art is not None
    assert art.title == "Safeguards as to arrest and detention"
    assert art.chapter == "Fundamental Rights"
    assert art.part.startswith("PART II")
    assert "twenty-four hours" in art.text
    assert library.get("25A") is not None and "five to sixteen" in library.get("25A").text  # type: ignore[union-attr]


@pytest.mark.parametrize(("question", "expected"), [
    ("Can the police keep me in custody without taking me to a magistrate?", "10"),
    ("Is education free for children?", "25A"),
    ("Do I have a right to information?", "19A"),
    ("Can I be punished twice for the same offence?", "13"),
    ("freedom of speech and the press", "19"),
    ("Is slavery or forced labour allowed?", "11"),
    ("right to a fair trial", "10A"),
    ("I want to criticise a minister online", "19"),
    ("My sister's government school is charging fees", "25A"),
    ("Can the government take my house without paying me", "24"),
    ("Can I hold a rally against the government", "16"),
    ("Can I start a political party", "17"),
    ("Can the government read my phone messages", "14"),
    ("My boss treats me differently because I am a woman", "25"),
    ("Can I be tried twice for the same crime", "13"),
    ("Can I be beaten in custody to confess", "14"),
    ("Can I travel to another province", "15"),
    ("Can they prosecute me again?", "13"),
    ("Can I live in another city?", "15"),
    ("How long is the term of the National Assembly", "52"),
])
def test_search_finds_the_right_article(library: Library, question: str, expected: str) -> None:
    top = [s.article for s, _ in library.search(question, limit=3)]
    assert expected in top, (question, top)


def test_search_pins_articles_named_in_the_query(library: Library) -> None:
    hits = library.search("what does Article 199 say about writs")
    assert hits[0][0].article == "199"


def test_get_accepts_labels(mini: Library) -> None:
    assert mini.get("article 2a") is not None
    assert mini.get(" 1 ") is not None
    assert mini.get("99") is None


def test_search_skips_omitted_and_handles_no_match(mini: Library) -> None:
    assert [s.article for s, _ in mini.search("rule omitted test act")] == []
    assert mini.search("zzzz") == []
    assert mini.search("arrested person detained")[0][0].article == "2"


def test_outline_groups_by_part_and_chapter(mini: Library) -> None:
    outline = mini.outline()
    assert outline[0]["part"] == "PART I"
    assert [c["chapter"] for c in outline[0]["chapters"]] == ["", "Rights"]


def test_tokenizer() -> None:
    assert stem("arrested") == "arrest"
    assert stem("liberties") == "liberty"
    assert tokenize("The police ARRESTED me!") == ["police", "arrest"]
    assert "custody" in expand("police")


def test_fundamental_rights_rank_above_equal_matches(library: Library) -> None:
    plain = Library.__new__(Library)
    plain.__dict__.update(library.__dict__)
    plain.RIGHTS_BOOST = 1.0
    query = "Can I use my own language"
    boosted = {s.article: score for s, score in library.search(query)}
    flat = {s.article: score for s, score in plain.search(query)}
    assert boosted["28"] == pytest.approx(flat["28"] * 1.5, rel=0.01)
    assert boosted["251"] == flat["251"]


def test_everyday_words_dont_hijack_procedural_questions(library: Library) -> None:
    assert library.search("What is the term of the National Assembly again?")[0][0].article == "52"
    city = [s.article for s, _ in library.search("How do city governments get elected?", limit=3)]
    assert "140A" in city and "15" not in city
    assert "13" not in [s.article for s, _ in library.search("Can the state prosecute a minister?", limit=3)]


TOPIC_TOP_ARTICLE = {
    "Arrest": "10",
    "Fair trial": "10A",
    "Free speech": "19",
    "Education": "25A",
    "Property": "24",
    "Religion": "20",
    "Privacy": "14",
    "Equality": "25",
    "Elections": "225",
}


def test_constitution_topic_buttons_find_their_articles() -> None:
    js = (Path(__file__).parents[1] / "lexmind/static/js/main.js").read_text()
    topics = dict(re.findall(r'\["([^"]+)", "([^"]+)"\]', js.split("const TOPICS")[1].split("];")[0]))
    assert set(topics) == set(TOPIC_TOP_ARTICLE)
    lib = default_library()
    for label, query in topics.items():
        hits = [s.article for s, _ in lib.search(query, limit=10)]
        assert hits[:1] == [TOPIC_TOP_ARTICLE[label]], (label, hits)
    assert "25A" not in [s.article for s, _ in lib.search(topics["Free speech"], limit=10)]
