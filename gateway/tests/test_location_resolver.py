import pytest

from gateway.location_resolver import LocationResolver


class _Repo:
    async def get_entity(self, uuid):
        return {"uuid": uuid, "name": "Gatehouse"} if uuid == "loc-1" else None


def _patch_kg(monkeypatch, value):
    async def _fake(_pid):
        return value

    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _fake)


@pytest.mark.asyncio
async def test_uuid_for_hits_cache_without_kg(monkeypatch):
    calls = {"n": 0}

    async def _kg(_pid):
        calls["n"] += 1
        return None

    monkeypatch.setattr("gateway.routes.codex._get_location_uuid", _kg)
    cache = {"Gatehouse": "loc-1"}
    r = LocationResolver(_Repo(), cache)
    assert await r.uuid_for("p1", "Gatehouse") == "loc-1"
    assert calls["n"] == 0  # cache hit -> KG never consulted


@pytest.mark.asyncio
async def test_uuid_for_falls_back_to_kg_and_records(monkeypatch):
    _patch_kg(monkeypatch, "loc-9")
    cache: dict[str, str] = {}
    r = LocationResolver(_Repo(), cache)
    assert await r.uuid_for("p1", "North Gate") == "loc-9"
    assert cache["North Gate"] == "loc-9"  # recorded for later maybe_close


@pytest.mark.asyncio
async def test_uuid_for_returns_none_when_unresolved(monkeypatch):
    _patch_kg(monkeypatch, None)
    r = LocationResolver(_Repo(), {})
    assert await r.uuid_for("p1", "Nowhere") is None


@pytest.mark.asyncio
async def test_name_for_reads_repo():
    r = LocationResolver(_Repo(), {})
    assert await r.name_for("loc-1") == "Gatehouse"
    assert await r.name_for("missing") is None


def test_record_lookup_forget():
    cache: dict[str, str] = {}
    r = LocationResolver(_Repo(), cache)
    r.record("Gatehouse", "loc-1")
    assert r.uuid_for_name("Gatehouse") == "loc-1"
    r.forget_name("Gatehouse")
    assert r.uuid_for_name("Gatehouse") is None
