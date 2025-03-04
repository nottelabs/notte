from pydantic import BaseModel
from slack_sdk.web.client import WebClient  # type: ignore[type_unknown]
from typing_extensions import override

from .base import BaseNotifier


class SlackConfig(BaseModel):
    """Configuration for Slack sending functionality."""

    token: str
    channel_id: str


class SlackNotifier(BaseNotifier):
    """Slack notification implementation."""

    def __init__(self, config: SlackConfig) -> None:
        super().__init__()
        self.config: SlackConfig = config
        self._client: WebClient = WebClient(token=self.config.token)

    @override
    async def send_message(self, text: str) -> None:
        """Send a message to the configured Slack channel."""
        _ = self._client.chat_postMessage(channel=self.config.channel_id, text=text)  # type: ignore[type_unknown]
