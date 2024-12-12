import json
import os
from dataclasses import dataclass
from pathlib import Path

from notte.pipe.listing import ActionListingPipes

ROOT_DIR = Path(__file__).parent.parent
CONFIG_PATH = ROOT_DIR / "notte_config.json"


@dataclass
class NotteConfig:
    """Configuration for Notte environment"""

    base_model: str = "groq/llama-3.3-70b-versatile"
    action_listing_pipe: ActionListingPipes = ActionListingPipes.SIMPLE_MARKDOWN_TABLE

    def __post_init__(self):
        if isinstance(self.action_listing_pipe, str):
            self.action_listing_pipe = ActionListingPipes(self.action_listing_pipe)

        # TODO: discuss whether we should use env variables or not
        env_base_model = os.getenv("NOTTE_BASE_MODEL")
        if env_base_model is not None:
            self.base_model = env_base_model

        env_action_listing_pipe = os.getenv("NOTTE_ACTION_LISTING_PIPE")
        if env_action_listing_pipe is not None:
            self.action_listing_pipe = ActionListingPipes(env_action_listing_pipe)

    @classmethod
    def load(cls, path: str | Path | None = None) -> "NotteConfig":
        """Load config from JSON file"""
        config_path = Path(path) if path else CONFIG_PATH

        try:
            with open(config_path, "r") as f:
                data = json.load(f)
                return cls(**data)
        except FileNotFoundError:
            return cls()  # Return default config if file not found
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in config file: {e}")
        except Exception as e:
            raise ValueError(f"Error loading config: {e}")
