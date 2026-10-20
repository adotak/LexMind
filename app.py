"""Vercel entrypoint (FastAPI zero-config): Vercel routes every request to ``app``."""

from lexmind.api import create_app

app = create_app()
