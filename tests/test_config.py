from pathlib import Path

import pytest

from nebula_agent.config import load_config


def write(tmp_path: Path, text: str) -> Path:
    p = tmp_path / "agents.yaml"
    p.write_text(text)
    return p


def test_loads_valid_config(tmp_path):
    cfg = load_config(write(tmp_path, "agents:\n  qa:\n    provider: anthropic\n    model: m\n"))
    assert cfg.agents["qa"].max_steps == 12


def test_unknown_provider_rejected(tmp_path):
    with pytest.raises(ValueError, match="unknown provider"):
        load_config(write(tmp_path, "agents:\n  qa:\n    provider: bogus\n    model: m\n"))


def test_missing_file(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_config(tmp_path / "nope.yaml")


def test_repo_agents_yaml_is_valid():
    assert {"qa", "cleaner"} <= set(load_config(Path("agents.yaml")).agents)
