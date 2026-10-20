# LexMind

LexMind is an AI legal assistant for Pakistan. Ask a question in plain English and it answers from the
**Constitution of the Islamic Republic of Pakistan** (as amended up to 21 November 2025), with the exact article
for every claim. A **Citation Checker** removes any sentence that cites an article that doesn't exist, wasn't in the
sources, or misquotes the text.

> LexMind gives legal information, not legal advice. It is not a licensed advocate.

## Features

- **Law Brain** (`POST /api/ask`): searches all 327 articles, then the AI writes an answer from the matching
  articles only, citing them as `[Art. 10A]`.
- **Citation Checker** (`lexmind/citations.py`): checks each citation. The article must exist, it must be one of the
  sources the AI was given, and any quoted words must appear in it word for word. Sentences that fail are removed and
  shown separately.
- **Constitution browser**: every part, chapter and article, with search.
- **Works without an AI key**: without `OPENAI_API_KEY` it returns the best-matching articles instead of a written
  answer.

## How it works

```
question → BM25 search over the Constitution → LLM answers from those articles only → Citation Checker → answer + sources
```

- `lexmind/data/constitution_pk.json` is built from the official National Assembly PDF by
  `scripts/build_library.py`. That script drops the small side notes and footnote markers,
  detects the bold article numbers and takes article titles from the table of contents.
- Search is BM25 keyword ranking in plain Python with a small synonym list (e.g. "police" → arrest, custody), so it
  needs no database. Naming an article ("Article 199") pins it to the top.

## Run locally

```bash
pip install -e ".[dev]"
lexmind serve            # http://127.0.0.1:8000
lexmind search "right to education"
```

Turn on AI answers with `export OPENAI_API_KEY=sk-...` (optional: `OPENAI_MODEL`, default `gpt-4o-mini`).

Checks: `ruff check . && mypy && pytest -q --cov` (coverage must stay at least 85%).

Rebuild the law data after a new amendment (update `SOURCE_URL` in the script first):

```bash
pip install -e ".[data]"
python scripts/build_library.py
```

## Environment variables

| Name | Default | Purpose |
| --- | --- | --- |
| `OPENAI_API_KEY` | unset | Turns on AI answers |
| `OPENAI_MODEL` | `gpt-4o-mini` | Model used for answers |
| `LEXMIND_ASK_PER_MINUTE` | `10` | Questions per minute per visitor (`0` = no limit). Counted per server instance |

## Deploy on Vercel

1. Go to https://vercel.com/new and pick **Import** next to `adotak/LexMind`.
2. **Framework Preset**: FastAPI (Vercel uses the root `app.py`). Leave the build and output settings as they are.
3. Open **Environment Variables** and add `OPENAI_API_KEY` (from https://platform.openai.com/api-keys). You can
   skip this to deploy in search-only mode.
4. Click **Deploy**. When it's done, open `https://<your-project>.vercel.app/api/health`. It should show
   `"status": "ok"`, and `"ai": true` if you added the key.

## Roadmap

1. Law Brain + Citation Checker (this release)
2. Counter-Argument Engine: AI "you" vs AI "opponent", scored by an AI "judge"
3. Contract Scanner: flags risky clauses using the Contract Act, 1872
4. More laws (Pakistan Penal Code, KP rent and consumer laws), Supabase + pgvector search, Clerk accounts

## Data source

[Constitution of the Islamic Republic of Pakistan, as amended up to 21 November 2025](https://na.gov.pk/uploads/documents/6926e060076ed_467.pdf),
National Assembly of Pakistan.
