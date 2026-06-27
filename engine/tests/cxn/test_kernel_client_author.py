import httpx
import pytest

from memento.cxn.kernel_client import LOOK_CONSTRUCTION, HttpComprehensionClient


@pytest.mark.asyncio
async def test_author_grammar_posts_look_construction():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["perm"] = request.headers.get("X-Permission")
        seen["token"] = request.headers.get("X-Internal-Token")
        import json

        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    c = HttpComprehensionClient(
        base_url="http://k", token="tok", bonfire_id="bf-1", client=client
    )
    ok = await c.author_grammar([LOOK_CONSTRUCTION])
    assert ok is True
    assert seen["url"] == "http://k/v1/bonfires/bf-1/kernel/author-grammar"
    assert seen["perm"] == "write" and seen["token"] == "tok"
    assert seen["body"]["constructions"][0]["construct_id"] == "mm.look.v1"
    assert seen["body"]["constructions"][0]["form"] == [{"role": "verb"}]


@pytest.mark.asyncio
async def test_author_grammar_raises_on_non_200():
    from memento.cxn.types import ComprehendError

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"error": "nope"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    c = HttpComprehensionClient(
        base_url="http://k", token="tok", bonfire_id="bf-1", client=client
    )
    with pytest.raises(ComprehendError):
        await c.author_grammar([LOOK_CONSTRUCTION])
