"""Discord bot: /ask command answering questions with Ollama + SearXNG."""

import aiohttp

# discord.py doesn't expose a proxy option in this version; patch its internal
# aiohttp sessions to honor HTTPS_PROXY from the environment.
_orig_session_init = aiohttp.ClientSession.__init__


def _trust_env_session_init(self, *args, **kwargs):
    kwargs.setdefault("trust_env", True)
    _orig_session_init(self, *args, **kwargs)


aiohttp.ClientSession.__init__ = _trust_env_session_init

import asyncio
import json
import discord
from discord import app_commands
from discord.ext import tasks
from pathlib import Path

import config
from ollama_client import OllamaError, chat_stream
from search import SearchError, search

MAX_MESSAGE_LEN = 2000
LAST_RELEASE_FILE = Path(__file__).with_name("last_release.txt")
CHANNELS_FILE = Path(__file__).with_name("channels.json")


def _load_channels() -> dict:
    """guild_id (str) -> {"announcements": int, "changelog": int}"""
    try:
        return json.loads(CHANNELS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_channels(data: dict):
    CHANNELS_FILE.write_text(json.dumps(data, indent=2))


def resolve_channels(guild_id: int | None) -> tuple[int, int]:
    """Return (announcements_cid, changelog_cid) for a guild, falling back
    to the global .env defaults when nothing is set for that guild."""
    if guild_id is not None:
        stored = _load_channels().get(str(guild_id), {})
        announce = int(stored.get("announcements") or 0)
        changelog = int(stored.get("changelog") or 0)
        return announce, changelog
    return config.ANNOUNCEMENTS_CHANNEL_ID, config.CHANGELOG_CHANNEL_ID

intents = discord.Intents.default()
# Message content intent (and the /ask text trigger) only if enabled in .env
if config.TEXT_TRIGGER_ENABLED:
    intents.message_content = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)


def build_embed(question: str, answer: str, results: list[dict]) -> discord.Embed:
    embed = discord.Embed(
        title="Answer",
        description=answer[: MAX_MESSAGE_LEN - 100],
        color=0x5865F2,
    )
    embed.add_field(name="Question", value=question[:1000], inline=False)
    if results:
        sources = "\n".join(
            f"[{i + 1}] {r['url']}"[:100] for i, r in enumerate(results[:5])
        )
        embed.add_field(name="Sources", value=sources[:1024], inline=False)
    embed.set_footer(text=f"Powered by {config.OLLAMA_MODEL} + SearXNG")
    return embed


async def run_pipeline(question: str) -> tuple[str, list[dict]]:
    """Search the web, then stream a complete answer from Ollama."""
    try:
        results = await search(question)
    except SearchError as exc:
        raise RuntimeError(f"🔍 Search failed: {exc}") from exc

    parts: list[str] = []
    try:
        async for chunk in chat_stream(question, results):
            parts.append(chunk)
    except OllamaError as exc:
        raise RuntimeError(f"🤖 Ollama failed: {exc}") from exc

    answer = "".join(parts).strip() or "(empty response from model)"
    return answer, results


async def send_answer(target: discord.abc.Messageable, question: str):
    """Search, generate, and send the answer, with typing indicator + error handling."""
    async with target.typing():
        try:
            answer, results = await run_pipeline(question)
        except RuntimeError as exc:
            await target.send(str(exc)[:MAX_MESSAGE_LEN])
            return

    embed = build_embed(question, answer, results)
    await target.send(embed=embed)

    # If the answer was too long for the embed, send the rest as messages
    if len(answer) > MAX_MESSAGE_LEN - 100:
        rest = answer[MAX_MESSAGE_LEN - 100 :]
        for i in range(0, len(rest), MAX_MESSAGE_LEN):
            await target.send(rest[i : i + MAX_MESSAGE_LEN])


async def fetch_github_release(tag: str | None = None) -> dict | None:
    repo = config.GITHUB_REPO
    if tag:
        url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"
    else:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
    headers = {"Accept": "application/vnd.github+json"}
    if config.GITHUB_TOKEN:
        headers["Authorization"] = f"Bearer {config.GITHUB_TOKEN}"
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            if resp.status != 200:
                return None
            return await resp.json()


def build_release_embed(release: dict) -> discord.Embed:
    tag = release.get("tag_name", "release")
    name = release.get("name") or tag
    body = (release.get("body") or "").strip()
    if len(body) > 3900:
        body = body[:3900] + "\n…"
    embed = discord.Embed(
        title=f"📢 {name}",
        description=body or "No release notes provided.",
        color=0x57F287,
        url=release.get("html_url"),
    )
    assets = release.get("assets", [])
    links = []
    for asset in assets:
        links.append(f"[{asset['name']}]({asset['browser_download_url']})")
    if links:
        embed.add_field(name="Downloads", value="\n".join(links)[:1024], inline=False)
    embed.set_footer(text=f"{config.GITHUB_REPO} · {tag}")
    return embed


def classify_update(release: dict) -> str:
    """Return 'everyone' for big updates, otherwise 'here'."""
    text = " ".join([
        str(release.get("name") or ""),
        str(release.get("tag_name") or ""),
        str(release.get("body") or ""),
    ]).lower()
    if any(keyword in text for keyword in config.BIG_UPDATE_KEYWORDS):
        return "everyone"
    return "here"


def _is_admin(interaction: discord.Interaction) -> bool:
    if interaction.guild is None:
        return False
    member = interaction.user
    if not isinstance(member, discord.Member):
        return False
    return member.guild_permissions.manage_messages or member.guild_permissions.administrator


async def post_announcement(channel, title: str, message: str, ping: str = "none"):
    embed = discord.Embed(title=title, description=message[:4096], color=0xFEE75C)
    content = None
    if ping == "everyone":
        content = "@everyone"
    elif ping == "here":
        content = "@here"
    elif ping == "role" and config.ANNOUNCE_ROLE_ID:
        content = f"<@&{config.ANNOUNCE_ROLE_ID}>"
    await channel.send(content=content, embed=embed)


@tree.command(name="setchannels", description="Set this server's announcements and changelog channels.")
@app_commands.describe(
    announcements="Channel where new releases get announced",
    changelog="Channel where full changelogs are posted",
)
@app_commands.choices(
    announcements=app_commands.ChannelType,
    changelog=app_commands.ChannelType,
)
async def setchannels_command(
    interaction: discord.Interaction,
    announcements: discord.TextChannel,
    changelog: discord.TextChannel,
):
    if not _is_admin(interaction):
        await interaction.response.send_message("You need Manage Messages permission.", ephemeral=True)
        return
    data = _load_channels()
    data[str(interaction.guild_id)] = {
        "announcements": announcements.id,
        "changelog": changelog.id,
    }
    _save_channels(data)
    await interaction.response.send_message(
        f"✅ Announcements → <#{announcements.id}>\n📄 Changelog → <#{changelog.id}>",
        ephemeral=True,
    )


@tree.command(name="showchannels", description="Show this server's configured announcement channels.")
async def showchannels_command(interaction: discord.Interaction):
    stored = _load_channels().get(str(interaction.guild_id), {})
    announce = int(stored.get("announcements") or config.ANNOUNCEMENTS_CHANNEL_ID or 0)
    changelog = int(stored.get("changelog") or config.CHANGELOG_CHANNEL_ID or 0)
    if not announce and not changelog:
        await interaction.response.send_message("No channels configured yet. Use /setchannels.", ephemeral=True)
        return
    text = []
    if announce:
        text.append(f"📢 Announcements → <#{announce}>")
    if changelog:
        text.append(f"📄 Changelog → <#{changelog}>")
    await interaction.response.send_message("\n".join(text), ephemeral=True)


@tree.command(name="announce", description="Post an announcement to the announcements channel.")
@app_commands.describe(title="Announcement title", message="Announcement body", ping="Ping type: none, here, everyone, role")
@app_commands.choices(ping=[
    app_commands.Choice(name="none", value="none"),
    app_commands.Choice(name="@here", value="here"),
    app_commands.Choice(name="@everyone", value="everyone"),
    app_commands.Choice(name="role", value="role"),
])
async def announce_command(interaction: discord.Interaction, title: str, message: str, ping: str = "none"):
    if not _is_admin(interaction):
        await interaction.response.send_message("You need Manage Messages permission.", ephemeral=True)
        return
    announce_cid, _ = resolve_channels(interaction.guild_id)
    channel = None
    if announce_cid:
        channel = client.get_channel(announce_cid)
    if channel is None:
        channel = interaction.channel
    if channel is None:
        await interaction.response.send_message("No announcements channel configured.", ephemeral=True)
        return
    await interaction.response.send_message("Posting announcement...", ephemeral=True)
    await post_announcement(channel, title, message, ping)
    await interaction.edit_original_response(content="Announcement posted.")


@tree.command(name="changelog", description="Post the latest GitHub release changelog.")
@app_commands.describe(tag="Release tag (leave empty for latest)")
async def changelog_command(interaction: discord.Interaction, tag: str = ""):
    if not _is_admin(interaction):
        await interaction.response.send_message("You need Manage Messages permission.", ephemeral=True)
        return
    _, cid = resolve_channels(interaction.guild_id)
    cid = cid or config.ANNOUNCEMENTS_CHANNEL_ID
    channel = None
    if cid:
        channel = client.get_channel(cid)
    if channel is None:
        channel = interaction.channel
    if channel is None:
        await interaction.response.send_message("No channel available.", ephemeral=True)
        return
    await interaction.response.send_message("Fetching changelog...", ephemeral=True)
    release = await fetch_github_release(tag or None)
    if not release:
        await interaction.edit_original_response(content="Could not fetch that release.")
        return
    embed = build_release_embed(release)
    await channel.send(embed=embed)
    await interaction.edit_original_response(content="Changelog posted.")


@tree.command(name="pinlatest", description="Pin the most recent message in the announcements channel.")
async def pinlatest_command(interaction: discord.Interaction):
    if not _is_admin(interaction):
        await interaction.response.send_message("You need Manage Messages permission.", ephemeral=True)
        return
    announce_cid, _ = resolve_channels(interaction.guild_id)
    channel = None
    if announce_cid:
        channel = client.get_channel(announce_cid)
    if channel is None:
        channel = interaction.channel
    if channel is None:
        await interaction.response.send_message("No channel available.", ephemeral=True)
        return
    await interaction.response.send_message("Pinning latest message...", ephemeral=True)
    messages = [m async for m in channel.history(limit=1)]
    if not messages:
        await interaction.edit_original_response(content="No messages to pin.")
        return
    try:
        await messages[0].pin()
    except discord.HTTPException as exc:
        await interaction.edit_original_response(content=f"Pin failed: {exc}")
        return
    await interaction.edit_original_response(content="Pinned latest message.")


@tasks.loop(minutes=config.POLL_INTERVAL_MINUTES)
async def release_poller():
    # Release poller is global: prefer .env channels, else any guild-configured ones.
    data = _load_channels()
    poll_announce = config.ANNOUNCEMENTS_CHANNEL_ID
    poll_changelog = config.CHANGELOG_CHANNEL_ID or config.ANNOUNCEMENTS_CHANNEL_ID
    if not poll_announce:
        for entry in data.values():
            poll_announce = int(entry.get("announcements") or 0)
            if poll_announce:
                break
    if not poll_changelog:
        for entry in data.values():
            poll_changelog = int(entry.get("changelog") or 0)
            if poll_changelog:
                break
    changelog_cid = poll_changelog
    announce_cid = poll_announce
    if not changelog_cid and not announce_cid:
        return

    release = await fetch_github_release()
    if not release:
        return
    tag = release.get("tag_name", "")
    if not tag:
        return
    try:
        last = LAST_RELEASE_FILE.read_text().strip()
    except FileNotFoundError:
        last = ""
    if tag == last:
        return
    LAST_RELEASE_FILE.write_text(tag)

    embed = build_release_embed(release)
    ping_type = classify_update(release)
    mention = "@everyone" if ping_type == "everyone" else "@here"

    # Post full changelog to changelog channel
    if changelog_cid:
        channel = client.get_channel(changelog_cid)
        if channel is None:
            try:
                channel = await client.fetch_channel(changelog_cid)
            except discord.HTTPException:
                channel = None
        if channel is not None:
            await channel.send(embed=embed)

    # Post new-release announcement to announcements channel
    if announce_cid:
        channel = client.get_channel(announce_cid)
        if channel is None:
            try:
                channel = await client.fetch_channel(announce_cid)
            except discord.HTTPException:
                channel = None
        if channel is not None:
            announcement = discord.Embed(
                title=f"New release: {release.get('name') or tag}",
                description="A new version is available. See the changelog channel for full notes.",
                color=0x5865F2,
                url=release.get("html_url"),
            )
            assets = release.get("assets", [])
            links = [f"[{a['name']}]({a['browser_download_url']})" for a in assets]
            if links:
                announcement.add_field(name="Downloads", value="\n".join(links)[:1024], inline=False)
            await channel.send(content=mention, embed=announcement)


@release_poller.before_loop
async def before_release_poller():
    await client.wait_until_ready()


@tree.command(name="ask", description="Ask the AI a question — it searches the web first.", dm_permission=True)
@app_commands.allowed_installs(guilds=True, users=True)
@app_commands.describe(question="What do you want to know?")
async def ask_command(interaction: discord.Interaction, question: str):
    await interaction.response.defer(thinking=True)
    channel = interaction.channel
    if channel is None:
        await interaction.followup.send("⚠️ Couldn't find the channel.")
        return
    async with channel.typing():
        try:
            answer, results = await run_pipeline(question)
        except RuntimeError as exc:
            await interaction.followup.send(str(exc)[:MAX_MESSAGE_LEN])
            return

    embed = build_embed(question, answer, results)
    await interaction.followup.send(embed=embed)

    if len(answer) > MAX_MESSAGE_LEN - 100:
        rest = answer[MAX_MESSAGE_LEN - 100 :]
        for i in range(0, len(rest), MAX_MESSAGE_LEN):
            await channel.send(rest[i : i + MAX_MESSAGE_LEN])


@client.event
async def on_message(message: discord.Message):
    if message.author.bot or not config.TEXT_TRIGGER_ENABLED:
        return

    # Respond to every message that contains "/ask"
    lower = message.content.lower()
    if config.TRIGGER in lower:
        # Strip the trigger and use the rest as the question
        question = lower.replace(config.TRIGGER, " ").strip()
        if not question:
            await message.reply("Usage: include a question after `/ask`.")
            return
        await send_answer(message.channel, question)


@client.event
async def on_ready():
    await tree.sync()
    await client.change_presence(
        status=discord.Status.online,
        activity=discord.CustomActivity(name="🚀 Try eAI today!"),
    )
    if not release_poller.is_running():
        release_poller.start()
    print(f"✅ Logged in as {client.user} — slash commands synced.")


def main():
    if not config.DISCORD_TOKEN:
        raise SystemExit("Set DISCORD_TOKEN in your .env file.")
    if config.PROXY:
        # discord.py's HTTPClient supports a proxy for API + gateway connections
        client.http.proxy = config.PROXY

    import signal

    def _shutdown(signum, frame):
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.create_task(client.close())
            else:
                client.run(config.DISCORD_TOKEN)  # no-op guard
        except Exception:
            pass

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)
    client.run(config.DISCORD_TOKEN)


if __name__ == "__main__":
    main()
