"""Build ``lexmind/data/constitution_pk.json`` from the official National Assembly PDF.

Needs the ``data`` extra (``pip install -e ".[data]"``). Run: ``python scripts/build_library.py``.

The PDF puts article text in an 11pt main column, side headings and footnotes in 8pt, and footnote
markers in 4-5.5pt superscript, so filtering characters by size leaves just the law text. Article numbers
are bold at the start of a line; article titles come from the table of contents.
"""
from __future__ import annotations

import io
import json
import re
import sys
import urllib.request
from pathlib import Path
from typing import Any

import pdfplumber

SOURCE_URL = "https://na.gov.pk/uploads/documents/6926e060076ed_467.pdf"
SOURCE_NAME = "Constitution of the Islamic Republic of Pakistan [As amended upto the 21st November, 2025]"
OUT = Path(__file__).resolve().parent.parent / "lexmind" / "data" / "constitution_pk.json"
PAGE_OFFSET = 22  # printed page 5 is PDF page 27
ARTICLE_RE = re.compile(r"^[\s\[]*(\d{1,3}[A-Z]{0,3})\.(?=\s|\(|$)")
TOC_RE = re.compile(r"^(\d{1,3}[A-Z]{0,3})\.\s+(.*)$")
ROMAN = {"I": 1, "V": 5, "X": 10, "L": 50}


def download() -> bytes:
    req = urllib.request.Request(SOURCE_URL, headers={"User-Agent": "Mozilla/5.0 LexMind data builder"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        return bytes(resp.read())


def toc_titles(pdf: Any) -> dict[str, str]:
    lines: list[str] = []
    for page in pdf.pages[2:26]:
        lines += (page.extract_text() or "").splitlines()
    titles: dict[str, str] = {}
    current: str | None = None
    for raw in lines:
        line = re.sub(r"\s+\d+[–-]\d+$", "", raw.strip())
        if line.startswith(("PART ", "CHAPTER", "ARTICLES", "CONSTITUTION OF", "ANNEX", "SCHEDULES", "––")):
            current = None
            continue
        if re.fullmatch(r"\(?[ivxl]+\)?", line) or not line:
            continue
        m = TOC_RE.match(line)
        if m and (current is None or _key(m.group(1)) > _key(current)):
            current = m.group(1)
            titles[current] = m.group(2)
        elif current and line[:1].islower():
            prev = titles[current]
            titles[current] = prev[:-1] + line if prev.endswith("-") else f"{prev} {line}"
        else:
            current = None
    return {k: re.sub(r"\s+", " ", v).strip().rstrip(".") for k, v in titles.items()}


def _key(article: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([A-Z]*)", article)
    assert m
    return int(m.group(1)), m.group(2)


def _roman(s: str) -> int:
    total = 0
    for i, ch in enumerate(s):
        v = ROMAN[ch]
        total += -v if i + 1 < len(s) and ROMAN[s[i + 1]] > v else v
    return total


def page_lines(page: Any) -> list[list[dict[str, Any]]]:
    chars = [c for c in page.chars if c["top"] > 100 and c["size"] >= 7.5 and 150 <= c["x0"] <= 455]
    chars.sort(key=lambda c: (c["top"], c["x0"]))
    rows: list[list[dict[str, Any]]] = []
    for ch in chars:
        if rows and abs(rows[-1][0]["top"] - ch["top"]) <= 3:
            rows[-1].append(ch)
        else:
            rows.append([ch])
    return [sorted(r, key=lambda c: c["x0"]) for r in rows]


def text_of(chars: list[dict[str, Any]]) -> str:
    out = ""
    prev = None
    for c in chars:
        if prev is not None and c["x0"] - prev["x1"] > 1.5 and not out.endswith(" "):
            out += " "
        out += c["text"]
        prev = c
    return out


SMALL_WORDS = {"and", "of", "the", "to", "between", "relating", "in"}


def title_case(text: str) -> str:
    if not text.isupper():
        return text
    words = [w.lower() if i and w.lower() in SMALL_WORDS else w.capitalize() for i, w in enumerate(text.split())]
    return " ".join(words).replace("Majlis-e-shoora (parliament)", "Majlis-e-Shoora (Parliament)")


def clean(text: str) -> str:
    text = text.replace("[", "").replace("]", "")
    text = re.sub(r"(\s*\*){3,}", " ", text)
    text = re.sub(r"\s\*(?=[\s.,;:]|$)", "", text)
    text = re.sub(r"_{2,}", "", text)
    text = text.replace("‘‘", "“").replace("’’", "”").replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\s+([,;:.])", r"\1", text)
    return text.strip()


def articles(pdf: Any, titles: dict[str, str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    part = chapter = ""
    part_title_next = False
    current: dict[str, Any] | None = None
    for pno in range(26, len(pdf.pages)):
        for row in page_lines(pdf.pages[pno]):
            raw = text_of(row).strip()
            body = [c for c in row if c["size"] >= 10.5]
            bold = bool(body) and sum("Bold" in c["fontname"] for c in body) / len(body) > 0.5
            if re.sub(r"[\s_\[]", "", raw).startswith("ANNEX"):
                if current:
                    out.append(current)
                return out
            if re.fullmatch(r"PART [IVXL]+", raw) and bold:
                part, chapter, part_title_next = raw, "", True
                continue
            if part_title_next and bold:
                part = f"{part} — {raw}"
                part_title_next = False
                continue
            if re.match(r"^\[?CHAPTER|^C\d+[A-Z]?\.", raw):
                chapter = re.sub(r"[\d\[\]]", "", raw.split("–", 1)[-1].split("—", 1)[-1]).strip(" .")
                continue
            if not body:
                continue
            body_text = text_of(body)
            m = ARTICLE_RE.match(body_text)
            digit = next((c for c in body if c["text"].isdigit()), None)
            if (m and digit is not None and "Bold" in digit["fontname"]
                    and (current is None or _key(m.group(1)) > _key(current["article"]))):
                if current:
                    out.append(current)
                num = m.group(1)
                current = {
                    "article": num,
                    "title": titles.get(num, ""),
                    "part": part,
                    "chapter": title_case(chapter),
                    "page": pno + 1 - PAGE_OFFSET,
                    "lines": [body_text[m.end():].strip()],
                }
                continue
            if current is not None:
                current["lines"].append(text_of(body).strip())
    if current:
        out.append(current)
    return out


def build(pdf_bytes: bytes) -> dict[str, Any]:
    with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
        titles = toc_titles(pdf)
        arts = articles(pdf, titles)
    sections = []
    for a in arts:
        text = clean("\n".join(line for line in a.pop("lines") if line))
        text = re.sub(r"\n(?!\(\w{1,4}\)|Provided|Explanation)", " ", text)
        omitted = "Omitted" in a["title"] or bool(re.search(r"\bOmitted by\b", text[:200]))
        sections.append({
            "id": f"PK-CONST-{a['article']}",
            "label": f"Article {a['article']}",
            **a,
            "omitted": omitted,
            "text": text,
        })
    return {
        "law": "Constitution of Pakistan",
        "jurisdiction": "Pakistan",
        "source_name": SOURCE_NAME,
        "source_url": SOURCE_URL,
        "sections": sections,
    }


def main() -> int:
    pdf = Path(sys.argv[1]).read_bytes() if len(sys.argv) > 1 else download()
    data = build(pdf)
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"wrote {len(data['sections'])} articles to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
