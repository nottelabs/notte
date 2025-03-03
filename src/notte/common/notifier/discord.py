import discord
from pydantic import BaseModel
from typing_extensions import override

from .base import BaseNotifier


class DiscordConfig(BaseModel):
    """Configuration for Discord sending functionality."""

    token: str
    channel_id: int


class DiscordNotifier(BaseNotifier):
    """Discord notification implementation."""

    config: DiscordConfig
    _client: discord.Client

    def __init__(self, config: DiscordConfig) -> None:
        super().__init__()
        self.config = config
        intents = discord.Intents.default()
        self._client = discord.Client(intents=intents)

    @override
    async def send_message(self, text: str) -> None:
        """Send a message to the configured Discord channel."""
        try:

            @self._client.event
            async def on_ready():  # type: ignore[no-called_function]
                try:
                    channel = self._client.get_channel(self.config.channel_id)
                    if channel is None:
                        raise ValueError(f"Could not find channel with ID: {self.config.channel_id}")
                    _ = await channel.send(text)  # type: ignore[type_unknown]
                finally:
                    await self._client.close()

            await self._client.start(self.config.token)
        except Exception as e:
            raise ValueError(f"Failed to send Discord message: {str(e)}")
