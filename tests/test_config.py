from ncdev.config import NCDevConfig


def test_config_includes_integrations() -> None:
    cfg = NCDevConfig()
    data = cfg.to_yaml_dict()
    assert "integrations" in data
    assert "test_crafter" in data["integrations"]
