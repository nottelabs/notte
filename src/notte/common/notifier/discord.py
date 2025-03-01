import discord
from pydantic import BaseModel
from typing_extensions import override

from notte.common.agent.types import AgentResponse

from .base import BaseNotifier


class DiscordConfig(BaseModel):
    """Configuration for Discord sending functionality."""

    token: str
    channel_id: int


class DiscordService:
    """Service for sending messages to Discord from Notte."""

    def __init__(self, config: DiscordConfig):
        self.config: DiscordConfig = config
        intents = discord.Intents.default()
        self._client = discord.Client(intents=intents)  # type: ignore[unknown-type]

    async def send_message(self, text: str) -> None:
        """Send a message to the configured Discord channel.

        Args:
            text: The message text to send
        """
        try:
            # Set up the event handler
            @self._client.event
            async def on_ready():  # type: ignore[unused-function]
                try:
                    channel = self._client.get_channel(self.config.channel_id)
                    if channel is None:
                        raise ValueError(f"Could not find channel with ID: {self.config.channel_id}")
                    _ = await channel.send(text)  # type: ignore[unknown-type]
                finally:
                    await self._client.close()

            # Run the client and wait for it to complete
            await self._client.start(self.config.token)

        except Exception as e:
            raise ValueError(f"Failed to send Discord message: {str(e)}")


class DiscordNotifier(BaseNotifier):
    """Discord notification implementation."""

    def __init__(self, config: DiscordConfig) -> None:
        super().__init__()  # Call parent class constructor
        self.discord_service: DiscordService = DiscordService(config)

    @override
    async def notify(self, task: str, result: AgentResponse) -> None:
        """Send a Discord notification about the task result.

        Args:
            task: The task description
            result: The agent's response to be sent
        """
        message = f"**Task**: {task}\n**Response**: {result.answer}"
        await self.discord_service.send_message(message)
