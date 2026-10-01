"""TUI orb tests.

The curses screen cannot be opened in a unit test (and must not be). These
tests drive the parts that are pure: key dispatch, the publish side effects,
the overlay rules, and the Qt-free import. A fake bridge records publishes, so
no socket is opened.

Real-terminal behavior (alternate screen, restoration, resize) is on-target and
stated as unverified in PLAN.md.
"""

import asyncio

from aiassistant.bus import topics
from aiassistant.tui.app import TuiApp, WATCHED_TOPICS
from aiassistant.tui import tokens


class FakeBridge:
    """Records publishes and subscriptions without a socket."""

    def __init__(self):
        self.published: list[tuple[str, dict]] = []
        self.subscribed: list[str] = []
        self.closed = False

    @property
    def subscriptions(self) -> set[str]:
        return set(self.subscribed)

    async def subscribe(self, topic):
        self.subscribed.append(topic)

    async def publish(self, topic, payload=None):
        self.published.append((topic, payload or {}))

    async def run(self):
        return None

    async def close(self):
        self.closed = True


def _app(bridge=None):
    return TuiApp(url="ws://127.0.0.1:1", token="", identity="Jarvis",
                  bridge=bridge or FakeBridge())


def _drive(app, action):
    """Run a key action inside a loop and let its publishes settle.

    ``_handle_key`` schedules publishes with ``ensure_future``, so it needs a
    running loop; the app is designed to run inside one.
    """
    async def scenario():
        action()
        await asyncio.sleep(0)
        await asyncio.sleep(0)
    asyncio.run(scenario())


class TestWatchSet:
    # The GUI orb's watch set, restated here because importing orb.app needs
    # PySide6, which is not installed in a headless test environment.
    ORB_TOPICS = (
        topics.VOICE_STATE,
        topics.VOICE_LEVEL,
        topics.VOICE_TRANSCRIBED,
        topics.AGENT_DELTA,
        topics.AGENT_FINAL,
        topics.AGENT_TOOL_EVENT,
        topics.AGENT_TURN_ERROR,
        topics.AGENT_TRANSCRIPT_SNAPSHOT,
        topics.STATUS_HARNESS,
    )

    def test_watches_the_same_topics_as_the_orb(self):
        assert tuple(WATCHED_TOPICS) == self.ORB_TOPICS

    def test_uses_topic_constants_not_literals(self):
        assert topics.VOICE_STATE in WATCHED_TOPICS
        assert topics.AGENT_DELTA in WATCHED_TOPICS


class TestInputPublishes:
    def test_enter_publishes_user_input_on_the_tui_channel(self):
        bridge = FakeBridge()
        app = _app(bridge)

        def action():
            for ch in "hello":
                app._insert(ch)
            app._submit()

        _drive(app, action)
        assert (topics.USER_INPUT_TEXT, {"text": "hello",
                                         "channel": topics.CHANNEL_TUI}) in bridge.published

    def test_slash_command_stays_local(self):
        bridge = FakeBridge()
        app = _app(bridge)

        def action():
            for ch in "/help":
                app._insert(ch)
            app._submit()

        _drive(app, action)
        assert bridge.published == []
        assert app.ui.help_open is True

    def test_ctrl_t_toggles_mute_and_publishes(self):
        bridge = FakeBridge()
        app = _app(bridge)
        _drive(app, lambda: app._handle_key(tokens.CTRL_T))
        assert bridge.published == [(topics.COMMAND_VOICE_MUTE, {"muted": True})]

    def test_ctrl_dot_interrupts(self):
        bridge = FakeBridge()
        app = _app(bridge)
        _drive(app, lambda: app._handle_key(tokens.CTRL_DOT))
        assert bridge.published == [(topics.COMMAND_AGENT_INTERRUPT, {})]

    def test_exit_publishes_shutdown_without_stopping_the_tui(self):
        bridge = FakeBridge()
        app = _app(bridge)

        def action():
            for ch in "/exit":
                app._insert(ch)
            app._submit()

        _drive(app, action)
        assert bridge.published == [(topics.COMMAND_ASSISTANT_SHUTDOWN, {})]
        assert app._stop is False  # Ctrl+D still owns quitting the TUI itself

    def test_ctrl_d_stops(self):
        app = _app()
        app._handle_key(tokens.CTRL_D)
        assert app._stop is True

    def test_ctrl_c_does_not_quit(self):
        app = _app()
        app._handle_key(tokens.CTRL_C)
        assert app._stop is False

    def test_printable_inserts(self):
        app = _app()
        app._handle_key(ord("x"))
        assert app.ui.composer == "x"

    def test_empty_submit_publishes_nothing(self):
        bridge = FakeBridge()
        app = _app(bridge)
        _drive(app, app._submit)
        assert bridge.published == []


class TestEscapeOrder:
    def test_esc_closes_help_first(self):
        app = _app()
        app.ui.help_open = True
        app._handle_escape()
        assert app.ui.help_open is False

    def test_esc_clears_the_composer_before_interrupting(self):
        bridge = FakeBridge()
        app = _app(bridge)

        def action():
            app._insert("draft")
            app._handle_escape()

        _drive(app, action)
        assert app.ui.composer == ""
        assert bridge.published == []

    def test_esc_interrupts_an_active_turn(self):
        bridge = FakeBridge()
        app = _app(bridge)
        app.model.state = "thinking"
        _drive(app, app._handle_escape)
        assert bridge.published == [(topics.COMMAND_AGENT_INTERRUPT, {})]

    def test_esc_never_quits(self):
        app = _app()
        app._handle_escape()
        assert app._stop is False


class TestFeedAndOverlays:
    def test_voice_state_updates_the_base_state(self):
        app = _app()
        app._on_message(topics.VOICE_STATE, {"state": "listening"})
        assert app.ui.base_state == "listening"
        assert app.model.state == "listening"

    def test_harness_error_sets_backend_down(self):
        app = _app()
        app._on_message(topics.AGENT_TURN_ERROR,
                        {"message": "down", "class": "harness"})
        assert app.ui.overlay == "backend_down"

    def test_a_delta_clears_backend_down(self):
        app = _app()
        app._on_message(topics.AGENT_TURN_ERROR, {"message": "x", "class": "harness"})
        app._on_message(topics.AGENT_DELTA, {"index": 0, "kind": "text", "text": "hi"})
        assert app.ui.overlay == ""


class TestSubscriptions:
    def test_subscribes_to_every_watched_topic(self):
        bridge = FakeBridge()
        app = _app(bridge)
        asyncio.run(app._subscribe_all())
        assert set(bridge.subscribed) == set(WATCHED_TOPICS)

    def test_does_not_resubscribe_when_already_subscribed(self):
        """The bridge replays subscriptions on reconnect; a second subscribe
        would register a duplicate forwarder and double every message."""
        bridge = FakeBridge()
        app = _app(bridge)
        asyncio.run(app._subscribe_all())
        first = list(bridge.subscribed)
        asyncio.run(app._subscribe_all())
        assert bridge.subscribed == first

    def test_subscribes_only_the_topics_missing_after_a_partial_connect(self):
        """A connect that dropped mid-loop must heal on the next one, not leave
        the remaining watched topics unsubscribed forever."""
        bridge = FakeBridge()
        app = _app(bridge)
        bridge.subscribed = list(WATCHED_TOPICS[:3])

        asyncio.run(app._subscribe_all())

        assert set(bridge.subscribed) == set(WATCHED_TOPICS)


class TestConnectResync:
    """A late-connecting client asks for the current state.

    voice.state is edge-triggered, so without the request the TUI stays on
    "Connecting..." for the whole session.
    """

    def test_connect_requests_state_and_harness_after_subscribing(self):
        bridge = FakeBridge()
        app = _app(bridge)

        async def scenario():
            app._loop = asyncio.get_running_loop()
            await app._subscribe_all()
            await asyncio.sleep(0)
            app.stop()
            await asyncio.sleep(0)
        asyncio.run(scenario())

        assert (topics.VOICE_STATE_REQUEST, {}) in bridge.published
        assert (topics.STATUS_HARNESS_REQUEST, {}) in bridge.published
        # Subscribes went out on this connect, then the two requests.
        assert set(bridge.subscribed) == set(WATCHED_TOPICS)
        assert [p[0] for p in bridge.published] == [
            topics.VOICE_STATE_REQUEST, topics.STATUS_HARNESS_REQUEST,
        ]

    def test_reconnect_requests_again_without_resubscribing(self):
        bridge = FakeBridge()
        app = _app(bridge)

        async def first():
            app._loop = asyncio.get_running_loop()
            await app._subscribe_all()
            await asyncio.sleep(0)
            app.stop()
            await asyncio.sleep(0)
        asyncio.run(first())
        first_subscribes = list(bridge.subscribed)
        bridge.published.clear()
        app._resync_task = None

        async def scenario():
            app._loop = asyncio.get_running_loop()
            app._stop = False
            await app._subscribe_all()
            await asyncio.sleep(0)
            app.stop()
            await asyncio.sleep(0)
        asyncio.run(scenario())

        assert bridge.subscribed == first_subscribes
        assert (topics.VOICE_STATE_REQUEST, {}) in bridge.published

    def test_resync_stops_once_the_base_state_arrives(self):
        bridge = FakeBridge()
        app = _app(bridge)

        async def scenario():
            app._loop = asyncio.get_running_loop()
            app._start_resync()
            await asyncio.sleep(0)
            app.ui.base_state = "idle"
            await asyncio.sleep(0)
            count = len([p for p in bridge.published
                         if p[0] == topics.VOICE_STATE_REQUEST])
            await asyncio.sleep(tokens.RESYNC_INTERVAL_S * 2)
            assert app._resync_task is None
            assert len([p for p in bridge.published
                        if p[0] == topics.VOICE_STATE_REQUEST]) == count

        asyncio.run(scenario())

    def test_a_voice_state_reply_clears_connecting_and_mute(self):
        bridge = FakeBridge()
        app = _app(bridge)
        app._on_message(topics.VOICE_STATE,
                        {"state": "muted", "muted": True})
        assert app.model.state == "muted"
        assert app.ui.base_state == "muted"
        assert app._muted is True


class TestNoQt:
    def test_importing_the_tui_pulls_no_qt(self):
        import subprocess
        import sys

        code = (
            "import sys; import aiassistant.tui.app; "
            "print('PySide6' in sys.modules)"
        )
        result = subprocess.run([sys.executable, "-c", code],
                                capture_output=True, text=True)
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "False"


class TestHelpHotword:
    """The TUI help overlay names the configured wake phrase."""

    def test_help_line_names_the_hotword(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(identity="Jarvis", hotwords=["hey jarvis"])
        assert 'say "hey jarvis"' in r._help_lines()[0]

    def test_help_omits_the_line_when_unconfigured(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(identity="Jarvis", hotwords=[])
        assert not r._hotword_line()
        assert not any("Hotword" in line for line in r._help_lines())

    def test_help_width_fits_the_longest_line(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(hotwords=["a very long wake phrase indeed"])
        assert max(len(line) for line in r._help_lines()) <= 200

    def test_config_supplies_hotwords_to_the_app(self):
        from aiassistant.tui.app import TuiApp
        app = TuiApp(url="ws://127.0.0.1:1", token="", identity="J",
                     bridge=FakeBridge(), hotwords=["hey jarvis"])
        assert app.renderer.hotwords == ["hey jarvis"]

    def test_empty_state_names_the_configured_hotword(self):
        """The empty-state hint must name config, never a literal phrase.

        A hard-coded phrase tells the user to say something the pipeline does
        not listen for ("hi jarvis" while config said "hey jarvis").
        """
        from aiassistant.tui.render import Renderer
        r = Renderer(hotwords=["hey jarvis"])
        assert r._empty_text() == (
            'No messages yet. Say "hey jarvis" or type below.'
        )
        assert "hi jarvis" not in r._empty_text()

    def test_empty_state_reflects_a_different_configured_phrase(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(hotwords=["computer"])
        assert '"computer"' in r._empty_text()

    def test_empty_state_without_a_hotword_omits_the_say_clause(self):
        from aiassistant.tui.render import Renderer
        r = Renderer(hotwords=[])
        assert r._empty_text() == "No messages yet. Type below."


class TestInterruptButton:
    """The control bar exposes a clickable stop button, not just a key.

    The renderer draws the labels and records their hitboxes; the app maps a
    click through them, so a mouse-only user can interrupt a turn.
    """

    def _renderer_at(self, cols):
        import curses
        from aiassistant.tui.render import Renderer, UIState
        from aiassistant.orb.model import OrbViewModel

        r = Renderer(hotwords=["hey jarvis"])
        r.setup()
        win = curses.initscr()
        win.erase()
        model = OrbViewModel()
        model.state = "thinking"
        r._draw_full(win, model, UIState(base_state="thinking"), 24, cols)
        return r

    def test_a_wide_terminal_has_a_stop_hitbox(self):
        r = self._renderer_at(120)
        actions = [action for _, _, _, action in r.button_hitboxes]
        assert "stop" in actions, "the stop button must be clickable"
        assert "mute" in actions

    def test_button_at_maps_a_click_to_an_action(self):
        r = self._renderer_at(120)
        row, start, end, action = next(
            b for b in r.button_hitboxes if b[3] == "stop")
        assert r.button_at(row, start) == "stop"
        assert r.button_at(row, end - 1) == "stop"
        # A cell outside every hitbox maps to nothing.
        assert r.button_at(row, end + 50) == ""

    def test_a_narrow_terminal_hides_the_buttons(self):
        r = self._renderer_at(80)
        assert r.button_hitboxes == [], (
            "buttons must not collide with the meter on a narrow terminal"
        )

    def test_the_mute_button_reflects_state(self):
        import curses
        from aiassistant.tui.render import Renderer, UIState
        from aiassistant.orb.model import OrbViewModel

        r = Renderer(hotwords=[])
        r.setup()
        win = curses.initscr()
        model = OrbViewModel()
        model.state = "muted"
        r._draw_buttons(win, model, UIState(base_state="muted"), 20, 140)
        labels = [label for action, label in r._buttons(model,
                                                        UIState(base_state="muted"))]
        assert any("unmute" in label for label in labels)


class TestMouseDispatch:
    """A click on a button publishes the matching command."""

    def test_a_stop_click_publishes_interrupt(self, monkeypatch):
        import curses
        from aiassistant.tui.app import TuiApp

        bridge = FakeBridge()
        app = TuiApp(url="ws://127.0.0.1:1", token="", identity="J",
                     bridge=bridge, hotwords=[])
        # A recorded hitbox that maps the clicked cell to "stop".
        app.renderer.button_hitboxes = [(5, 10, 18, "stop")]
        monkeypatch.setattr(curses, "getmouse",
                            lambda: (0, 12, 5, 0, curses.BUTTON1_CLICKED))

        async def scenario():
            app._loop = asyncio.get_running_loop()
            app._handle_mouse()
            await asyncio.sleep(0)
        asyncio.run(scenario())

        assert (topics.COMMAND_AGENT_INTERRUPT, {}) in bridge.published

    def test_a_click_outside_a_button_publishes_nothing(self, monkeypatch):
        import curses
        from aiassistant.tui.app import TuiApp

        bridge = FakeBridge()
        app = TuiApp(url="ws://127.0.0.1:1", token="", identity="J",
                     bridge=bridge, hotwords=[])
        app.renderer.button_hitboxes = [(5, 10, 18, "stop")]
        monkeypatch.setattr(curses, "getmouse",
                            lambda: (0, 60, 5, 0, curses.BUTTON1_CLICKED))

        async def scenario():
            app._loop = asyncio.get_running_loop()
            app._handle_mouse()
            await asyncio.sleep(0)
        asyncio.run(scenario())

        assert not any(t == topics.COMMAND_AGENT_INTERRUPT
                       for t, _ in bridge.published)
