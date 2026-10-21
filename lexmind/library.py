"""The law library: articles of the Constitution of Pakistan, searchable by meaning-ish keyword ranking (BM25).

BM25 runs in plain Python on ~300 articles in a few milliseconds, so the library needs no database or
embedding service. Swap in pgvector when the library grows to many laws.
"""
from __future__ import annotations

import json
import math
import re
from collections import Counter
from functools import lru_cache
from importlib import resources
from typing import Any

from pydantic import BaseModel

STOPWORDS = frozenset(
    "a an and are as at be been by can could do does for from had has have he her his how i if in into is it its "
    "may me my no not of on or our shall she should so such than that the their them then there these they this "
    "to under was we were what when where which who whom why will with without would you your any all also other "
    "said being upon".split()
)
SYNONYMS = {
    "police": ["arrest", "detain", "custody"],
    "jail": ["detention", "custody", "imprisonment"],
    "prison": ["detention", "imprisonment"],
    "lawyer": ["legal", "practitioner"],
    "advocate": ["legal", "practitioner"],
    "school": ["education"],
    "job": ["service", "employment", "profession"],
    "work": ["labour", "employment", "service"],
    "speech": ["expression"],
    "protest": ["assembly"],
    "religion": ["religious", "profess"],
    "women": ["sex", "women"],
    "gender": ["sex"],
    "house": ["property", "dwelling"],
    "land": ["property"],
    "privacy": ["privacy", "home", "dignity"],
    "tax": ["taxation", "taxes"],
    "vote": ["election", "elections"],
    "court": ["court", "judicial"],
    "torture": ["torture", "dignity", "evidence"],
}
ARTICLE_REF = re.compile(r"\b(?:art(?:icle)?s?\.?)\s*(\d{1,3}[A-Za-z]{0,3})\b", re.I)


class Section(BaseModel):
    id: str
    label: str
    article: str
    title: str
    part: str
    chapter: str
    page: int
    text: str
    omitted: bool = False


def stem(word: str) -> str:
    for suffix in ("ations", "ation", "ments", "ment", "ings", "ing", "ies", "ed", "es", "s"):
        if len(word) > len(suffix) + 3 and word.endswith(suffix):
            return word[: -len(suffix)] + ("y" if suffix == "ies" else "")
    return word


def tokenize(text: str) -> list[str]:
    return [stem(w) for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in STOPWORDS and len(w) > 1]


def expand(query: str) -> dict[str, float]:
    """Query terms with weights: the user's own words count fully, synonyms count half."""
    words = re.findall(r"[a-z]+", query.lower())
    terms = {stem(s): 0.5 for w in words for s in SYNONYMS.get(w, [])}
    terms.update(dict.fromkeys(tokenize(query), 1.0))
    return terms


class Library:
    """Search and lookup over one law's sections."""

    MIN_SHARE = 0.3  # drop weak matches scoring under 30% of the best one

    K1 = 1.4
    B = 0.75
    TITLE_WEIGHT = 3

    def __init__(self, data: dict[str, Any]):
        self.law: str = data["law"]
        self.jurisdiction: str = data["jurisdiction"]
        self.source_name: str = data["source_name"]
        self.source_url: str = data["source_url"]
        self.sections = [Section(**s) for s in data["sections"]]
        self._by_article = {s.article.upper(): s for s in self.sections}
        self._docs: list[Counter[str]] = []
        for s in self.sections:
            doc = Counter(tokenize(s.text))
            for tok in tokenize(f"{s.title} {s.chapter}"):
                doc[tok] += self.TITLE_WEIGHT
            self._docs.append(doc)
        self._lengths = [sum(d.values()) for d in self._docs]
        self._avg = sum(self._lengths) / max(len(self._lengths), 1)
        df: Counter[str] = Counter()
        for d in self._docs:
            df.update(d.keys())
        n = len(self._docs)
        self._idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def get(self, article: str) -> Section | None:
        return self._by_article.get(article.strip().upper().removeprefix("ARTICLE").strip())

    def search(self, query: str, limit: int = 5) -> list[tuple[Section, float]]:
        terms = expand(query)
        scores: list[tuple[float, int]] = []
        for i, doc in enumerate(self._docs):
            if self.sections[i].omitted:
                continue
            score = 0.0
            norm = self.K1 * (1 - self.B + self.B * self._lengths[i] / self._avg)
            for t, weight in terms.items():
                tf = doc.get(t, 0)
                if tf:
                    score += weight * self._idf[t] * tf * (self.K1 + 1) / (tf + norm)
            if score > 0:
                scores.append((score, i))
        scores.sort(reverse=True)
        floor = scores[0][0] * self.MIN_SHARE if scores else 0.0
        hits = [(self.sections[i], round(s, 3)) for s, i in scores[:limit] if s >= floor]
        named = [self.get(a) for a in ARTICLE_REF.findall(query)]
        pinned = [(s, 99.0) for s in named if s is not None]
        seen = {s.id for s, _ in pinned}
        return (pinned + [h for h in hits if h[0].id not in seen])[:limit]

    def outline(self) -> list[dict[str, Any]]:
        """Parts -> chapters -> article labels, for browsing."""
        parts: dict[str, dict[str, list[dict[str, str]]]] = {}
        for s in self.sections:
            parts.setdefault(s.part, {}).setdefault(s.chapter, []).append(
                {"article": s.article, "title": s.title})
        return [{"part": p, "chapters": [{"chapter": c, "articles": a} for c, a in ch.items()]}
                for p, ch in parts.items()]


@lru_cache(maxsize=1)
def default_library() -> Library:
    raw = resources.files("lexmind").joinpath("data/constitution_pk.json").read_text(encoding="utf-8")
    return Library(json.loads(raw))
