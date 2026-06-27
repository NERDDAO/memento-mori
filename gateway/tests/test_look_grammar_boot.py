import pytest

from memento.cxn.kernel_client import LOOK_CONSTRUCTION


@pytest.mark.asyncio
async def test_seed_look_grammar_authors_look_construction(monkeypatch):
    calls = []

    class _StubClient:
        def __init__(self, *a, **k):
            self.bonfire_id = k.get("bonfire_id")

        async def author_grammar(self, constructions):
            calls.append(constructions)
            return True

    import memento.cxn.kernel_client as kc

    monkeypatch.setattr(kc, "HttpComprehensionClient", _StubClient)

    from gateway.look_tool import seed_look_grammar

    ok = await seed_look_grammar("bf-1")
    assert ok is True
    assert calls == [[LOOK_CONSTRUCTION]]
    assert calls[0][0]["construct_id"] == "mm.look.v1"
