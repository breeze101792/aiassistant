"""The TUI orb: a full-screen curses frontend over the bus WebSocket.

A separate process (ADR-0017) that reuses :class:`OrbViewModel` from
``orb/model.py`` — the same Qt-free mapping the GUI orb renders. It speaks to
the assistant only through :class:`aiassistant.bridge.Bridge`, publishes the
same topics, and never imports Qt or touches an audio device.

One asyncio loop owns everything: the bridge, stdin (registered with
``loop.add_reader``, never a blocking read), and a 10 Hz redraw tick. All
curses calls happen on that one thread, which is why curses is safe here.
"""

import asyncio
import curses
import logging
import signal
import sys

from aiassistant.bridge import Bridge, BridgeError
from aiassistant.bus import topics
from aiassistant.orb.model import OrbViewModel, feed

from . import tokens
from .render import Renderer, UIState, error_visible

logger = logging.getLogger(__name__)

# Same watch set as the GUI orb (orb/app.py WATCHED_TOPICS); the TUI invents no
# topics. ``status.assistant.ready`` is not rendered, so it is not subscribed.
WATCHED_TOPICS = (
    topics.VOICE_STATE,
    topics.VOICE_LEVEL,
    topics.AGENT_DELTA,
    topics.AGENT_FINAL,
    topics.AGENT_TOOL_EVENT,
    topics.AGENT_TURN_ERROR,
    topics.AGENT_TRANSCRIPT_SNAPSHOT,
    topics.STATUS_HARNESS,
)

# The states in which an interrupt is meaningful (interactions.md § Escape).
ACTIVE_STATES = frozenset({"listening", "transcribing", "thinking", "speaking"})

# Error classes that set the ``backend-down`` overlay; anything else sets
# ``transcript-error`` (states.md § State sources).
HARNESS_ERROR_CLASS = "harness"

# States whose arrival clears a ``transcript-error`` overlay (states.md).
TURN_START_STATES = frozenset({"listening", "thinking"})


class TuiApp:
    """Owns the bridge, the view model, the curses screen, and the input loop."""

    def __init__(self, url: str, token: str, identity: str,
                 renderer: Renderer | None = None, bridge: Bridge | None = None):
        self.model = OrbViewModel()
        self.ui = UIState()
        self.renderer = renderer or Renderer(identity=identity)
        self._bridge = bridge
        self._url = url
        self._token = token
        self._stdscr: curses.window | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop = False
        self._prev_row_count = 0
        self._snapshot_pending = False
        self._muted = False
        self._signal_handlers: dict = {}

    # ── Bridge ───────────────────────────────────────────────

    def _ensure_bridge(self) -> Bridge:
        if self._bridge is None:
            self._bridge = Bridge(
                name="tui",
                url=self._url,
                token=self._token,
                on_message=self._on_message,
                on_state=self._on_state,
            )
        return self._bridge

    def _on_message(self, topic: str, payload: dict) -> None:
        """Apply one bus message to the shared view model, then the overlays.

        Mirrors ``orb/app.py``: after a delta, a gap means the transcript is
        incomplete, so a snapshot is requested rather than rendering a hole.
        The overlay rules (states.md § State sources) live here because the view
        model deliberately keeps only the base state word.
        """
        prior_state = self.model.state
        feed(self.model, topic, payload)
        self._apply_overlay(topic, payload, prior_state)
        if self.model.needs_snapshot and not self._snapshot_pending:
            self._snapshot_pending = True
            self._request_snapshot()
        elif not self.model.needs_snapshot:
            self._snapshot_pending = False

    def _apply_overlay(self, topic: str, payload: dict, prior_state: str) -> None:
        """Layer ``backend-down`` / ``transcript-error`` on the base state.

        The base state comes from ``voice.state`` (and starts at ``connecting``);
        an overlay never silently replaces it. Transitions follow states.md:
        ``backend-down`` clears on the next delta, final, or voice state;
        ``transcript-error`` clears on the next listening/thinking. Esc hides the
        error row but keeps the base glyph, as the overlay rules require.
        """
        if topic == topics.VOICE_STATE:
            state = payload.get("state")
            if state:
                self.ui.base_state = state
            if self.ui.overlay == "backend_down":
                self.ui.overlay = ""
            elif self.ui.overlay == "transcript_error" and state in TURN_START_STATES:
                self.ui.overlay = ""
                self.ui.error_dismissed = False
        elif topic == topics.AGENT_TURN_ERROR:
            error_class = str(payload.get("class", ""))
            self.ui.error_class = error_class
            self.ui.error_dismissed = False
            self.ui.overlay = ("backend_down" if error_class == HARNESS_ERROR_CLASS
                               else "transcript_error")
            self.ui.base_state = prior_state or self.ui.base_state
        elif topic in (topics.AGENT_DELTA, topics.AGENT_FINAL):
            if self.ui.overlay == "backend_down":
                self.ui.overlay = ""
            # ``on_error`` set the model's state to "error"; once the overlay is
            # gone, restore the base word so the header does not show %o%.
            if self.model.state == "error" and self.ui.base_state:
                self.model.state = self.ui.base_state

        if topic != topics.AGENT_TURN_ERROR and self.model.state != "error":
            # The base state tracks the model for every non-error event.
            self.ui.base_state = self.model.state

    def _request_snapshot(self) -> None:
        """Ask for the transcript after a gap. Best-effort, never fatal."""
        if self._loop is None:
            return
        self._loop.create_task(self._publish(
            topics.AGENT_TRANSCRIPT_SNAPSHOT + ".request", {}))

    def _on_state(self, state: str) -> None:
        """Bridge state change: track it and re-subscribe on connect.

        The bridge restores its own subscriptions on reconnect, so this only
        covers the first connect and any subscribe that raced it
        (``BridgeError``); a later ``connected`` retries.
        """
        self.ui.bridge_state = state
        if state == tokens.BRIDGE_CONNECTED:
            self._resubscribe()
        elif state.startswith("disconnected") or state == "closed":
            self.model.state = "connecting"
            self.ui.base_state = "connecting"

    def _resubscribe(self) -> None:
        if self._loop is None:
            return
        self._loop.create_task(self._subscribe_all())

    async def _subscribe_all(self) -> None:
        bridge = self._ensure_bridge()
        # The bridge replays its own subscriptions on reconnect, so subscribe
        # only on the first connect. Subscribing again would register a second
        # forwarder server-side and double every message.
        if bridge.subscriptions:
            return
        for topic in WATCHED_TOPICS:
            try:
                await bridge.subscribe(topic)
            except BridgeError:
                # The subscribe raced the connection; the next "connected"
                # state re-runs this.
                logger.debug("subscribe to %s raced the connection", topic)
                return

    async def _publish(self, topic: str, payload: dict) -> None:
        try:
            await self._ensure_bridge().publish(topic, payload)
        except BridgeError:
            logger.debug("publish of %s failed; not connected", topic)

    # ── Lifecycle ────────────────────────────────────────────

    async def run(self) -> int:
        """Run until Ctrl+D, EOF, or a signal. Returns a process exit code."""
        self._loop = asyncio.get_running_loop()
        self._install_signal_handlers()
        self._stdscr = curses.initscr()
        try:
            self._configure_screen()
            self.renderer.setup()

            # stdin arrives as a loop callback, never a blocking read.
            add_reader = getattr(self._loop, "add_reader", None)
            self._reader_added = False
            if add_reader is not None:
                try:
                    add_reader(sys.stdin.fileno(), self._on_stdin_ready)
                    self._reader_added = True
                except (ValueError, OSError, NotImplementedError):
                    logger.debug("stdin not reader-capable; quitting on EOF only")

            self._draw()

            bridge_task = asyncio.ensure_future(self._ensure_bridge().run())
            draw_task = asyncio.ensure_future(self._draw_loop())
            try:
                await self._wait_stopped()
            finally:
                self._remove_reader()
                for task in (draw_task, bridge_task):
                    task.cancel()
                await asyncio.gather(draw_task, bridge_task, return_exceptions=True)
                await self._close_bridge()
        finally:
            # Every exit path restores the terminal, including a crash.
            curses.endwin()
            self._restore_signal_handlers()
        return 0

    def _remove_reader(self) -> None:
        if not getattr(self, "_reader_added", False) or self._loop is None:
            return
        try:
            self._loop.remove_reader(sys.stdin.fileno())
        except (AttributeError, ValueError, OSError):
            pass
        self._reader_added = False

    async def _wait_stopped(self) -> None:
        while not self._stop:
            await asyncio.sleep(tokens.DRAW_INTERVAL_S)
            if sys.stdin.isatty():
                continue
            # A piped stdin has no reader signal; an EOF ends the app.
            self._check_stdin_eof()

    def _check_stdin_eof(self) -> None:
        import select
        try:
            ready, _, _ = select.select([sys.stdin], [], [], 0)
        except (ValueError, OSError):
            return
        if not ready:
            return
        try:
            if sys.stdin.read(1) == "":
                self.stop()
        except (ValueError, OSError):
            return

    async def _draw_loop(self) -> None:
        """Repaint at ~10 Hz. ``draw`` is idempotent, so this is not animation:
        the design animates nothing, and a full repaint of a terminal screen is
        cheap (layout.md § Resize).
        """
        while not self._stop:
            await asyncio.sleep(tokens.DRAW_INTERVAL_S)
            self._draw()

    def _draw(self) -> None:
        """Repaint once.

        ``Renderer.draw`` swallows and logs its own failures, so a render error
        never crashes the process or leaves the terminal broken; any escape
        here still reaches the ``finally`` in ``run``.
        """
        if self._stdscr is None:
            return
        self._track_new_rows()
        self.renderer.draw(self._stdscr, self.model, self.ui)

    def stop(self) -> None:
        self._stop = True

    def _configure_screen(self) -> None:
        screen = self._stdscr
        if screen is None:
            return
        try:
            curses.noecho()
            # raw() keeps Ctrl+C as an input key (delivered as 3) instead of
            # raising SIGINT, so the TUI can treat it as the no-op the design
            # specifies while an external SIGINT/SIGTERM still stops the app.
            curses.raw()
            screen.keypad(True)
            # A short read timeout lets curses assemble an escape sequence (an
            # arrow key is ESC + two bytes) before it is mistaken for a bare Esc.
            screen.timeout(tokens.INPUT_TIMEOUT_MS)
        except curses.error:
            logger.debug("screen setup partially failed", exc_info=True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass  # Some terminals have no visible cursor to hide.

    # ── Input ────────────────────────────────────────────────

    def _on_stdin_ready(self) -> None:
        """Loop callback: read the keys that are already queued.

        ``getch`` returns -1 once the queue drains, so the loop ends there; the
        screen's short timeout is what lets curses finish an escape sequence
        rather than reporting a bare Esc.
        """
        if self._stdscr is None or self._stop:
            return
        for _ in range(tokens.INPUT_BATCH):
            try:
                key = self._stdscr.getch()
            except curses.error:
                continue
            if key == -1:
                break
            self._handle_key(key)
            if self._stop:
                break

    def _handle_key(self, key: int) -> None:
        if key == tokens.CTRL_D:
            self._stop = True
            return
        if key == tokens.CTRL_C:
            return  # The app owns Ctrl+C; it is not quit (layout.md § Composer).
        if key == curses.KEY_RESIZE:
            return
        if key == tokens.CTRL_L:
            self._clear()
            return
        if key == tokens.CTRL_T:
            self._toggle_mute()
            return
        if key == tokens.CTRL_DOT:
            asyncio.ensure_future(self._publish(topics.COMMAND_AGENT_INTERRUPT, {}))
            return
        if key == curses.KEY_F1:
            self.ui.help_open = not self.ui.help_open
            return
        if key == tokens.ESCAPE:
            self._handle_escape()
            return
        if self.ui.help_open:
            return  # Any other key is swallowed while the help overlay is open.
        if key in (curses.KEY_ENTER, 10, 13):
            self._submit()
            return
        if key in (curses.KEY_BACKSPACE, tokens.BACKSPACE, tokens.DELETE):
            self._backspace()
            return
        if key == curses.KEY_LEFT:
            self._cursor_left()
            return
        if key == curses.KEY_RIGHT:
            self._cursor_right()
            return
        if self._scroll_by_key(key):
            return
        if 32 <= key < 127:
            self._insert(chr(key))

    def _scroll_by_key(self, key: int) -> bool:
        if key == curses.KEY_PPAGE:
            self.ui.scroll += self._page_height()
        elif key == curses.KEY_NPAGE:
            self.ui.scroll = max(0, self.ui.scroll - self._page_height())
        elif key == curses.KEY_UP:
            self.ui.scroll += 1
        elif key == curses.KEY_DOWN:
            self.ui.scroll = max(0, self.ui.scroll - 1)
        elif key == curses.KEY_HOME:
            self.ui.scroll = tokens.SCROLL_MAX
        elif key == curses.KEY_END:
            self.ui.scroll = 0
        else:
            return False
        if self.ui.scroll == 0:
            self.ui.new_count = 0
        return True

    def _page_height(self) -> int:
        if self._stdscr is None:
            return 1
        try:
            rows, _ = self._stdscr.getmaxyx()
        except curses.error:
            return 1
        return max(1, rows - tokens.CHROME_ROWS)

    # ── Composer editing ─────────────────────────────────────

    def _insert(self, char: str) -> None:
        text = self.ui.composer
        pos = self.ui.cursor
        self.ui.composer = text[:pos] + char + text[pos:]
        self.ui.cursor = pos + 1

    def _backspace(self) -> None:
        text = self.ui.composer
        pos = self.ui.cursor
        if pos <= 0:
            return
        self.ui.composer = text[:pos - 1] + text[pos:]
        self.ui.cursor = pos - 1

    def _cursor_left(self) -> None:
        self.ui.cursor = max(0, self.ui.cursor - 1)

    def _cursor_right(self) -> None:
        self.ui.cursor = min(len(self.ui.composer), self.ui.cursor + 1)

    def _submit(self) -> None:
        text = self.ui.composer.strip()
        if not text:
            return
        self.ui.composer = ""
        self.ui.cursor = 0
        if text.startswith("/"):
            self._local_command(text)
            return
        # Append the user's own row optimistically, then publish.
        self.model.on_user_input({"text": text})
        asyncio.ensure_future(self._publish(
            topics.USER_INPUT_TEXT, {"text": text, "channel": topics.CHANNEL_TUI}))

    def _local_command(self, text: str) -> None:
        command = text.split()[0]
        if command == "/clear":
            self._clear()
        elif command == "/help":
            self.ui.help_open = True
        else:
            logger.info("unknown local command: %s", command)

    def _clear(self) -> None:
        self.model.clear()
        self.ui.scroll = 0
        self.ui.new_count = 0

    def _toggle_mute(self) -> None:
        self._muted = not self._muted
        asyncio.ensure_future(self._publish(
            topics.COMMAND_VOICE_MUTE, {"muted": self._muted}))

    def _handle_escape(self) -> None:
        """The documented resolution order (layout.md § Controls).

        Help closes first, then the error overlay is dismissed (the row and the
        ``! Backend down`` text go; the base state glyph stays), then the
        composer clears, then an active turn is interrupted. Esc never quits.
        """
        if self.ui.help_open:
            self.ui.help_open = False
        elif error_visible(self.model, self.ui):
            self.ui.error_dismissed = True
            self.ui.overlay = ""
        elif self.ui.composer:
            self.ui.composer = ""
            self.ui.cursor = 0
        elif self.ui.display_state(self.model) in ACTIVE_STATES:
            asyncio.ensure_future(self._publish(topics.COMMAND_AGENT_INTERRUPT, {}))

    # ── Pin and new-row tracking ─────────────────────────────

    def _track_new_rows(self) -> None:
        count = len(self.model.transcript)
        if self.ui.scroll > 0 and count > self._prev_row_count:
            self.ui.new_count += count - self._prev_row_count
        self._prev_row_count = count

    # ── Signals and shutdown ─────────────────────────────────

    def _install_signal_handlers(self) -> None:
        """Set a stop flag on SIGINT/SIGTERM instead of dying mid-draw."""
        loop = self._loop
        if loop is None:
            return
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                self._signal_handlers[sig] = signal.getsignal(sig)
                loop.add_signal_handler(sig, self.stop)
            except (NotImplementedError, RuntimeError, ValueError):
                logger.debug("signal %s handler not installed", sig)

    def _restore_signal_handlers(self) -> None:
        loop = self._loop
        for sig, previous in list(self._signal_handlers.items()):
            try:
                if loop is not None:
                    loop.remove_signal_handler(sig)
            except (NotImplementedError, RuntimeError, ValueError):
                pass
            try:
                signal.signal(sig, previous)
            except (ValueError, OSError, TypeError):
                pass
        self._signal_handlers.clear()

    async def _close_bridge(self) -> None:
        if self._bridge is None:
            return
        try:
            await self._bridge.close()
        except Exception:
            logger.debug("bridge close raised", exc_info=True)
        self.ui.bridge_state = "closed"


async def run(url: str, token: str, identity: str) -> int:
    """Convenience entry point used by ``__main__`` and tests."""
    return await TuiApp(url=url, token=token, identity=identity).run()
