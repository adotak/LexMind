from __future__ import annotations

from lexmind.citations import check
from lexmind.library import Library


def test_verified_citations_are_kept(mini: Library) -> None:
    r = check(mini, "You have a right to water [Art. 1]. Police must free you within a day [Art. 2].", {"1", "2"})
    assert r.removed == []
    assert r.verified_articles == ["1", "2"]
    assert "[Art. 2]" in r.answer


def test_invented_article_is_removed(mini: Library) -> None:
    r = check(mini, "Water is a right [Art. 1]. You may also sue the moon [Art. 77].", {"1", "2"})
    assert r.answer == "Water is a right [Art. 1]."
    assert r.removed == ["You may also sue the moon [Art. 77]."]
    bad = [c for c in r.citations if not c.verified]
    assert bad[0].article == "77" and "No such article" in bad[0].reason


def test_article_outside_the_sources_is_removed(mini: Library) -> None:
    r = check(mini, "Detention is limited [Art. 2].", {"1"})
    assert r.answer == ""
    assert "not in the sources" in r.citations[0].reason


def test_misquote_is_removed_and_real_quote_kept(mini: Library) -> None:
    good = 'It says "access to clean drinking water" [Art. 1].'
    bad = 'It says "free bottled water for everyone" [Art. 1].'
    r = check(mini, f"{good} {bad}", {"1"})
    assert r.answer == good
    assert r.removed == [bad]
    assert r.citations[0].verified is False and "Quoted words" in r.citations[0].reason


def test_uncited_sentences_pass_through(mini: Library) -> None:
    r = check(mini, "Short answer: yes.\nThis depends on the facts.", set())
    assert r.answer == "Short answer: yes. This depends on the facts."
    assert r.citations == []
