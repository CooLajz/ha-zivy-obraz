"""Lazy, conditional preview downloads shared by requests for one panel."""

from __future__ import annotations

import asyncio
from time import monotonic

from aiohttp import ClientError, ClientSession

MIN_REQUEST_INTERVAL = 60
IMAGE_TYPES = {"image/png", "image/bmp", "image/x-ms-bmp", "image/webp"}


class PreviewCache:
    """Keep image bytes in memory until the device contact or URL changes."""

    def __init__(self) -> None:
        self.url: str | None = None
        self.contact: str | None = None
        self.content: bytes | None = None
        self.content_type = "image/png"
        self._etag: str | None = None
        self._modified: str | None = None
        self._revision = 0
        self._completed_revision = -1
        self._next_request = 0.0
        self._lock = asyncio.Lock()

    def update(self, url: str | None, contact: str | None) -> bool:
        """Invalidate the revision without discarding reusable image data."""
        if (url, contact) == (self.url, self.contact):
            return False
        if url != self.url:
            self.content = None
            self._etag = self._modified = None
        self.url, self.contact = url, contact
        self._revision += 1
        return True

    @property
    def pending(self) -> bool:
        """Return whether a new revision still needs a request."""
        return bool(self.url) and self._completed_revision != self._revision

    @property
    def delay(self) -> float:
        """Return the remaining request cooldown."""
        return max(0.0, self._next_request - monotonic())

    async def async_image(
        self, session: ClientSession, timeout: int, headers: dict[str, str]
    ) -> bytes | None:
        """Fetch at most once per revision, coalescing concurrent callers."""
        async with self._lock:
            if not self.url:
                return None
            if not self.pending or self.delay:
                return self.content

            revision = self._revision
            request_headers = dict(headers)
            if self.content is not None:
                if self._etag:
                    request_headers["If-None-Match"] = self._etag
                elif self._modified:
                    request_headers["If-Modified-Since"] = self._modified
            self._next_request = monotonic() + MIN_REQUEST_INTERVAL
            try:
                async with asyncio.timeout(timeout):
                    async with session.get(
                        self.url, headers=request_headers
                    ) as response:
                        # A URL/contact change during this request supersedes it.
                        if revision != self._revision:
                            return None
                        if response.status == 304 and self.content is not None:
                            self._etag = response.headers.get("ETag", self._etag)
                            self._modified = response.headers.get(
                                "Last-Modified", self._modified
                            )
                            self._completed_revision = revision
                            return self.content
                        response.raise_for_status()
                        content_type = response.headers.get(
                            "Content-Type", ""
                        ).split(";", 1)[0].strip().lower()
                        if content_type not in IMAGE_TYPES:
                            raise ValueError("Unsupported preview content type")
                        content = await response.read()
                        if revision != self._revision:
                            return None
                        if not content:
                            raise ValueError("Empty preview")
                        self.content = content
                        self.content_type = content_type
                        self._etag = response.headers.get("ETag")
                        self._modified = response.headers.get("Last-Modified")
                        self._completed_revision = revision
            except (ClientError, TimeoutError, ValueError):
                if revision == self._revision:
                    # Do not retry a broken/revoked preview on every page load.
                    # The next contact or URL change permits another attempt.
                    self.content = None
                    self._etag = self._modified = None
                    self._completed_revision = revision
                return None
            return self.content
