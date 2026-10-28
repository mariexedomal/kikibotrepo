"""A small Discord bot with two application commands."""

import logging
import os

import discord
from discord import app_commands

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord_bot")


class StarterBot(discord.Client):
    """Discord client with an application-command tree."""

    def __init__(self) -> None:
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def setup_hook(self) -> None:
        synced_commands = await self.tree.sync()
        logger.info("Synced %s slash command(s).", len(synced_commands))

    async def on_ready(self) -> None:
        if self.user is not None:
            logger.info("Connected to Discord as %s (ID: %s).", self.user, self.user.id)


bot = StarterBot()


@bot.tree.command(name="ping", description="Check whether the bot is responding.")
async def ping(interaction: discord.Interaction) -> None:
    """Reply with the bot's current gateway latency."""
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"Pong! Gateway latency: {latency_ms} ms.")


@bot.tree.command(name="hello", description="Say hello to the bot.")
async def hello(interaction: discord.Interaction) -> None:
    """Greet the person who used the command."""
    await interaction.response.send_message(f"Hello, {interaction.user.mention}!")


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
