"""Keep the plan folders in Vercel Blob, so every instance of the deployed API sees them.

The API keeps each dossier as a folder on disk (`<data_dir>/<plan id>/...`). On Vercel the
disk belongs to one instance and is gone when it stops, and the next request may land on
another instance. `BlobMirror` wraps the app: before a request that names a plan, it pulls
the files of that plan that changed in Blob; once the response has been sent in full
(streamed answers included), it pushes the files the request wrote.

Off unless the deployment has a Blob store (`BLOB_READ_WRITE_TOKEN`, or the OIDC token of a
project with one connected), so local runs and the tests keep using the disk only.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

PLAN_PATH = re.compile(r"^(?:/api)?/plans/([0-9a-f]{32})(?:/|$)")
UPLOAD_PATH = re.compile(r"^(?:/api)?/plans/?$")
PREFIX = "plans/"


def enabled() -> bool:
    return bool(os.environ.get("BLOB_READ_WRITE_TOKEN") or os.environ.get("CONFORMSCOPE_BLOB"))


def _files(folder: Path) -> dict[str, tuple[int, int]]:
    if not folder.exists():
        return {}
    return {p.relative_to(folder).as_posix(): (p.stat().st_mtime_ns, p.stat().st_size)
            for p in folder.rglob("*") if p.is_file()}


class BlobMirror:
    def __init__(self, app, data_dir: str | Path) -> None:
        self.app = app
        self.data_dir = Path(data_dir)
        self.etags: dict[str, str] = {}  # what this instance holds, by Blob pathname

    async def pull(self, plan_id: str) -> None:
        from vercel import blob

        folder = self.data_dir / plan_id
        async for item in blob.query_blobs(prefix=f"{PREFIX}{plan_id}/"):
            if self.etags.get(item.pathname) == item.etag:
                continue
            got = await blob.get_blob(item.pathname, access="private")
            target = folder / item.pathname[len(f"{PREFIX}{plan_id}/"):]
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(bytes(got.body))
            self.etags[item.pathname] = item.etag

    async def push(self, plan_id: str, before: dict[str, tuple[int, int]]) -> None:
        from vercel import blob

        folder = self.data_dir / plan_id
        for rel, stamp in _files(folder).items():
            if before.get(rel) == stamp:
                continue
            pathname = f"{PREFIX}{plan_id}/{rel}"
            put = await blob.put_blob(pathname, (folder / rel).read_bytes(), access="private",
                                      allow_overwrite=True)
            self.etags[pathname] = put.etag

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        path = scope["path"]
        match = PLAN_PATH.match(path)
        uploading = scope["method"] == "POST" and UPLOAD_PATH.match(path)
        if not match and not uploading:
            return await self.app(scope, receive, send)

        if match:
            plan_id = match.group(1)
            await self.pull(plan_id)
            before = {plan_id: _files(self.data_dir / plan_id)}
        else:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            known = {p.name for p in self.data_dir.iterdir()}
            before = {}

        async def finish():
            ids = list(before) if match else [
                p.name for p in self.data_dir.iterdir() if p.is_dir() and p.name not in known]
            for plan_id in ids:
                await self.push(plan_id, before.get(plan_id, {}))

        async def relay(message):
            # Push before the last body chunk leaves, so the next request finds the files.
            if message["type"] == "http.response.body" and not message.get("more_body"):
                await finish()
            await send(message)

        await self.app(scope, receive, relay)


def wrap(app, data_dir: str | Path):
    return BlobMirror(app, data_dir) if enabled() else app


__all__ = ["BlobMirror", "enabled", "wrap"]
