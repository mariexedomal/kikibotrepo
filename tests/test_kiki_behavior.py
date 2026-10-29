import asyncio
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import discord

import discord_bot.bot as bot_module
from discord_bot.behavior import (
    is_conversation_followup,
    is_explicitly_addressed,
    is_relevant_spontaneous_candidate,
    lowercase_prose,
)
from discord_bot.bot import KikiBot, bot
from discord_bot.gemini_service import ChatTurn, GeminiResponder
from discord_bot.mood import (
    MoodSignal,
    MoodSnapshot,
    MoodState,
    apply_signal,
    classify_mood_signal,
    format_huh_report,
)
from discord_bot.state_store import MoodStore


class AddressRecognitionTests(unittest.TestCase):
    def test_detects_expected_direct_addresses(self) -> None:
        examples = (
            "ei kiki, eai?",
            "kiki, olha isso aqui",
            "mano kiki isso não faz sentido",
            "alguém explica isso pra kiki?",
            "kiki, tu gosta disso?",
            "e a kiki, o que acha?",
            "oi, kiki",
            "kiki????",
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertTrue(is_explicitly_addressed(text))

    def test_ignores_third_person_mentions(self) -> None:
        examples = (
            "a kiki falou disso ontem.",
            "estou contando uma história sobre a kiki.",
            "conheci alguém que se chama kiki.",
        )
        for text in examples:
            with self.subTest(text=text):
                self.assertFalse(is_explicitly_addressed(text))

    def test_followups_and_spontaneous_relevance(self) -> None:
        self.assertTrue(is_conversation_followup("tudo bem?"))
        self.assertTrue(is_conversation_followup("também, tô entediado"))
        self.assertFalse(is_conversation_followup("mudando de assunto: olha meu pc"))
        self.assertFalse(is_relevant_spontaneous_candidate("bom dia"))
        self.assertTrue(is_relevant_spontaneous_candidate("alguém viu esse jogo?"))

    def test_lowercases_prose_but_keeps_technical_spans(self) -> None:
        original = (
            "OI, veja API_KEY e myVariable em https://EXAMPLE.com/Path "
            "e `<@123>`:\n```Python\nPRINT('HI')\n```"
        )
        self.assertEqual(
            lowercase_prose(original),
            "oi, veja API_KEY e myVariable em https://EXAMPLE.com/Path "
            "e `<@123>`:\n```Python\nPRINT('HI')\n```",
        )


class MoodTests(unittest.TestCase):
    def test_signals_are_contextual_and_bounded(self) -> None:
        kindness = classify_mood_signal(
            "obrigada, kiki", addressed_to_kiki=True
        )
        hostility = classify_mood_signal(
            "kiki, você é uma idiota", addressed_to_kiki=True
        )
        profanity_alone = classify_mood_signal(
            "vsfd kiki", addressed_to_kiki=True
        )

        self.assertIsNotNone(kindness)
        self.assertIsNotNone(hostility)
        self.assertIsNone(profanity_alone)

        assert hostility is not None
        state = MoodState()
        for _ in range(100):
            state = apply_signal(state, hostility)
        self.assertTrue(all(0.0 <= value <= 1.0 for value in state.as_dict().values()))

    def test_huh_admits_insufficient_history(self) -> None:
        snapshot = MoodSnapshot(
            state=MoodState(),
            recent_reasons=(),
            interaction_count=0,
            updated_at=None,
        )
        self.assertIn("não tenho interações recentes", format_huh_report(snapshot))


class MoodStoreTests(unittest.IsolatedAsyncioTestCase):
    async def test_mood_survives_store_recreation_without_storing_messages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "mood.sqlite3"
            first_store = MoodStore(str(path))
            await first_store.initialize()
            signal = MoodSignal(
                category="humor",
                reason="a conversa teve um sinal de humor",
                changes={"amusement": 0.05},
            )
            first_snapshot = await first_store.record_signal(123, signal)

            restarted_store = MoodStore(str(path))
            await restarted_store.initialize()
            restored_snapshot = await restarted_store.snapshot(123)

            self.assertGreater(restored_snapshot.interaction_count, 0)
            self.assertAlmostEqual(
                restored_snapshot.state.amusement,
                first_snapshot.state.amusement,
                places=6,
            )
            connection = sqlite3.connect(path)
            try:
                stored_tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                self.assertEqual(
                    stored_tables, {"kiki_mood", "kiki_mood_events"}
                )
                saved_values = connection.execute(
                    "SELECT state_json, reason FROM kiki_mood "
                    "JOIN kiki_mood_events USING (guild_id)"
                ).fetchone()
                self.assertNotIn("raw user message", str(saved_values))
            finally:
                connection.close()


class GeminiServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_silence_marker_and_mood_context_are_handled(self) -> None:
        responder = GeminiResponder("mock-key-never-sent")
        responder._client.aio.models.generate_content = AsyncMock(
            return_value=SimpleNamespace(text=" [[SILENT]] ")
        )
        responder._client.aio.aclose = AsyncMock()

        result = await responder.generate_reply(
            [ChatTurn(role="user", author="ana", text="como foi?")],
            mood_context="curiosidade=60/100",
            allow_silence=True,
        )

        self.assertIsNone(result)
        config = responder._client.aio.models.generate_content.await_args.kwargs[
            "config"
        ]
        self.assertIn("curiosidade=60/100", config.system_instruction)
        self.assertIn("[[SILENT]]", config.system_instruction)
        await responder.close()

    async def test_provider_error_is_returned_as_no_reply(self) -> None:
        responder = GeminiResponder("mock-key-never-sent")
        error = ValueError("do not log request details")
        error.status_code = 401
        responder._client.aio.models.generate_content = AsyncMock(
            side_effect=error
        )
        responder._client.aio.aclose = AsyncMock()

        with self.assertLogs("discord_bot.gemini", level="WARNING") as logs:
            result = await responder.generate_reply(
                [ChatTurn(role="user", author="ana", text="oi")]
            )

        self.assertIsNone(result)
        self.assertIn("HTTP 401", logs.output[0])
        self.assertNotIn("do not log request details", logs.output[0])
        await responder.close()

    async def test_missing_gemini_secret_keeps_client_commands_available(self) -> None:
        with (
            patch.dict("os.environ", {"GEMINI_API_KEY": ""}),
            patch("discord_bot.bot.STATE_DB_PATH", ":memory:"),
        ):
            client = KikiBot()
        try:
            self.assertIsNone(client.gemini)
        finally:
            await client.close()


class BotMessageTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.service = MagicMock()
        self.service.generate_reply = AsyncMock(
            side_effect=["OI, TUDO BEM?", "TÔ DE BOA!"]
        )
        self.service.close = AsyncMock()
        with patch("discord_bot.bot.GeminiResponder", return_value=self.service):
            self.client = KikiBot()
        self.client.gemini = self.service
        self.client.mood_store = MoodStore(
            str(Path(self.temp_dir.name) / "mood.sqlite3")
        )
        await self.client.mood_store.initialize()
        self.client._mood_store_ready = True

        self.bot_user = MagicMock(spec=discord.ClientUser)
        self.bot_user.id = 999
        self.client._connection.user = self.bot_user

        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 500
        self.channel = MagicMock(spec=discord.TextChannel)
        self.channel.id = 123
        self.author = self._author(101, "ana")

    async def asyncTearDown(self) -> None:
        await self.client.close()
        self.temp_dir.cleanup()

    @staticmethod
    def _author(user_id: int, name: str) -> MagicMock:
        author = MagicMock(spec=discord.Member)
        author.id = user_id
        author.bot = False
        author.name = name
        author.display_name = name
        return author

    def _message(
        self,
        message_id: int,
        content: str,
        *,
        author: MagicMock | None = None,
        mentions: list[MagicMock] | None = None,
    ) -> MagicMock:
        message = MagicMock(spec=discord.Message)
        message.id = message_id
        message.author = author or self.author
        message.channel = self.channel
        message.guild = self.guild
        message.webhook_id = None
        message.content = content
        message.mentions = mentions or []
        message.reference = None
        message.reply = AsyncMock(return_value=MagicMock(id=message_id + 10_000))
        return message

    async def test_name_address_continues_and_deduplicates(self) -> None:
        first = self._message(1, "ei kiki, eai?")
        await self.client.on_message(first)
        first.reply.assert_awaited_once()
        self.assertEqual(first.reply.await_args.args[0], "oi, tudo bem?")

        followup = self._message(2, "tudo bem?")
        await self.client.on_message(followup)
        followup.reply.assert_awaited_once()
        self.assertEqual(followup.reply.await_args.args[0], "tô de boa!")

        await self.client.on_message(followup)
        self.assertEqual(self.service.generate_reply.await_count, 2)

    async def test_ping_and_commands_remain_available(self) -> None:
        names = {command.name for command in bot.tree.get_commands()}
        self.assertEqual(names, {"ping", "hello", "huh"})
        self.assertTrue(self.client.intents.message_content)
        self.assertFalse(self.client.intents.members)
        self.assertFalse(self.client.intents.presences)

    async def test_huh_command_uses_stored_mood(self) -> None:
        class FakeMoodStore:
            async def snapshot(self, guild_id: int) -> MoodSnapshot:
                return MoodSnapshot(
                    state=MoodState(happiness=0.8, curiosity=0.7),
                    recent_reasons=("a conversa teve um sinal de humor",),
                    interaction_count=1,
                    updated_at=1.0,
                )

        interaction = MagicMock()
        interaction.guild_id = 500
        interaction.response.send_message = AsyncMock()
        prior_store = bot.mood_store
        prior_ready = bot._mood_store_ready
        bot.mood_store = FakeMoodStore()
        bot._mood_store_ready = True
        try:
            command = bot.tree.get_command("huh")
            assert command is not None
            await command.callback(interaction)
        finally:
            bot.mood_store = prior_store
            bot._mood_store_ready = prior_ready

        response = interaction.response.send_message.await_args
        self.assertIn("humor simulado", response.args[0])
        self.assertIn("sinal de humor", response.args[0])
        self.assertTrue(response.kwargs["ephemeral"])

    async def test_channel_cooldown_limits_new_conversations(self) -> None:
        first = self._message(
            10, "<@999> oi", mentions=[self.bot_user]
        )
        await self.client.on_message(first)

        different_user = self._author(202, "bia")
        second = self._message(
            11,
            "<@999> oi",
            author=different_user,
            mentions=[self.bot_user],
        )
        await self.client.on_message(second)

        first.reply.assert_awaited_once()
        second.reply.assert_not_awaited()
        self.assertEqual(self.service.generate_reply.await_count, 1)

    async def test_bot_authored_messages_are_ignored(self) -> None:
        bot_author = self._author(303, "another-bot")
        bot_author.bot = True
        message = self._message(17, "ei kiki, responde", author=bot_author)

        await self.client.on_message(message)

        message.reply.assert_not_awaited()
        self.assertEqual(self.service.generate_reply.await_count, 0)

    async def test_user_cooldown_applies_across_channels(self) -> None:
        first = self._message(15, "ei kiki, olha isso")
        await self.client.on_message(first)

        other_channel = MagicMock(spec=discord.TextChannel)
        other_channel.id = 456
        second = self._message(16, "ei kiki, outra coisa")
        second.channel = other_channel
        await self.client.on_message(second)

        first.reply.assert_awaited_once()
        second.reply.assert_not_awaited()
        self.assertEqual(self.service.generate_reply.await_count, 1)

    async def test_third_person_mention_does_not_trigger_reply(self) -> None:
        message = self._message(
            20,
            "ontem eu contei uma história sobre a kiki, mas ninguém falava com ela.",
        )
        with patch.object(bot_module, "REPLY_PROBABILITY", 0.0):
            await self.client.on_message(message)
        message.reply.assert_not_awaited()
        self.assertEqual(self.service.generate_reply.await_count, 0)


if __name__ == "__main__":
    unittest.main()
