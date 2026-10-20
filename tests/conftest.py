from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from langchain_core.language_models.fake_chat_models import FakeListChatModel

from lexmind.api import create_app
from lexmind.library import Library, default_library

MINI = {
    "law": "Test Law",
    "jurisdiction": "Testland",
    "source_name": "Test source",
    "source_url": "https://example.com/law.pdf",
    "sections": [
        {"id": "T-1", "label": "Article 1", "article": "1", "title": "Right to water", "part": "PART I", "chapter": "",
         "page": 1, "text": "Every person shall have access to clean drinking water."},
        {"id": "T-2", "label": "Article 2", "article": "2", "title": "Arrest", "part": "PART I", "chapter": "Rights",
         "page": 2, "text": "No person who is arrested shall be detained beyond twenty-four hours."},
        {"id": "T-2A", "label": "Article 2A", "article": "2A", "title": "Old rule", "part": "PART I", "chapter": "",
         "page": 2, "text": "Omitted by the Test Act.", "omitted": True},
    ],
}


@pytest.fixture
def mini() -> Library:
    return Library(MINI)


@pytest.fixture
def library() -> Library:
    return default_library()


def fake_llm(*responses: str) -> Any:
    return FakeListChatModel(responses=list(responses))


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app(ask_per_minute=0))
