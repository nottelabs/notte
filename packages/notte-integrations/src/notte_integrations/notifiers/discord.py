import asyncio
from typing import Any

import discord
from notte_agent.common.notifier import BaseNotifier
from typing_extensions import override


class DiscordNotifier(BaseNotifier):
    """Discord notification implementation."""

    def __init__(self, token: str, channel_id: int) -> None:
        super().__init__()
        self.token: str = token
        self.channel_id: int = channel_id
        self._client: discord.Client = discord.Client(intents=discord.Intents.default())

    @override
    def send_message(self, text: str) -> None:
        """Send a message to the configured Discord channel."""
        try:

            @self._client.event
            async def on_ready():  # pyright: ignore[reportUnusedFunction]
                try:
                    channel = self._client.get_channel(self.channel_id)
                    if channel is None:
                        raise ValueError(f"Could not find channel with ID: {self.channel_id}")
                    _: Any = await channel.send(text)  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
                finally:
                    await self._client.close()

            _ = asyncio.run(self._client.start(self.token))
        except Exception as e:
            raise ValueError(f"Failed to send Discord message: {str(e)}")
