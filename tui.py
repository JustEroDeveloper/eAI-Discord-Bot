#!/usr/bin/env python3
"""Terminal UI for the eAI Discord bot (Ollama + SearXNG).

Usage:  python tui.py
Keys:   s = start, k = stop, r = restart, l = view logs, h = service health, q = quit
"""

import os
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from rich import box
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table

BASE = Path(__file__).resolve().parent
VENV_PYTHON = BASE / ".venv" / "bin" / "python"
BOT_PY = BASE / "bot.py"
LOG_FILE = BASE / "bot.log"
PID_FILE = BASE / "bot.pid"

console = Console()


def bot_pids() -> list[int]:
    try:
        out = subprocess.run(
            ["pgrep", "-f", "bot.py"], capture_output=True, text=True, check=False
        ).stdout.split()
        return [int(p) for p in out if int(p) != os.getpid()]
    except Exception:
        return []


def is_running() -> bool:
    return bool(bot_pids())


def start_bot() -> str:
    if is_running():
        return "Already running."
    with open(LOG_FILE, "ab") as log:
        proc = subprocess.Popen(
            [str(VENV_PYTHON), "-u", str(BOT_PY)],
            cwd=BASE,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    PID_FILE.write_text(str(proc.pid))
    time.sleep(3)
    return "Started ✅" if is_running() else "Start attempted — check logs."


def stop_bot() -> str:
    pids = bot_pids()
    if not pids:
        return "Not running."
    for pid in pids:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
    time.sleep(1)
    for pid in bot_pids():
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    return "Stopped 🛑"


_no_proxy_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http_ok(url: str, timeout: float = 3.0) -> bool:
    try:
        with _no_proxy_opener.open(url, timeout=timeout) as resp:
            return resp.status < 500
    except Exception:
        return False


def service_health() -> Table:
    table = Table(box=box.SIMPLE, show_header=True, header_style="bold cyan")
    table.add_column("Service")
    table.add_column("Status")
    table.add_column("Endpoint")

    ollama = http_ok("http://localhost:11434/")
    searxng = http_ok("http://localhost:8080/search?q=ping&format=json")
    bot = is_running()

    table.add_row("Ollama", "🟢 up" if ollama else "🔴 down", "http://localhost:11434")
    table.add_row("SearXNG", "🟢 up" if searxng else "🔴 down", "http://localhost:8080")
    table.add_row("Discord bot", "🟢 running" if bot else "⚪ stopped", str(BOT_PY.name))
    return table


def status_panel() -> Panel:
    pids = bot_pids()
    state = (
        f"[green]● RUNNING[/green]  (pid {', '.join(map(str, pids))})"
        if pids
        else "[red]● STOPPED[/red]"
    )
    return Panel(
        f"  {state}\n\n"
        "  [bold]s[/bold] start   [bold]k[/bold] stop   [bold]r[/bold] restart\n"
        "  [bold]l[/bold] logs    [bold]h[/bold] service health   [bold]q[/bold] quit",
        title="🤖 eAI Discord Bot",
        border_style="green" if pids else "red",
    )


def show_logs(lines: int = 30):
    console.clear()
    if LOG_FILE.exists():
        tail = LOG_FILE.read_text(errors="replace").splitlines()[-lines:]
        console.print(Panel("\n".join(tail) or "(empty log)", title="📜 bot.log (last lines)", border_style="yellow"))
    else:
        console.print("[yellow]No bot.log yet.[/yellow]")
    input("\nPress Enter to return…")


def main():
    message = ""
    while True:
        console.clear()
        console.print(status_panel())
        console.print(service_health())
        if message:
            console.print(f"\n[bold]{message}[/bold]")
            message = ""
        try:
            key = console.input("\n[dim]Command [s/k/r/l/h/q] >[/dim] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            break
        if key == "s":
            message = start_bot()
        elif key == "k":
            message = stop_bot()
        elif key == "r":
            stop_bot()
            message = start_bot().replace("Started", "Restarted")
        elif key == "l":
            show_logs()
        elif key == "h":
            pass  # health table is already on screen
        elif key == "q":
            break
        else:
            message = "Unknown command. Use s/k/r/l/h/q."
    console.print("Bye 👋")


if __name__ == "__main__":
    main()
