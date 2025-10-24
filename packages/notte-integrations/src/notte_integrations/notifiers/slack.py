from functools import cached_property
from typing import Literal

from notte_core.common.notifier import BaseNotifier
from slack_sdk.web.client import WebClient
from slack_sdk.webhook import WebhookClient
from typing_extensions import override


class SlackNotifier(BaseNotifier):
    """Slack notification implementation."""

    type: Literal["slack"] = "slack"  # pyright: ignore [reportIncompatibleVariableOverride]
    token: str
    channel_id: str

    @cached_property
    def client(self) -> WebClient:
        if not self.token:
            raise ValueError("Token is required")
        return WebClient(token=self.token)

    @override
    def send_message(self, text: str) -> None:
        """Send a message to the configured Slack channel."""
        _ = self.client.chat_postMessage(channel=self.channel_id, text=text)  # pyright: ignore [reportUnknownMemberType]


class SlackWebhookNotifier(BaseNotifier):
    """Slack notification implementation."""

    type: Literal["slack-webhook"] = "slack-webhook"  # pyright: ignore [reportIncompatibleVariableOverride]
    url: str

    @cached_property
    def client(self) -> WebhookClient:
        if not self.url:
            raise ValueError("URL is required")
        return WebhookClient(url=self.url)

    @override
    def send_message(self, text: str) -> None:
        """Send a message to the configured Slack channel."""
        _ = self.client.send(text=text)
