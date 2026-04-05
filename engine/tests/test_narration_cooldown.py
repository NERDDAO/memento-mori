import time
from pathlib import Path
from memento.narration_cooldown import NarrationCooldown


def test_should_narrate_first_time(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json")
    assert nc.should_narrate("tavern") is True


def test_record_blocks_immediate_renarration(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json", cooldown=10.0)
    nc.record("tavern")
    assert nc.should_narrate("tavern") is False


def test_cooldown_expires(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json", cooldown=0.1)
    nc.record("tavern")
    time.sleep(0.15)
    assert nc.should_narrate("tavern") is True


def test_persists_across_instances(tmp_path):
    path = tmp_path / "cooldowns.json"
    nc1 = NarrationCooldown(path=path, cooldown=10.0)
    nc1.record("tavern")

    nc2 = NarrationCooldown(path=path, cooldown=10.0)
    assert nc2.should_narrate("tavern") is False


def test_independent_locations(tmp_path):
    nc = NarrationCooldown(path=tmp_path / "cooldowns.json", cooldown=10.0)
    nc.record("tavern")
    assert nc.should_narrate("tavern") is False
    assert nc.should_narrate("market") is True
