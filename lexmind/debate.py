"""Counter-Argument Engine: an AI opponent attacks your position, LexMind rebuts, an AI judge scores it.

All three roles see only the Constitution articles found for the case. Every attack and rebuttal goes
through the Citation Checker, so neither side can win a point with an invented or misquoted article.
Without an AI key it still finds the articles on your side and the exceptions the other side is most
likely to use against you.
"""
from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, Field

from . import brain
from .citations import Citation, check
from .library import Library, Section

MAX_SOURCES = 8
MAX_ATTACKS = 3
LIMIT_MARKERS = re.compile(
    r"\b(subject to|provided (?:further )?that|nothing in|save (?:in accordance|for|by|as)|except|unless|"
    r"shall not apply|reasonable restrictions?)\b",
    re.I,
)
RULES = (
    "Use ONLY the Constitution articles provided. Cite every legal claim like [Art. 10A], citing only the "
    "provided articles. If you quote the law, copy the words exactly inside double quotes, followed by the "
    "citation. Use plain, simple English. Never invent laws, cases or facts."
)
OPPONENT_PROMPT = (
    "You are the other side's lawyer in a practice debate about the law of Pakistan. Find the strongest attacks "
    f"on the user's position, especially using the exceptions, conditions and limits in the articles. Give at most "
    f"{MAX_ATTACKS} attacks, strongest first, each 2-3 sentences. {RULES} Reply with JSON only: "
    '{{"attacks": [{{"point": "short headline", "argument": "the attack"}}]}}'
)
DEFENDER_PROMPT = (
    "You are LexMind, defending the user's position in a practice debate about the law of Pakistan. Rebut each "
    f"attack in 2-3 sentences. {RULES} If the law gives the user no answer to an attack, say so honestly in one "
    'sentence without a citation. Reply with JSON only, one rebuttal per attack in the same order: '
    '{{"rebuttals": ["rebuttal to attack 1", "rebuttal to attack 2"]}}'
)
JUDGE_PROMPT = (
    "You are a strict, neutral judge scoring a practice debate about the law of Pakistan. Score each side from 0 "
    "to 10 only on how well its points are backed by the Constitution articles; claims without a citation count "
    "for little. Reply with JSON only: "
    '{{"you": 0, "opponent": 0, "summary": "two sentences on who argued better and why", '
    '"weak_spots": ["up to 3 short things the user must prove or prepare for"]}}'
)
JUDGE_NOTE = "The AI judge's score is practice, not a prediction of what a real court will decide."


class Limit(BaseModel):
    """An exception or condition in an article: where the other side is most likely to push back."""

    article: str
    title: str
    text: str


class Round(BaseModel):
    point: str
    attack: str
    rebuttal: str  # empty when LexMind had no law-backed answer
    removed: list[str]


class Verdict(BaseModel):
    you: int
    opponent: int
    summary: str
    weak_spots: list[str]
    note: str = JUDGE_NOTE


class Debate(BaseModel):
    position: str
    opponent: str
    mode: str  # "ai" or "search"
    note: str
    rounds: list[Round]
    verdict: Verdict | None
    law_backed: dict[str, int]  # verified citations per side
    limits: list[Limit]
    sources: list[brain.Source]
    citations: list[Citation]
    disclaimer: str = brain.DISCLAIMER


class _Attack(BaseModel):
    point: str
    argument: str


class _Attacks(BaseModel):
    attacks: list[_Attack]


class _Rebuttals(BaseModel):
    rebuttals: list[str]


class _Judgement(BaseModel):
    you: float
    opponent: float
    summary: str
    weak_spots: list[str] = Field(default_factory=list)


def limits(section: Section, per_article: int = 2, width: int = 300) -> list[Limit]:
    """Clauses of an article that narrow the right it gives (provisos, "subject to", "nothing in", ...)."""
    found: list[Limit] = []
    for clause in section.text.split("\n"):
        m = LIMIT_MARKERS.search(clause)
        if not m:
            continue
        text = clause.strip()
        if len(text) > width:
            start = max(0, m.start() - 80)
            text = ("…" if start else "") + clause[start:start + width].strip()
            text = text.rsplit(" ", 1)[0] + "…"
        found.append(Limit(article=section.article, title=section.title, text=text))
        if len(found) == per_article:
            break
    return found


def score(x: float) -> int:
    return int(round(min(10.0, max(0.0, x))))


def _chain(llm: Any, system: str, human: str) -> Any:
    from langchain_core.output_parsers import JsonOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    return ChatPromptTemplate.from_messages([("system", system), ("human", human)]) | llm | JsonOutputParser()


def debate(library: Library, position: str, opponent: str = "", llm: Any = None) -> Debate:
    hits = library.search(f"{position} {opponent}", limit=MAX_SOURCES)
    sections = [s for s, _ in hits]
    sources = [brain.Source(article=s.article, title=s.title, chapter=s.chapter, part=s.part,
                            snippet=brain.snippet(s.text), score=sc) for s, sc in hits]
    found = [lim for s in sections for lim in limits(s)][:6]

    def result(mode: str, note: str, rounds: list[Round], verdict: Verdict | None, law_backed: dict[str, int],
               citations: list[Citation]) -> Debate:
        return Debate(position=position, opponent=opponent, mode=mode, note=note, rounds=rounds, verdict=verdict,
                      law_backed=law_backed, limits=found, sources=sources, citations=citations)

    if llm is None and not brain.enabled():
        note = ("AI debate is off, so here are the articles on your side and the exceptions the other side is "
                "most likely to use." if hits else "No article of the Constitution matched. Try different words.")
        return result("search", note, [], None, {}, [])

    llm = llm or brain.default_llm()
    allowed = {s.article for s in sections}
    ctx = brain.context(sections)
    limit_text = "\n".join(f"[Art. {lim.article}] {lim.text}" for lim in found) or "(none found)"
    citations: dict[str, Citation] = {}
    backed = {"you": 0, "opponent": 0}

    def checked(text: str, side: str) -> tuple[str, list[str]]:
        result = check(library, text, allowed)
        for c in result.citations:
            if c.article not in citations or citations[c.article].verified:
                citations[c.article] = c
        backed[side] += len(result.verified_articles)
        return result.answer, result.removed

    attacks = _Attacks.model_validate(_chain(llm, OPPONENT_PROMPT, "Sources:\n{context}\n\nExceptions in these "
                                             "articles:\n{limits}\n\nUser's position: {position}\nWhat the other "
                                             "side says: {opponent}").invoke(
        {"context": ctx, "limits": limit_text, "position": position, "opponent": opponent or "(not given)"}))
    rounds: list[Round] = []
    for a in attacks.attacks[:MAX_ATTACKS]:
        text, removed = checked(a.argument, "opponent")
        if text:  # an attack with no law-backed sentence left isn't worth answering
            rounds.append(Round(point=a.point.strip(), attack=text, rebuttal="", removed=removed))
    if not rounds:
        return result("ai", "The other side couldn't build a law-backed attack from these articles.", [], None,
                      backed, list(citations.values()))

    listing = "\n".join(f"{i}. {r.point}: {r.attack}" for i, r in enumerate(rounds, 1))
    rebuttals = _Rebuttals.model_validate(_chain(llm, DEFENDER_PROMPT, "Sources:\n{context}\n\nUser's position: "
                                                 "{position}\n\nAttacks:\n{attacks}").invoke(
        {"context": ctx, "position": position, "attacks": listing}))
    for r, reply in zip(rounds, rebuttals.rebuttals, strict=False):
        text, removed = checked(reply, "you")
        r.rebuttal = text if any(c in text for c in ("[Art", "[art")) else ""
        r.removed += removed

    transcript = "\n\n".join(f"Attack {i}: {r.point}\nOther side: {r.attack}\nUser: "
                             f"{r.rebuttal or '(no law-backed answer)'}" for i, r in enumerate(rounds, 1))
    judged = _Judgement.model_validate(_chain(llm, JUDGE_PROMPT, "User's position: {position}\n\n{transcript}\n\n"
                                              "Verified citations: user {you}, other side {opp}").invoke(
        {"position": position, "transcript": transcript, "you": backed["you"], "opp": backed["opponent"]}))
    summary = check(library, judged.summary, allowed).answer
    unanswered = [f"You have no law-backed answer yet to: {r.point}" for r in rounds if not r.rebuttal]
    verdict = Verdict(you=score(judged.you), opponent=score(judged.opponent), summary=summary,
                      weak_spots=(unanswered + [w.strip() for w in judged.weak_spots if w.strip()])[:4])
    return result("ai", "", rounds, verdict, backed, list(citations.values()))
