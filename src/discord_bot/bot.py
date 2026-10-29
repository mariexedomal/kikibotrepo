"""Discord client for Kiki, with commands, conversational context, and mood."""

import asyncio
import logging
import os
import random
import sqlite3
import time
from collections import OrderedDict, deque
from dataclasses import dataclass

import discord
from discord import app_commands

from .behavior import (
    is_conversation_followup,
    is_explicitly_addressed,
    is_relevant_spontaneous_candidate,
    lowercase_prose,
    normalize_text,
    remove_bot_mention,
)
from .gemini_service import ChatTurn, GeminiResponder
from .mood import (
    classify_mood_signal,
    format_huh_report,
    mood_prompt_context,
)
from .settings import (
    CHANNEL_COOLDOWN_SECONDS,
    CONTEXT_MESSAGE_COUNT,
    CONVERSATION_CONTINUATION_SECONDS,
    CREATOR_USER_IDS,
    MAX_CHANNEL_HISTORIES,
    MAX_CONCURRENT_GEMINI_REQUESTS,
    MAX_CONVERSATION_FOLLOWUPS,
    MAX_INPUT_CHARACTERS,
    MAX_REPLY_CHARACTERS,
    MAX_SEEN_MESSAGES,
    MAX_TRACKED_BOT_REPLIES,
    REPLY_PROBABILITY,
    STATE_DB_PATH,
    USER_COOLDOWN_SECONDS,
)
from .state_store import MoodStore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
logger = logging.getLogger("discord_bot")


@dataclass(frozen=True)
class ActiveConversation:
    """Short-lived, per-user continuation window after Kiki replies."""

    expires_at: float
    followups_left: int


class KikiBot(discord.Client):
    """Discord client with bounded channel context and persistent server mood."""

    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.message_content = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        api_key = os.getenv("GEMINI_API_KEY")
        self.gemini = GeminiResponder(api_key) if api_key else None
        self.mood_store = MoodStore(STATE_DB_PATH)
        self._mood_store_ready = False
        self._histories: OrderedDict[int, deque[ChatTurn]] = OrderedDict()
        self._last_reply_at: dict[int, float] = {}
        self._last_user_reply_at: OrderedDict[tuple[int, int], float] = OrderedDict()
        self._active_conversations: OrderedDict[
            tuple[int, int], ActiveConversation
        ] = OrderedDict()
        self._seen_message_ids: OrderedDict[int, None] = OrderedDict()
        self._bot_reply_ids: OrderedDict[int, None] = OrderedDict()
        self._pending_channels: set[int] = set()
        self._gemini_slots = asyncio.Semaphore(MAX_CONCURRENT_GEMINI_REQUESTS)

    async def setup_hook(self) -> None:
        try:
            await self.mood_store.initialize()
            self._mood_store_ready = True
            logger.info("Persistent per-server mood storage is ready.")
        except (OSError, sqlite3.Error) as error:
            logger.error(
                "Mood storage is unavailable (%s); /huh will explain the issue.",
                type(error).__name__,
            )

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

    def _remember_id(
        self,
        collection: OrderedDict[int, None],
        message_id: int,
        limit: int,
    ) -> None:
        collection[message_id] = None
        collection.move_to_end(message_id)
        while len(collection) > limit:
            collection.popitem(last=False)

    def _get_history(self, channel_id: int) -> deque[ChatTurn]:
        history = self._histories.get(channel_id)
        if history is None:
            history = deque(maxlen=CONTEXT_MESSAGE_COUNT)
            self._histories[channel_id] = history

        self._histories.move_to_end(channel_id)
        while len(self._histories) > MAX_CHANNEL_HISTORIES:
            oldest_channel_id, _ = self._histories.popitem(last=False)
            self._last_reply_at.pop(oldest_channel_id, None)
            for key in tuple(self._active_conversations):
                if key[0] == oldest_channel_id:
                    self._active_conversations.pop(key, None)
        return history

    def _message_replies_to_kiki(self, message: discord.Message) -> bool:
        reference = message.reference
        if reference is None:
            return False

        referenced_id = getattr(reference, "message_id", None)
        if referenced_id is not None and referenced_id in self._bot_reply_ids:
            return True

        resolved = getattr(reference, "resolved", None)
        resolved_author = getattr(resolved, "author", None)
        return (
            self.user is not None
            and resolved_author is not None
            and getattr(resolved_author, "id", None) == self.user.id
        )

    def _active_followup(
        self,
        channel_id: int,
        user_id: int,
        text: str,
        explicitly_addressed: bool,
        replied_to_kiki: bool,
        now: float,
    ) -> bool:
        key = (channel_id, user_id)
        conversation = self._active_conversations.get(key)
        if conversation is None:
            return False
        if (
            conversation.expires_at < now
            or conversation.followups_left <= 0
        ):
            self._active_conversations.pop(key, None)
            return False
        if explicitly_addressed or replied_to_kiki or is_conversation_followup(text):
            self._active_conversations.move_to_end(key)
            return True
        return False

    def _is_creator(self, author: discord.abc.User) -> bool:
        if author.id in CREATOR_USER_IDS:
            return True
        names = {
            normalize_text(getattr(author, "display_name", "")),
            normalize_text(getattr(author, "name", "")),
        }
        return bool(names & {"helv", "mari"})

    def _author_label(self, author: discord.abc.User) -> str:
        if self._is_creator(author):
            return "helv/mari (a mesma criadora)"
        display_name = getattr(author, "display_name", None) or author.name
        return str(display_name)[:80]

    async def _record_mood_signal(
        self,
        guild_id: int,
        text: str,
        *,
        addressed_to_kiki: bool,
        is_creator: bool,
    ) -> None:
        if not self._mood_store_ready:
            return
        signal = classify_mood_signal(
            text,
            addressed_to_kiki=addressed_to_kiki,
            is_creator=is_creator,
        )
        if signal is None:
            return
        try:
            await self.mood_store.record_signal(guild_id, signal)
        except (OSError, sqlite3.Error) as error:
            logger.warning(
                "Could not update mood state (%s).", type(error).__name__
            )

    async def _mood_context(self, guild_id: int) -> str:
        if not self._mood_store_ready:
            return ""
        try:
            snapshot = await self.mood_store.snapshot(guild_id)
            return mood_prompt_context(snapshot)
        except (OSError, sqlite3.Error) as error:
            logger.warning(
                "Could not read mood state (%s).", type(error).__name__
            )
            return ""

    async def on_message(self, message: discord.Message) -> None:
        message_id = getattr(message, "id", None)
        if message_id is not None:
            if message_id in self._seen_message_ids:
                return
            self._remember_id(
                self._seen_message_ids, message_id, MAX_SEEN_MESSAGES
            )

        if (
            message.author.bot
            or message.webhook_id is not None
            or not isinstance(message.channel, (discord.TextChannel, discord.Thread))
            or message.guild is None
        ):
            return

        original_text = message.content.strip()
        if not original_text:
            return

        user_id = message.author.id
        channel_id = message.channel.id
        guild_id = message.guild.id
        mentioned_kiki = self.user is not None and self.user in message.mentions
        replied_to_kiki = self._message_replies_to_kiki(message)
        name_address = is_explicitly_addressed(original_text)
        explicitly_addressed = mentioned_kiki or name_address or replied_to_kiki

        text = (
            remove_bot_mention(original_text, self.user.id)
            if self.user is not None
            else original_text
        )
        if not text:
            text = "me chamou."

        now = time.monotonic()
        continuation = self._active_followup(
            channel_id,
            user_id,
            text,
            explicitly_addressed,
            replied_to_kiki,
            now,
        )

        history = self._get_history(channel_id)
        history.append(
            ChatTurn(
                role="user",
                author=self._author_label(message.author),
                text=text[:MAX_INPUT_CHARACTERS],
            )
        )
        await self._record_mood_signal(
            guild_id,
            text,
            addressed_to_kiki=explicitly_addressed or continuation,
            is_creator=self._is_creator(message.author),
        )

        if self.gemini is None or channel_id in self._pending_channels:
            return

        if not explicitly_addressed and not continuation:
            if not is_relevant_spontaneous_candidate(text):
                return
            if random.random() >= REPLY_PROBABILITY:
                return

        if not continuation:
            last_channel_reply = self._last_reply_at.get(channel_id)
            if (
                last_channel_reply is not None
                and now - last_channel_reply < CHANNEL_COOLDOWN_SECONDS
            ):
                return
            user_key = (guild_id, user_id)
            last_user_reply = self._last_user_reply_at.get(user_key)
            if (
                last_user_reply is not None
                and now - last_user_reply < USER_COOLDOWN_SECONDS
            ):
                return

        self._pending_channels.add(channel_id)
        try:
            mood_context = await self._mood_context(guild_id)
            async with self._gemini_slots:
                generated_text = await self.gemini.generate_reply(
                    list(history),
                    mood_context=mood_context,
                    allow_silence=not explicitly_addressed and not continuation,
                )

            if not generated_text:
                return

            reply = lowercase_prose(generated_text)[:MAX_REPLY_CHARACTERS]
            if not reply:
                return

            try:
                sent_message = await message.reply(
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

            history.append(ChatTurn(role="model", author="kiki", text=reply))
            sent_id = getattr(sent_message, "id", None)
            if sent_id is not None:
                self._remember_id(
                    self._bot_reply_ids, sent_id, MAX_TRACKED_BOT_REPLIES
                )

            completed_at = time.monotonic()
            self._last_reply_at[channel_id] = completed_at
            user_key = (guild_id, user_id)
            self._last_user_reply_at[user_key] = completed_at
            self._last_user_reply_at.move_to_end(user_key)
            while len(self._last_user_reply_at) > MAX_SEEN_MESSAGES:
                self._last_user_reply_at.popitem(last=False)

            conversation_key = (channel_id, user_id)
            if continuation:
                prior = self._active_conversations.get(conversation_key)
                followups_left = (
                    prior.followups_left - 1 if prior is not None else 0
                )
            else:
                followups_left = MAX_CONVERSATION_FOLLOWUPS
            if followups_left > 0:
                self._active_conversations[conversation_key] = ActiveConversation(
                    expires_at=completed_at + CONVERSATION_CONTINUATION_SECONDS,
                    followups_left=followups_left,
                )
                self._active_conversations.move_to_end(conversation_key)
                while len(self._active_conversations) > MAX_SEEN_MESSAGES:
                    self._active_conversations.popitem(last=False)
            else:
                self._active_conversations.pop(conversation_key, None)
        except Exception as error:
            logger.warning(
                "Kiki could not generate a reply (%s).", type(error).__name__
            )
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
        f"pong! latência do discord: {latency_ms} ms."
    )


@bot.tree.command(name="hello", description="Say hello to the bot.")
async def hello(interaction: discord.Interaction) -> None:
    """Greet the person who used the command."""
    await interaction.response.send_message(
        f"oi, {interaction.user.mention}! a kiki chegou."
    )


@bot.tree.command(name="huh", description="See Kiki's current simulated mood.")
@app_commands.guild_only()
async def huh(interaction: discord.Interaction) -> None:
    """Show the current server mood and recent recorded factors."""
    if interaction.guild_id is None:
        await interaction.response.send_message(
            "o /huh só funciona dentro de um servidor.", ephemeral=True
        )
        return
    if not bot._mood_store_ready:
        await interaction.response.send_message(
            "meu histórico de humor tá indisponível agora; tenta de novo depois.",
            ephemeral=True,
        )
        return
    try:
        snapshot = await bot.mood_store.snapshot(interaction.guild_id)
    except (OSError, sqlite3.Error) as error:
        logger.warning("Could not read /huh mood state (%s).", type(error).__name__)
        await interaction.response.send_message(
            "não consegui ler meu estado de humor agora; tenta de novo depois.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        format_huh_report(snapshot),
        ephemeral=True,
        allowed_mentions=discord.AllowedMentions.none(),
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
