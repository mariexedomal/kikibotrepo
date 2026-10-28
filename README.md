# Python Discord Bot

A small Python starter bot with two Discord slash commands:

- `/ping` reports the bot's Discord gateway latency.
- `/hello` greets the person who ran the command.

It uses the free, open-source `discord.py` library and Discord's bot API. No
paid package, API subscription, or privileged Message Content intent is needed.

## Create and invite the bot

1. Create an application in the [Discord Developer Portal](https://discord.com/developers/applications).
2. Open its **Bot** page and create a bot user. Copy its token; treat it like a password.
3. In **OAuth2 → URL Generator**, select the `bot` and `applications.commands` scopes.
4. Select the `View Channels` and `Send Messages` bot permissions, then use the
   generated URL to add the bot to a server where you have permission.
5. In Replit, add a secret named `DISCORD_BOT_TOKEN` and paste the bot token into
   the secret value. Never put the real token in source code or commit it.
6. Start the **Discord Bot** workflow.

The bot does not need the privileged Message Content intent because it uses
slash commands rather than reading regular chat messages.

## Run locally

Install the project dependencies with `uv sync`, set `DISCORD_BOT_TOKEN` in
your shell environment, then run:

```sh
uv run discord-bot
```

## Notes

- Global slash commands can take a little while to appear after the first sync.
- The bot process must be running to respond to commands.
- The code and dependencies are free. Keeping a bot online continuously depends
  on the hosting environment's availability and plan.
