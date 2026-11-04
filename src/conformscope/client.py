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


VERIFIER_BASE_URL = "https://inference.baseten.co/v1"
VERIFIER_MODEL = "meta-models/muse-spark-open"  # Muse Spark Open (the -1026 hackathon build now 404s)


def make_verifier_client() -> OpenAI:
    """Muse Spark Open on Baseten, the verifier's client (issue #16)."""
    load_dotenv()
    key = os.environ.get("BASETEN_API_KEY")
    if not key:
        raise MissingKeyError("BASETEN_API_KEY is not set. Copy .env.example to .env and fill it in.")
    return OpenAI(base_url=VERIFIER_BASE_URL, api_key=key)
