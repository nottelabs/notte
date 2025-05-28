import asyncio
from typing import Any, Literal

import discord
from notte_core.common.notifier import BaseNotifier
from pydantic import Field
from typing_extensions import override


class DiscordNotifier(BaseNotifier):
    """Discord notification implementation."""

    type: Literal["discord"] = "discord"  # pyright: ignore [reportIncompatibleVariableOverride]
    token: str
    channel_id: int
    client: discord.Client = Field(
        default_factory=lambda: discord.Client(intents=discord.Intents.default()), exclude=True
    )

    @override
    def send_message(self, text: str) -> None:
        """Send a message to the configured Discord channel."""
        try:

            @self.client.event
            async def on_ready():  # pyright: ignore[reportUnusedFunction]
                try:
                    channel = self.client.get_channel(self.channel_id)
                    if channel is None:
                        raise ValueError(f"Could not find channel with ID: {self.channel_id}")
                    _: Any = await channel.send(text)  # pyright: ignore[reportUnknownMemberType,reportAttributeAccessIssue]
                finally:
                    await self.client.close()

            _ = asyncio.run(self.client.start(self.token))
        except Exception as e:
            raise ValueError(f"Failed to send Discord message: {str(e)}")
