"""CLI visual feedback — thin wrapper around Rich.

Emits icon-prefixed event lines and colored session banners, plus
a Rich-flavored logging handler. Importing this module does nothing
until a helper is called.
"""

from __future__ import annotations

import logging
from rich.console import Console
from rich.logging import RichHandler
from rich.panel import Panel
from rich.text import Text

console = Console()


def install_logging(level: int = logging.INFO) -> None:
    handler = RichHandler(
        console=console,
        show_time=True,
        show_path=False,
        rich_tracebacks=True,
        markup=True,
    )
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="%H:%M:%S",
        handlers=[handler],
    )
    # Quiet noisy deps
    for noisy in ("websockets", "google", "httpx", "httpcore", "asyncio"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


def startup(model: str, simulate: bool, webcam: bool, webcam_detail: str = "") -> None:
    body = Text()
    body.append("Model   ", style="bold")
    body.append(f"{model}\n", style="cyan")
    body.append("Mode    ", style="bold")
    body.append("simulate" if simulate else "raspberry-pi", style="yellow")
    body.append("\nCamera  ", style="bold")
    if webcam:
        body.append(f"real webcam — {webcam_detail}", style="green")
    else:
        body.append("mock test frames", style="dim")
    console.print(Panel(body, title="[bold magenta]🤖 GEMINI LIVE ROBOT[/]", border_style="magenta"))


def session_start(n: int) -> None:
    console.rule(f"[bold green]▶ Session {n} started")


def session_end(n: int, reason: str = "") -> None:
    suffix = f" — {reason}" if reason else ""
    console.rule(f"[dim]■ Session {n} ended{suffix}")


def wake_prompt() -> None:
    console.print("\n[bold yellow]>>> Press ENTER to wake the robot[/]", end=" ")


def event(icon: str, label: str, message: str, style: str = "white") -> None:
    console.print(f"  [{style}]{icon} {label:<9}[/] {message}")


def mic_started() -> None:
    event("🎤", "MIC", "[dim]capturing at 16 kHz[/]", style="cyan")


def speaker_started() -> None:
    event("🔊", "SPEAKER", "[dim]ready at 24 kHz[/]", style="cyan")


def camera_frame_sent(nbytes: int, source: str) -> None:
    event("📷", "CAMERA", f"[dim]sent {nbytes:,} bytes ({source})[/]", style="blue")


def audio_out_chunk(nbytes: int) -> None:
    # Rate-limited to avoid spamming; print ONE dot per chunk so user sees flow.
    console.print("[cyan]·[/]", end="", soft_wrap=True)


def audio_out_complete() -> None:
    console.print()  # newline after dots


def tool_call(name: str, args: dict) -> None:
    args_preview = ", ".join(f"{k}={v!r}" for k, v in list(args.items())[:3])
    if len(args) > 3:
        args_preview += ", ..."
    event("🔧", "TOOL", f"[bold]{name}[/]({args_preview})", style="magenta")


def tool_result(name: str, result: dict) -> None:
    if "error" in result:
        event(" ↳", "", f"[red]error: {result['error']}[/]", style="red")
    else:
        # Show a short preview of the result
        preview = ", ".join(f"{k}={v!r}" for k, v in list(result.items())[:3])
        if len(preview) > 90:
            preview = preview[:87] + "..."
        event(" ↳", "", f"[dim]{preview}[/]", style="dim")


def error(msg: str) -> None:
    console.print(f"[bold red]✖ {msg}[/]")


def info(msg: str) -> None:
    console.print(f"[dim]{msg}[/]")


# ── Live state feedback ─────────────────────────────────────
# These emit compact, color-coded "what is happening right now" lines.

def state_listening() -> None:
    console.print("  [bold cyan]🎙  LISTENING[/]  [dim]— speak now[/]")


def state_user_speaking() -> None:
    console.print("  [bold cyan]🗨  YOU SPEAKING[/]  [dim]— streaming mic audio to Gemini[/]")


def state_thinking() -> None:
    console.print("  [bold yellow]💭 GEMINI THINKING[/]  [dim]— processing your request[/]")


def state_speaking() -> None:
    console.print("  [bold green]🗣  GEMINI SPEAKING[/]  [dim]— audio streaming back[/]")


def state_tool_running(name: str) -> None:
    console.print(f"  [bold magenta]⚙  RUNNING TOOL[/]  [dim]— {name}[/]")


def user_transcript(text: str) -> None:
    if text.strip():
        console.print(f"  [cyan]you:[/]     [italic]\"{text.strip()}\"[/]")


def gemini_transcript(text: str) -> None:
    if text.strip():
        console.print(f"  [green]gemini:[/]  [italic]\"{text.strip()}\"[/]")


def heartbeat(state: str, elapsed: float, mic_chunks: int, out_chunks: int) -> None:
    console.print(
        f"  [dim]⏲  {state:<14} · {elapsed:4.1f}s in state · "
        f"mic {mic_chunks:>3} · audio {out_chunks:>3}[/]"
    )


def turn_timing(label: str, seconds: float) -> None:
    console.print(f"  [dim]⏱  {label}: {seconds*1000:.0f} ms[/]")


def server_event(name: str) -> None:
    console.print(f"  [dim]← server: {name}[/]")


# ── Debug / diagnostic streams ──────────────────────────────
# These are verbose on purpose — meant for the "why isn't turn 2 working?"
# phase. Toggle with env DEBUG_LIVE=1.

def mic_tick(real: int, silent: int, avg_rms: int, peak_rms: int) -> None:
    """One-second rollup of outgoing mic traffic."""
    style = "green" if real > 0 and peak_rms > 300 else "dim"
    console.print(
        f"  [{style}]📤 mic-1s · real={real:>2} silent={silent:>2} "
        f"avg_rms={avg_rms:>5} peak_rms={peak_rms:>5}[/]"
    )


def mic_voice_event(kind: str, rms: int) -> None:
    """Fired when we cross from silence→voice or voice→silence client-side."""
    if kind == "voice_start":
        console.print(f"  [bold yellow]🎤▶ voice onset (rms={rms})[/]")
    else:
        console.print(f"  [dim]🎤⏸ voice offset[/]")


def server_raw(summary: str) -> None:
    console.print(f"  [dim magenta]← raw: {summary}[/]")


def recv_wait(seconds: float) -> None:
    console.print(
        f"  [dim red]… recv_loop: {seconds:.1f}s since last server message[/]"
    )


def audio_send_error(exc: Exception) -> None:
    console.print(f"  [bold red]✖ send_audio_chunk failed: {exc!r}[/]")
