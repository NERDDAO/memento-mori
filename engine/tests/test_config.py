from memento.config import load_config, get_model_for_crew


def test_load_config():
    config = load_config()
    assert config["game"]["name"] == "Memento Mori"
    assert config["game"]["permadeath"] is True
    assert config["llm"]["default_model"].startswith("openrouter/")
    assert "narration" in config["llm"]["overrides"]


def test_config_has_round_window():
    config = load_config()
    assert config["game"]["round_window_seconds"] == 20


def test_get_model_for_crew_default():
    model = get_model_for_crew("context")
    assert model == "openrouter/anthropic/claude-sonnet-4"


def test_get_model_for_crew_override():
    model = get_model_for_crew("classification")
    assert model == "openrouter/anthropic/claude-haiku-4"


def test_get_model_for_crew_narration():
    model = get_model_for_crew("narration")
    assert model == "openrouter/anthropic/claude-sonnet-4"
