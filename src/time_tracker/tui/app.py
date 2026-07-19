"""Textual interface for the first persistent timer workflow."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Protocol

from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Static

from time_tracker.domain.models import ActiveTimer, CompletedTimer


class TrackerGateway(Protocol):
    """Operations available to the TUI across the application boundary."""

    def get_active(self) -> ActiveTimer | None:
        """Return the recovered active timer."""
        ...

    def start(
        self,
        project: str,
        activity: str,
        note: str | None = None,
    ) -> ActiveTimer:
        """Persist and return a new active timer."""
        ...

    def stop(self) -> CompletedTimer | None:
        """Persist and return the stopped timer."""
        ...


class TimeTrackerApp(App[None]):
    """Keyboard-first start/stop screen backed by the local agent."""

    TITLE = "Time Tracker"
    SUB_TITLE = "Persistent walking skeleton"
    BINDINGS = [
        Binding("f5", "start_timer", "Start / switch"),
        Binding("f6", "stop_timer", "Stop"),
        Binding("ctrl+q", "quit", "Quit"),
    ]
    CSS = """
    Screen {
        align: center middle;
    }

    #tracker {
        width: 72;
        height: auto;
        padding: 1 2;
        border: round $accent;
    }

    #active-timer {
        height: 5;
        margin-bottom: 1;
        padding: 1;
        text-align: center;
        background: $panel;
        content-align: center middle;
    }

    Input {
        margin-bottom: 1;
    }

    #actions {
        height: auto;
        margin-top: 1;
    }

    #actions Button {
        width: 1fr;
        margin-right: 1;
    }

    #message {
        height: 2;
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, client: TrackerGateway) -> None:
        super().__init__()
        self.client = client
        self.active_timer: ActiveTimer | None = None

    def compose(self) -> ComposeResult:
        """Compose the single-screen timer workflow."""
        yield Header()
        with Vertical(id="tracker"):
            yield Static("No timer running", id="active-timer")
            yield Input(placeholder="Project", id="project")
            yield Input(placeholder="Activity", id="activity")
            yield Input(placeholder="Optional note", id="note")
            with Horizontal(id="actions"):
                yield Button("Start / switch  F5", id="start-button", variant="success")
                yield Button("Stop  F6", id="stop-button", variant="warning")
            yield Static("", id="message")
        yield Footer()

    async def on_mount(self) -> None:
        """Recover any persisted active timer when the TUI reconnects."""
        self.set_interval(1.0, self._render_active)
        try:
            self.active_timer = await asyncio.to_thread(self.client.get_active)
        except Exception as error:
            self._show_message(str(error), error=True)
        self._render_active()

    @on(Button.Pressed, "#start-button")
    async def handle_start_button(self) -> None:
        """Handle pointer activation of the start action."""
        await self._start_timer()

    @on(Button.Pressed, "#stop-button")
    async def handle_stop_button(self) -> None:
        """Handle pointer activation of the stop action."""
        await self._stop_timer()

    async def action_start_timer(self) -> None:
        """Start or switch the timer from the F5 binding."""
        await self._start_timer()

    async def action_stop_timer(self) -> None:
        """Stop the timer from the F6 binding."""
        await self._stop_timer()

    async def _start_timer(self) -> None:
        project = self.query_one("#project", Input).value
        activity = self.query_one("#activity", Input).value
        note = self.query_one("#note", Input).value
        try:
            self.active_timer = await asyncio.to_thread(
                self.client.start,
                project,
                activity,
                note,
            )
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self._show_message("Timer persisted and running.")
        self._render_active()

    async def _stop_timer(self) -> None:
        try:
            completed = await asyncio.to_thread(self.client.stop)
        except Exception as error:
            self._show_message(str(error), error=True)
            return
        self.active_timer = None
        if completed is None:
            self._show_message("No active timer to stop.")
        else:
            self._show_message(
                f"Stopped {completed.project} / {completed.activity} "
                f"after {_format_duration(completed.duration)}."
            )
        self._render_active()

    def _render_active(self) -> None:
        active_widget = self.query_one("#active-timer", Static)
        stop_button = self.query_one("#stop-button", Button)
        if self.active_timer is None:
            active_widget.update("No timer running")
            stop_button.disabled = True
            return

        timer = self.active_timer
        now = datetime.now(UTC)
        elapsed = max(now - timer.started_at, timedelta())
        local_start = timer.started_at.astimezone().isoformat(timespec="seconds")
        note = f"\n{timer.note}" if timer.note else ""
        active_widget.update(
            f"{timer.project} / {timer.activity}\n"
            f"Started {local_start} · {_format_duration(elapsed)}{note}"
        )
        stop_button.disabled = False

    def _show_message(self, message: str, *, error: bool = False) -> None:
        widget = self.query_one("#message", Static)
        widget.update(message)
        widget.styles.color = self.theme_variables["error" if error else "success"]


def _format_duration(duration: timedelta) -> str:
    total_seconds = max(0, int(duration.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
