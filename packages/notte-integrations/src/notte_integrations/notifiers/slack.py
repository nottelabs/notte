from typing import Any, Literal

from notte_core.common.notifier import BaseNotifier
from pydantic import model_validator
from pydantic.fields import Field
from slack_sdk.web.client import WebClient
from typing_extensions import override


class SlackNotifier(BaseNotifier):
    """Slack notification implementation."""

    type: Literal["slack"] = "slack"  # pyright: ignore [reportIncompatibleVariableOverride]
    token: str
    channel_id: str
    client: WebClient = Field(exclude=True)

    @model_validator(mode="before")
    def setup_client(cls, data: dict[str, Any]) -> dict[str, Any]:
        """Set up the Slack client using the token."""
        if "token" in data and data["token"]:
            data["client"] = WebClient(token=data["token"])
        else:
            raise ValueError("Invalid token")
        return data

    @override
    def send_message(self, text: str) -> None:
        """Send a message to the configured Slack channel."""
        _ = self.client.chat_postMessage(channel=self.channel_id, text=text)  # pyright: ignore [reportUnknownMemberType]
