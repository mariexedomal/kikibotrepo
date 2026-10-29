# Kiki — Python Discord Bot

Kiki is the existing Python Discord bot, using `discord.py` and Google's
official `google-genai` SDK. It keeps `/ping` and `/hello`, adds `/huh`, and can
join server conversations through Gemini.

## Discord setup

1. Open the app in Replit and start or restart the **Discord Bot** workflow.
2. In Discord's [Developer Portal](https://discord.com/developers/applications),
   open the bot application, then go to **Bot → Privileged Gateway Intents**.
3. Enable **Message Content Intent**. The code enables only that additional
   privileged intent; Presence and Server Members intents remain off.
4. Confirm the bot has permission to view and send messages in the channels
   where it should participate.

Keep the existing Replit Secrets: `DISCORD_BOT_TOKEN` and `GEMINI_API_KEY`.
Never put either value in source code or chat.

## Try Kiki from Discord on iPhone

1. In Replit's Safari workspace, open **Workflows**, select **Discord Bot**, and
   tap **Restart**. Wait for the log that says slash commands synced and Kiki's
   Gemini chat is ready.
2. In the Discord app, open a server channel where Kiki can read and send
   messages. Run `/ping` and `/hello` to check the existing commands.
3. Start a conversation with `ei kiki, eai?` or directly mention `@Kiki`.
   She should normally respond even without a Discord ping.
4. Continue with `tudo bem?` or `também, tô entediado` within about 90 seconds.
   Kiki can continue the same exchange without another mention.
5. Run `/huh` in the server to see the stored mood summary and recent generic
   reasons. The command reply is visible only to you.
6. Try `alguém falou que a Kiki fez isso` to check that a third-person mention
   does not automatically make her answer. Direct mentions and replies to
   Kiki's messages are stronger signals.

Kiki may stay silent when a spontaneous message is not relevant, when cooldowns
apply, or when Gemini returns its explicit silence marker. A direct address
bypasses the random chance, but not the per-channel and per-user cooldowns
unless it is a detected continuation of an active exchange.

## Behavior and privacy

- Ordinary prose is lowercased. Code spans, URLs, Discord mention tokens, and
  identifiers such as `API_KEY` or `myVariable` retain their case.
- Kiki recognizes likely direct name-addresses, replies to her messages, and
  short follow-ups from the same person. Unaddressed replies require a relevance
  check and a configurable random chance.
- The default spontaneous reply chance is 18%; the channel cooldown is 15
  seconds and the per-user cooldown is 30 seconds. Active conversations last
  up to 90 seconds and allow up to four follow-ups by default.
- Short-term message context is kept in memory (up to 10 messages per channel)
  and disappears when the process restarts. Only the messages needed for a
  generated reply are sent to Gemini.
- The simulated mood is separate from message context. A small set of bounded
  mood scores and generic reason labels are stored per server in
  `data/kiki-state.sqlite3`; raw messages and user IDs are not stored in that
  database. `/huh` reports the stored scores and recorded reasons, or says when
  there is not enough recent signal.
- The mood uses local text cues, not a second AI request. It can miss sarcasm,
  subtle emotion, or a joke's target. It is fictional state, not consciousness
  or persistent factual memory.
- Helv and Mari are treated as the same creator. Exact display names `helv` and
  `mari` work as a fallback; optionally set `KIKI_CREATOR_USER_IDS` to a
  comma-separated list of the creator's Discord user IDs for more reliable
  identification.
- Kiki's Nikko rivalry is occasional and playful. Her interest in adult women
  is only used when relevant and consensual; it must not be used to sexualize
  minors or harass members.

### Behavior settings

Set optional environment variables in Replit's **Secrets** or environment
settings. Defaults are suitable for a small server.

| Variable | Default | Purpose |
| --- | ---: | --- |
| `KIKI_REPLY_PROBABILITY` | `0.18` | Chance of considering a relevant, unaddressed message |
| `KIKI_CHANNEL_COOLDOWN_SECONDS` | `15` | Minimum time between new replies in a channel |
| `KIKI_USER_COOLDOWN_SECONDS` | `30` | Minimum time between new replies to one user |
| `KIKI_CONVERSATION_CONTINUATION_SECONDS` | `90` | Follow-up window for an active exchange |
| `KIKI_MAX_CONVERSATION_FOLLOWUPS` | `4` | Maximum unmentioned follow-up replies per exchange |
| `KIKI_CONTEXT_MESSAGES` | `10` | Recent messages retained in memory per channel |
| `KIKI_MAX_INPUT_CHARACTERS` | `1200` | Maximum characters kept from one message |
| `KIKI_MAX_REPLY_CHARACTERS` | `700` | Maximum characters in a Kiki reply |
| `KIKI_STATE_DB_PATH` | `data/kiki-state.sqlite3` | Local SQLite file for simulated mood |
| `KIKI_CREATOR_USER_IDS` | unset | Optional comma-separated creator Discord IDs |

The database file is ignored by Git and excluded from published bundles. It
survives restarting this Replit workflow because the workspace file remains in
place. Replit's published-app filesystem is reset when the app is published or
republished, so this SQLite state does **not** survive a deployment refresh. A
deployed bot that needs durable mood state should use a persistent SQL database.

## Dependencies, cost, and external data

- Python dependencies are managed with `uv` and locked in `uv.lock`. SQLite is
  from Python's standard library; this feature adds no paid service or
  subscription.
- The selected model is `gemini-3.8-flash`. Google's
  [pricing page](https://ai.google.dev/gemini-api/docs/pricing) currently lists
  it as free on the Gemini API free tier. Quotas and terms can change; keep the
  Google project on its free tier to avoid paid usage.
- When Kiki generates a reply, recent channel messages are sent to Google's
  Gemini API. Do not use her in channels containing information that should not
  be sent to Google. Google's current pricing page says free-tier content may
  be used to improve its products; review current terms before enabling Kiki in
  a private server.
- API errors, rate limits, and Discord send errors are handled without logging
  message contents or credentials. If Gemini cannot reply, Kiki stays online
  and skips that message.
