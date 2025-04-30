from notte_agent.common.notifier import BaseNotifier
from slack_sdk.web.client import WebClient
from typing_extensions import override


class SlackNotifier(BaseNotifier):
    """Slack notification implementation."""

    def __init__(self, token: str, channel_id: str) -> None:
        super().__init__()
        self.token: str = token
        self.channel_id: str = channel_id
        self._client: WebClient = WebClient(token=self.token)

    @override
    def send_message(self, text: str) -> None:
        """Send a message to the configured Slack channel."""
        _ = self._client.chat_postMessage(channel=self.channel_id, text=text)  # type: ignore[type_unknown]
