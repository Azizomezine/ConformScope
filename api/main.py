"""The API as a Vercel Function: the app under /api, its plan folders kept in Vercel Blob.

vercel.json sends /api/* here; the web service answers everything else.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from fastapi import FastAPI  # noqa: E402

from conformscope.api import create_app  # noqa: E402
from conformscope.mirror import wrap  # noqa: E402

DATA = "/tmp/conformscope/plans"  # the only writable disk on Vercel

app = FastAPI(title="ConformScope")
app.mount("/api", create_app(DATA))
app = wrap(app, DATA)