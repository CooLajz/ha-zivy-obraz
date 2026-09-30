"""Exercise preview bandwidth guarantees without a Home Assistant install."""

import asyncio
import importlib.util
from pathlib import Path

from aiohttp import web
import pytest
import pytest_asyncio

spec = importlib.util.spec_from_file_location(
    "preview", Path(__file__).parents[1] / "custom_components/zivy_obraz/preview.py"
)
preview = importlib.util.module_from_spec(spec)
spec.loader.exec_module(preview)


@pytest_asyncio.fixture
async def server():
    requests = []
    state = {
        "status": 200,
        "body": b"test image bytes",
        "headers": {"ETag": '"v1"', "Content-Type": "image/png"},
    }

    async def handler(request):
        requests.append(dict(request.headers))
        if gate := state.get("gate"):
            state["started"].set()
            await gate.wait()
        return web.Response(
            status=state["status"], body=state["body"], headers=state["headers"]
        )

    app = web.Application()
    app.router.add_get("/preview", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", 0)
    await site.start()
    port = site._server.sockets[0].getsockname()[1]
    async with preview.ClientSession() as session:
        yield f"http://127.0.0.1:{port}/preview", session, requests, state
    await runner.cleanup()


@pytest.mark.asyncio
async def test_lazy_cache_and_concurrent_requests(server):
    url, session, requests, _ = server
    cache = preview.PreviewCache()
    cache.update(url, "first contact")
    assert not requests
    result = await asyncio.gather(
        *(cache.async_image(session, 5, {}) for _ in range(10))
    )
    assert result == [b"test image bytes"] * 10
    assert len(requests) == 1
    assert not cache.update(url, "first contact")
    cache._next_request = 0
    assert await cache.async_image(session, 5, {}) == b"test image bytes"
    assert len(requests) == 1  # Cache does not expire with time.


@pytest.mark.asyncio
async def test_changed_contact_uses_etag_and_304(server):
    url, session, requests, state = server
    cache = preview.PreviewCache()
    cache.update(url, "first")
    await cache.async_image(session, 5, {})
    cache.update(url, "second")
    # Even changed contacts may not bypass the server's minimum interval.
    await cache.async_image(session, 5, {})
    assert len(requests) == 1
    assert cache.pending and cache.delay > 0
    cache._next_request = 0
    state.update(status=304, body=b"")
    assert await cache.async_image(session, 5, {}) == b"test image bytes"
    assert requests[-1]["If-None-Match"] == '"v1"'
    assert not cache.pending
    cache.update(url, "third")
    cache._next_request = 0
    state.update(status=200, body=b"new image")
    state["headers"]["ETag"] = '"v2"'
    assert await cache.async_image(session, 5, {}) == b"new image"


@pytest.mark.asyncio
async def test_last_modified_fallback(server):
    url, session, requests, state = server
    modified = "Wed, 30 Sep 2026 12:00:00 GMT"
    state["headers"] = {"Content-Type": "image/bmp", "Last-Modified": modified}
    cache = preview.PreviewCache()
    cache.update(url, "first")
    await cache.async_image(session, 5, {})
    assert cache.content_type == "image/bmp"
    cache.update(url, "second")
    cache._next_request = 0
    await cache.async_image(session, 5, {})
    assert requests[-1]["If-Modified-Since"] == modified
    assert "If-None-Match" not in requests[-1]


@pytest.mark.asyncio
async def test_url_rotation_and_disable_clear_private_image(server):
    url, session, requests, _ = server
    cache = preview.PreviewCache()
    cache.update(url, "first")
    await cache.async_image(session, 5, {})
    cache.update(url + "?new-key", "first")
    assert cache.content is None
    cache._next_request = 0
    await cache.async_image(session, 5, {})
    assert "If-None-Match" not in requests[-1]
    cache.update(None, "first")
    assert await cache.async_image(session, 5, {}) is None
    assert cache.content is None and not cache.pending
    assert len(requests) == 2


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", [404, 500, "empty", "html"])
async def test_failures_do_not_trigger_page_load_retries(server, failure):
    url, session, requests, state = server
    cache = preview.PreviewCache()
    cache.update(url, "first")
    await cache.async_image(session, 5, {})
    cache.update(url, "second")
    cache._next_request = 0
    if isinstance(failure, int):
        state["status"] = failure
    elif failure == "empty":
        state["body"] = b""
    else:
        state["headers"]["Content-Type"] = "text/html"
    assert await cache.async_image(session, 5, {}) is None
    cache._next_request = 0
    assert await cache.async_image(session, 5, {}) is None
    assert len(requests) == 2
    assert not cache.pending


@pytest.mark.asyncio
async def test_inflight_response_does_not_restore_disabled_image(server):
    url, session, _, state = server
    state.update(gate=asyncio.Event(), started=asyncio.Event())
    cache = preview.PreviewCache()
    cache.update(url, "first")
    task = asyncio.create_task(cache.async_image(session, 5, {}))
    await state["started"].wait()
    cache.update(None, "first")
    state["gate"].set()
    assert await task is None
    assert cache.content is None
