from typing import Any

import discord
from notte_agent.common.notifier import BaseNotifier
from pydantic import BaseModel
from typing_extensions import override


class DiscordConfig(BaseModel):
    """Configuration for Discord sending functionality."""

    token: str
    channel_id: int


class DiscordNotifier(BaseNotifier):
    """Discord notification implementation."""

    def __init__(self, config: DiscordConfig) -> None:
        super().__init__()
        self.config: DiscordConfig = config
        self._client: discord.Client = discord.Client(intents=discord.Intents.default())

    @override
    async def send_message(self, text: str) -> None:
        """Send a message to the configured Discord channel."""
        try:

            @self._client.event
            async def on_ready():  # pyright: ignore[reportUnusedFunction]
                try:
                    channel = self._client.get_channel(self.config.channel_id)
                    if channel is None:
                        raise ValueError(f"Could not find channel with ID: {self.config.channel_id}")
                    _: Any = await channel.send(text)  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
                finally:
                    await self._client.close()

            await self._client.start(self.config.token)
        except Exception as e:
            raise ValueError(f"Failed to send Discord message: {str(e)}")
