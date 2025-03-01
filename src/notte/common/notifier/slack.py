from pydantic import BaseModel
from slack_sdk.errors import SlackApiError
from slack_sdk.web import SlackResponse
from slack_sdk.web.client import WebClient
from typing_extensions import override

from notte.common.agent.types import AgentResponse

from .base import BaseNotifier


class SlackConfig(BaseModel):
    """Configuration for Slack sending functionality."""

    token: str
    channel_id: str


class SlackService:
    """Service for sending messages to Slack from Notte."""

    def __init__(self, config: SlackConfig):
        self.config: SlackConfig = config
        self._client: WebClient = WebClient(token=self.config.token)

    async def send_message(self, text: str) -> None:
        """Send a message to the configured Slack channel.

        Args:
            text: The message text to send
        """
        try:
            _: SlackResponse = self._client.chat_postMessage(channel=self.config.channel_id, text=text)  #  type: ignore[unknown import]
        except SlackApiError as e:
            raise ValueError(f"Failed to send Slack message: {str(e)}")


class SlackNotifier(BaseNotifier):
    """Slack notification implementation."""

    def __init__(self, config: SlackConfig) -> None:
        super().__init__()  # Call parent class constructor
        self.slack_service: SlackService = SlackService(config)

    @override
    async def notify(self, task: str, result: AgentResponse) -> None:
        """Send a Slack notification about the task result.

        Args:
            task: The task description
            result: The agent's response to be sent
        """
        message = f"""
:robot_face: *Notte Agent Report*

*Task Details*
-------------
*Task:* {task}
*Execution Time:* {round(result.duration_in_s, 2)} seconds
*Status:* {"✅ Success" if result.success else "❌ Failed"}

*Agent Response*
--------------
{result.answer}

_Powered by Notte_ :crescent_moon:"""
        await self.slack_service.send_message(message)
