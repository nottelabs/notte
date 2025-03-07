import discord  # type: ignore
from pydantic import BaseModel
from typing_extensions import override

from .base import BaseNotifier


class DiscordConfig(BaseModel):
    """Configuration for Discord sending functionality."""

    token: str
    channel_id: int


class DiscordNotifier(BaseNotifier):
    """Discord notification implementation."""

    def __init__(self, config: DiscordConfig) -> None:
        super().__init__()
        self.config: DiscordConfig = config
        self._client: discord.client.Client = discord.Client(intents=discord.Intents.default())  # type: ignore[type_unknown]

    @override
    async def send_message(self, text: str) -> None:
        """Send a message to the configured Discord channel."""
        try:

            @self._client.event  # type: ignore[type_unknown]
            async def on_ready():  # type: ignore[no-called_function]
                try:
                    channel: discord.TextChannel = self._client.get_channel(self.config.channel_id)  # type: ignore[type_unknown]
                    if channel is None:
                        raise ValueError(f"Could not find channel with ID: {self.config.channel_id}")
                    _ = await channel.send(text)  # type: ignore[type_unknown]
                finally:
                    await self._client.close()  # type: ignore[type_unknown]

            await self._client.start(self.config.token)  # type: ignore[type_unknown]
        except Exception as e:
            raise ValueError(f"Failed to send Discord message: {str(e)}")
