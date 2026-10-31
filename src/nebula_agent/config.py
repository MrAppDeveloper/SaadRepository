from __future__ import annotations

from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field

DEFAULT_CONFIG = Path("agents.yaml")
KNOWN_PROVIDERS = ("anthropic", "claude_cli", "nebula", "openai_compat")


class AgentConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    provider: str
    model: str
    tools: list[str] = Field(default_factory=list)
    max_steps: int = Field(default=12, ge=1)
    require_approval: list[str] = Field(default_factory=list)


class Config(BaseModel):
    model_config = ConfigDict(extra="forbid")

    agents: dict[str, AgentConfig]


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    """Load agents.yaml and the local .env (if present)."""
    load_dotenv()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text()) or {}
    config = Config.model_validate(data)
    for name, agent in config.agents.items():
        if agent.provider not in KNOWN_PROVIDERS:
            raise ValueError(
                f"Agent '{name}' uses unknown provider '{agent.provider}'. "
                f"Known: {', '.join(KNOWN_PROVIDERS)}"
            )
    return config
