# Python Discord Bot

A Python Discord bot with `/ping` and `/hello` slash commands plus occasional
Brazilian Portuguese conversation powered by Gemini.

## Run & Operate

- `pnpm --filter @workspace/api-server run dev` — run the API server (port 5000)
- `uv run discord-bot` — run the Discord bot
- `pnpm run typecheck` — full typecheck across all packages
- `pnpm run build` — typecheck + build all packages
- `pnpm --filter @workspace/api-spec run codegen` — regenerate API hooks and Zod schemas from the OpenAPI spec
- `pnpm --filter @workspace/db run push` — push DB schema changes (dev only)
- Required secrets: `DISCORD_BOT_TOKEN`, `GEMINI_API_KEY`
- Discord Developer Portal: enable Message Content Intent for regular chat replies
- `README.md` — bot setup, permissions, configuration, cost, and privacy notes

## Stack

- Python 3.13, `discord.py`, Google's `google-genai`, and uv for the Discord bot
- pnpm workspaces, Node.js 24, TypeScript 5.9
- API: Express 5
- DB: PostgreSQL + Drizzle ORM
- Validation: Zod (`zod/v4`), `drizzle-zod`
- API codegen: Orval (from OpenAPI spec)
- Build: esbuild (CJS bundle)

## Where things live

- `src/discord_bot/bot.py` — Discord client, slash commands, and message handling
- `src/discord_bot/personality.py` — Kiki's editable persona instructions
- `src/discord_bot/gemini_service.py` — asynchronous Gemini requests and retries
- `src/discord_bot/settings.py` — configurable reply and context limits
- `pyproject.toml` / `uv.lock` — Python project metadata and locked dependencies
- `artifacts/api-server` — shared API service
- `artifacts/mockup-sandbox` — design canvas preview service

## Architecture decisions

_Populate as you build — non-obvious choices a reader couldn't infer from the code (3-5 bullets)._

## Product

_Describe the high-level user-facing capabilities of this app once they exist._

## User preferences

_Populate as you build — explicit user instructions worth remembering across sessions._

## Gotchas

_Populate as you build — sharp edges, "always run X before Y" rules._

## Pointers

- See the `pnpm-workspace` skill for workspace structure, TypeScript setup, and package details
