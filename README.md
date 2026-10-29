# Kiki — Python Discord Bot

Kiki is a Python Discord bot that uses Google's official `google-genai` SDK and
Gemini Flash for occasional, natural conversation in server text channels.
The original `/ping` and `/hello` slash commands remain available.

## Discord setup

1. In the [Discord Developer Portal](https://discord.com/developers/applications),
   open the bot application.
2. Under **Bot → Privileged Gateway Intents**, enable **Message Content Intent**.
   The code enables only this additional privileged intent; it does not enable
   Presence or Server Members intents.
3. Under **OAuth2 → URL Generator**, select `bot` and
   `applications.commands`. Grant the bot permission to view channels and send
   messages, then use the generated URL to invite it to your server.
4. Make sure the bot can view and send messages in the channels where Kiki
   should participate.

## Secrets and workflow

Add these values under Replit Secrets. Never put them in source code or share
them in chat:

- `DISCORD_BOT_TOKEN` — the Discord bot token.
- `GEMINI_API_KEY` — a Google AI Studio Gemini API key.

Start or restart the existing **Discord Bot** workflow. It runs
`uv run discord-bot`. The bot keeps `/ping` and `/hello` available if the
Gemini key is missing, but ordinary chat replies are disabled until the key is
present.

## Test Kiki

1. Wait for the workflow log to say that slash commands have synced.
2. In your Discord server, run `/ping` and `/hello` to check the existing
   commands.
3. In a channel the bot can read, directly mention it and send a message, such
   as `@Kiki OI, TUDO BEM?`. A direct mention skips the random reply chance; the
   channel cooldown still applies.
4. If there is no reply, check Message Content Intent, channel permissions,
   both Replit Secrets, and the workflow logs. Gemini quota or service errors
   leave the bot online but can make it skip a reply.

## Kiki's behavior

- She speaks Brazilian Portuguese and every message she sends is converted to
  uppercase.
- She may reply to an ordinary text message without being mentioned. By default,
  each message has an 18% chance to trigger a reply, with a 15-second cooldown
  per channel. A direct `@Kiki` mention skips the random chance but still obeys
  the cooldown.
- The last 10 messages per channel are kept in memory for context. This is
  temporary context only: it is not saved to a database and disappears when the
  bot restarts.
- Her editable personality instructions are in
  `src/discord_bot/personality.py`.

Behavior can be adjusted with Replit environment variables:

| Variable | Default | Purpose |
| --- | ---: | --- |
| `KIKI_REPLY_PROBABILITY` | `0.18` | Chance from `0` to `1` of replying without a mention |
| `KIKI_CHANNEL_COOLDOWN_SECONDS` | `15` | Minimum seconds between replies in one channel |
| `KIKI_CONTEXT_MESSAGES` | `10` | Recent messages retained per channel, from `2` to `30` |
| `KIKI_MAX_INPUT_CHARACTERS` | `1200` | Maximum characters kept from one message |
| `KIKI_MAX_REPLY_CHARACTERS` | `700` | Maximum characters in a Kiki reply |

## Dependencies, cost, and privacy

- The project uses `discord.py` and Google's official `google-genai` Python
  package. Both are installed from the project dependency lock file.
- The selected model is `gemini-3.8-flash`. Google's pricing page currently
  lists it as free of charge on the Gemini API free tier
  ([pricing](https://ai.google.dev/gemini-api/docs/pricing)). Free-tier quotas
  and terms can change; this code does not enable billing or switch to a paid
  model. Keep the Google project on its free tier if you want to avoid charges.
- When Kiki considers a reply, the recent channel context is sent to Google's
  Gemini API. Do not use the bot in channels where messages contain information
  that should not be sent to Google. Google's current pricing page says
  free-tier content may be used to improve its products; review the current
  terms before enabling Kiki in a private server.
- API failures and rate limits are retried briefly and then skipped. The bot
  stays online, but Kiki may remain silent until the service is available again.
