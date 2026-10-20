"""Citation Checker: every claim the AI makes must point at a real article that says what the AI claims.

The model cites sources as ``[Art. 10A]``. A citation passes only if the article exists in the library
and was one of the sources the model was given. Any text in double quotes right before a citation must
appear word for word in that article. Sentences with a failed citation are removed from the answer.
"""
from __future__ import annotations

import re

from pydantic import BaseModel

from .library import Library

CITE = re.compile(r"\[Art\.?\s*(\d{1,3}[A-Za-z]{0,3})\]", re.I)
QUOTE = re.compile(r"[\"“]([^\"”]{8,})[\"”]\s*$")
SENTENCE_END = re.compile(r"(?<=[.!?])(?<![Aa]rt\.)\s+|\n+")


class Citation(BaseModel):
    article: str
    verified: bool
    reason: str = ""


class CheckResult(BaseModel):
    answer: str
    citations: list[Citation]
    removed: list[str]

    @property
    def verified_articles(self) -> list[str]:
        return [c.article for c in self.citations if c.verified]


def _normalize(text: str) -> str:
    text = text.replace("“", '"').replace("”", '"').replace("‘", "'").replace("’", "'")
    text = re.sub(r"[–—-]", "-", text)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s\-'\"]", " ", text.lower())).strip()


def check_citation(library: Library, article: str, allowed: set[str], before: str) -> Citation:
    section = library.get(article)
    if section is None:
        return Citation(article=article.upper(), verified=False, reason="No such article in the Constitution")
    if section.article not in allowed:
        return Citation(article=section.article, verified=False, reason="Article was not in the sources searched")
    quote = QUOTE.search(before)
    if quote and _normalize(quote.group(1)) not in _normalize(section.text):
        return Citation(article=section.article, verified=False, reason="Quoted words are not in this article")
    return Citation(article=section.article, verified=True)


def check(library: Library, answer: str, allowed: set[str]) -> CheckResult:
    """Verify every ``[Art. N]`` in ``answer``; drop sentences whose citations fail."""
    kept: list[str] = []
    removed: list[str] = []
    citations: dict[str, Citation] = {}
    for sentence in (s for s in SENTENCE_END.split(answer.strip()) if s.strip()):
        ok = True
        pos = 0
        for m in CITE.finditer(sentence):
            c = check_citation(library, m.group(1), allowed, sentence[pos:m.start()])
            pos = m.end()
            prev = citations.get(c.article)
            if prev is None or prev.verified:
                citations[c.article] = c
            ok = ok and c.verified
        (kept if ok else removed).append(sentence.strip())
    return CheckResult(answer=" ".join(kept).strip(), citations=list(citations.values()), removed=removed)
