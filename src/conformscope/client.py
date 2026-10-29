"""The Meta Model API client, configured from MODEL_API_KEY."""

from __future__ import annotations

import os

from dotenv import load_dotenv
from openai import OpenAI

BASE_URL = "https://api.meta.ai/v1"


class MissingKeyError(RuntimeError):
    pass


def make_client() -> OpenAI:
    load_dotenv()
    key = os.environ.get("MODEL_API_KEY")
    if not key:
        raise MissingKeyError("MODEL_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return OpenAI(base_url=BASE_URL, api_key=key)
