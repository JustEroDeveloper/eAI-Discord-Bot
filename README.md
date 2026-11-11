# Discord AI Bot — Ollama + SearXNG

A Discord bot that answers questions using web search (SearXNG) and a local LLM (Ollama).

## Commands

- `/ask <question>` — search the web, answer with your local LLM
- `/setchannels` *(admin)* — set this server's announcements and changelog channels (stored in `channels.json`)
- `/showchannels` — show the configured channels
- `/announce` *(admin)* — post a custom announcement
- `/changelog` *(admin)* — post the latest GitHub release changelog
- `/pinlatest` *(admin)* — pin the newest message in the announcements channel
- **Text trigger (optional):** any message containing `/ask` (disable via `TEXT_TRIGGER_ENABLED=false`)
- **Text trigger:** any message containing `/ask` (disable via `TEXT_TRIGGER_ENABLED=false`)

## Setup

1. **Install dependencies** (Python 3.11+ recommended):
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure** — copy `.env.example` to `.env` and fill in:
   - `DISCORD_TOKEN` — from the Discord Developer Portal → Bot → Reset Token
   - `OLLAMA_MODEL` — e.g. `llama3`, `mistral`, `qwen2.5` (run `ollama list` to see yours)

3. **Discord Developer Portal:**
   - Enable **Message Content Intent** under Bot → Privileged Gateway Intents
     (required for the text trigger; slash commands work without it).
   - Invite the bot with the `bot` + `applications.commands` scopes and
     Send Messages / Read Message History permissions.

4. **SearXNG:** the JSON API must be enabled. If search fails with 403, edit
   SearXNG's `settings.yml`:
   ```yaml
   search:
     formats: [html, json]
   ```
   and restart SearXNG.

5. **Run:**
   ```bash
   python bot.py
   ```

## Config (`.env`)

| Variable | Default | Description |
|---|---|---|
| `DISCORD_TOKEN` | — | Bot token (required) |
| `OLLAMA_URL` | `http://localhost:11434` | Ollama API |
| `OLLAMA_MODEL` | `llama3` | Model name from `ollama list` |
| `SEARXNG_URL` | `http://localhost:8080` | SearXNG instance |
| `MAX_SEARCH_RESULTS` | `5` | Results fed to the model |
| `TEXT_TRIGGER_ENABLED` | `true` | Also reply to plain messages containing `/ask` |
| `TEMPERATURE` | `0.4` | LLM temperature |

## ⚠️ Security

Never share your bot token. If it leaks (e.g. posted in chat), go to the
Developer Portal and **Reset Token** immediately.

## Terminal UI

```bash
.venv/bin/python tui.py
```

Keys: `s` start · `k` stop · `r` restart · `l` view logs · `h` service health · `q` quit

## Security & Disclaimer

See [DISCLAIMER.md](./DISCLAIMER.md) — no warranty; the author is not responsible for any misuse.
