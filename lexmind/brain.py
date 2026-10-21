"""Law Brain: answers a legal question from the Constitution only, then runs the Citation Checker.

Turned on by setting ``OPENAI_API_KEY`` (and optionally ``OPENAI_MODEL``). Without a key LexMind still
works: it returns the most relevant articles instead of a written answer.
"""
from __future__ import annotations

import os
from typing import Any, cast

from pydantic import BaseModel

from .citations import Citation, check
from .library import Library, Section

DEFAULT_MODEL = "gpt-4o-mini"
MAX_SOURCES = 6
SYSTEM_PROMPT = (
    "You are LexMind, a legal information assistant for Pakistan. Answer ONLY from the Constitution articles "
    "provided. After every sentence that states the law, cite its article like [Art. 10A]. Only cite articles "
    "from the sources given. If you quote the law, copy the words exactly inside double quotes, followed by "
    "the citation. Lead with a one-sentence direct answer, then explain in plain, simple English (short "
    "sentences, no legal jargon). If the sources do not answer the question, say so plainly and suggest what "
    "kind of law or lawyer would. Never invent laws, cases or facts. You give legal information, not advice."
)
DISCLAIMER = (
    "LexMind gives legal information, not legal advice. For anything serious, talk to a licensed advocate."
)


class Source(BaseModel):
    article: str
    title: str
    chapter: str
    part: str
    snippet: str
    score: float


class Answer(BaseModel):
    question: str
    answer: str
    mode: str  # "ai" or "search"
    sources: list[Source]
    citations: list[Citation]
    removed: list[str]
    disclaimer: str = DISCLAIMER


def enabled() -> bool:
    return bool(os.environ.get("OPENAI_API_KEY"))


def default_llm() -> Any:
    from langchain_openai import ChatOpenAI

    return ChatOpenAI(model=os.environ.get("OPENAI_MODEL") or DEFAULT_MODEL, temperature=0.1, timeout=40,
                      max_retries=1)


def snippet(text: str, limit: int = 320) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def context(sections: list[Section]) -> str:
    return "\n\n".join(f"[Art. {s.article}] {s.title}\n{s.text}" for s in sections)


def ask(library: Library, question: str, llm: Any = None) -> Answer:
    hits = library.search(question, limit=MAX_SOURCES)
    sources = [Source(article=s.article, title=s.title, chapter=s.chapter, part=s.part, snippet=snippet(s.text),
                      score=score) for s, score in hits]
    if llm is None and not enabled():
        text = ("AI answers are off, so here are the articles of the Constitution that best match your question."
                if hits else "No article of the Constitution matched your question. Try different words.")
        return Answer(question=question, answer=text, mode="search", sources=sources, citations=[], removed=[])

    from langchain_core.output_parsers import StrOutputParser
    from langchain_core.prompts import ChatPromptTemplate

    prompt = ChatPromptTemplate.from_messages([
        ("system", SYSTEM_PROMPT),
        ("human", "Sources:\n{context}\n\nQuestion: {question}"),
    ])
    chain = prompt | (llm or default_llm()) | StrOutputParser()
    raw = cast(str, chain.invoke({"context": context([s for s, _ in hits]), "question": question}))
    result = check(library, raw, {s.article for s, _ in hits})
    answer = result.answer or "I couldn't give an answer backed by a verified source. Try rephrasing."
    return Answer(question=question, answer=answer, mode="ai", sources=sources, citations=result.citations,
                  removed=result.removed)
