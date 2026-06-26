from gateway.world_identity import resolve_bonfire_id


def test_resolve_prefers_env(monkeypatch):
    monkeypatch.setenv("BONFIRE_ID", "6650000000000000000000f1")
    assert resolve_bonfire_id() == "6650000000000000000000f1"


def test_resolve_falls_back_to_slug(monkeypatch):
    monkeypatch.delenv("BONFIRE_ID", raising=False)
    assert resolve_bonfire_id() == "mm-world-v1"


def test_resolve_falls_back_when_env_blank(monkeypatch):
    monkeypatch.setenv("BONFIRE_ID", "")
    assert resolve_bonfire_id() == "mm-world-v1"
