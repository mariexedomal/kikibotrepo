"""Discord client for Kiki, with slash commands and occasional Gemini replies."""

import asyncio
import logging
import os
import random
import time
from collections import OrderedDict, deque

import discord
from discord import app_commands

from .gemini_service import ChatTurn, GeminiResponder
from .settings import (
    CHANNEL_COOLDOWN_SECONDS,
    CONTEXT_MESSAGE_COUNT,
    MAX_CHANNEL_HISTORIES,
    MAX_CONCURRENT_GEMINI_REQUESTS,
    MAX_INPUT_CHARACTERS,
    MAX_REPLY_CHARACTERS,
    REPLY_PROBABILITY,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord_bot")


class KikiBot(discord.Client):
    """Discord client with short-lived channel context and Kiki's commands."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        api_key = os.getenv("GEMINI_API_KEY")
        self.gemini = GeminiResponder(api_key) if api_key else None
        self._histories: OrderedDict[int, deque[ChatTurn]] = OrderedDict()
        self._last_reply_at: dict[int, float] = {}
        self._pending_channels: set[int] = set()
        self._gemini_slots = asyncio.Semaphore(MAX_CONCURRENT_GEMINI_REQUESTS)

    async def setup_hook(self) -> None:
        synced_commands = await self.tree.sync()
        logger.info("Synced %s slash command(s).", len(synced_commands))
        if self.gemini is None:
            logger.warning(
                "GEMINI_API_KEY is missing; conversational replies are disabled."
            )
        else:
            logger.info("Kiki's Gemini chat is ready.")

    async def on_ready(self) -> None:
        if self.user is not None:
            logger.info("Connected to Discord as %s (ID: %s).", self.user, self.user.id)

    def _get_history(self, channel_id: int) -> deque[ChatTurn]:
        history = self._histories.get(channel_id)
        if history is None:
            history = deque(maxlen=CONTEXT_MESSAGE_COUNT)
            self._histories[channel_id] = history

        self._histories.move_to_end(channel_id)
        while len(self._histories) > MAX_CHANNEL_HISTORIES:
            oldest_channel_id, _ = self._histories.popitem(last=False)
            self._last_reply_at.pop(oldest_channel_id, None)
        return history

    async def on_message(self, message: discord.Message) -> None:
        if (
            message.author.bot
            or message.webhook_id is not None
            or not isinstance(message.channel, (discord.TextChannel, discord.Thread))
        ):
            return

        if self.gemini is None:
            return

        text = message.content.strip()
        if not text:
            return

        mentioned_kiki = self.user is not None and self.user in message.mentions
        if self.user is not None:
            text = text.replace(f"<@{self.user.id}>", "")
            text = text.replace(f"<@!{self.user.id}>", "")
            text = text.strip()
        if not text:
            text = "A PESSOA TE CHAMOU."

        channel_id = message.channel.id
        history = self._get_history(channel_id)
        history.append(
            ChatTurn(
                role="user",
                author=message.author.display_name,
                text=text[:MAX_INPUT_CHARACTERS],
            )
        )

        if channel_id in self._pending_channels:
            return

        now = time.monotonic()
        last_reply_at = self._last_reply_at.get(channel_id)
        if (
            last_reply_at is not None
            and now - last_reply_at < CHANNEL_COOLDOWN_SECONDS
        ):
            return
        if not mentioned_kiki and random.random() >= REPLY_PROBABILITY:
            return

        # Claim the cooldown before awaiting Gemini so overlapping messages cannot
        # start duplicate replies in this channel.
        self._last_reply_at[channel_id] = now
        self._pending_channels.add(channel_id)
        try:
            async with self._gemini_slots:
                generated_text = await self.gemini.generate_reply(list(history))

            if not generated_text:
                return

            reply = generated_text.upper().strip()[:MAX_REPLY_CHARACTERS]
            if not reply:
                return

            try:
                await message.reply(
                    reply,
                    mention_author=False,
                    allowed_mentions=discord.AllowedMentions.none(),
                )
            except discord.HTTPException as error:
                logger.warning(
                    "Discord could not send Kiki's reply (HTTP %s).",
                    error.status,
                )
                return

            history.append(ChatTurn(role="model", author="KIKI", text=reply))
        finally:
            self._pending_channels.discard(channel_id)

    async def close(self) -> None:
        try:
            if self.gemini is not None:
                await self.gemini.close()
        finally:
            await super().close()


bot = KikiBot()


@bot.tree.command(name="ping", description="Check whether the bot is responding.")
async def ping(interaction: discord.Interaction) -> None:
    """Reply with the bot's current gateway latency."""
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"PONG! LATÊNCIA DO DISCORD: {latency_ms} MS."
    )


@bot.tree.command(name="hello", description="Say hello to the bot.")
async def hello(interaction: discord.Interaction) -> None:
    """Greet the person who used the command."""
    await interaction.response.send_message(
        f"OII, {interaction.user.mention}! A KIKI CHEGOU."
    )


def main() -> None:
    """Start the bot using a token provided through the environment."""
    token = os.getenv("DISCORD_BOT_TOKEN")
    if not token:
        raise SystemExit(
            "DISCORD_BOT_TOKEN is missing. Add your bot token as a Replit Secret "
            "with that exact name, then start the Discord Bot workflow."
        )

    bot.run(token)


if __name__ == "__main__":
    main()
